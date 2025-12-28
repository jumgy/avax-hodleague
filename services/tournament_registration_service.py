from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from fastapi import HTTPException, status
import hashlib
from typing import List

from models.tournament_deck_models import TournamentDeck
from models.tournament_models import Tournament
from models.user_card_models import UserCard
from models.card_models import Card
from models.rarity_models import Rarity
from models.token_models import Token

class TournamentRegistrationService:
    """
    Сервис для управления регистрацией игроков в турниры
    """
    
    @staticmethod
    def generate_deck_hash(tournament_id: int, user_id: int, deck_composition: List[int]) -> str:
        """Генерирует SHA256 хеш деки"""
        sorted_deck = sorted(deck_composition)
        hash_string = f"{tournament_id}:{user_id}:{':'.join(map(str, sorted_deck))}"
        return hashlib.sha256(hash_string.encode()).hexdigest()
    
    @staticmethod
    async def validate_and_register_deck(
        db: AsyncSession,
        tournament_id: int,
        user_id: int,
        deck_composition: List[int]
    ) -> TournamentDeck:
        """
        Валидирует и регистрирует деку в турнире.
        Фиксирует total_weight как снэпшот на момент регистрации.
        """
        
        # 1. Проверка: ровно 5 карт
        if len(deck_composition) != 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Deck must contain exactly 5 cards"
            )
        
        # 2. Проверка: нет дубликатов
        if len(set(deck_composition)) != 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Deck cannot contain duplicate cards"
            )
        
        # 3. Турнир существует и status = "registration"
        tournament_query = select(Tournament).where(Tournament.id == tournament_id)
        tournament = (await db.execute(tournament_query)).scalar_one_or_none()
        
        if not tournament:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tournament not found"
            )
        
        if tournament.status != "registration":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tournament registration is closed. Current status: {tournament.status}"
            )
        
        # 4. Юзер еще не зарегистрирован
        existing_deck_query = select(TournamentDeck).where(
            and_(
                TournamentDeck.tournament_id == tournament_id,
                TournamentDeck.user_id == user_id,
                TournamentDeck.is_active == True
            )
        )
        existing_deck = (await db.execute(existing_deck_query)).scalar_one_or_none()
        
        if existing_deck:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You are already registered for this tournament. Use PUT endpoint to update your deck."
            )
        
        # 5. Получаем карты с join к Card и Token
        cards_query = select(UserCard, Card, Token, Rarity).join(
            Card, UserCard.card_id == Card.id
        ).join(
            Token, Card.token_id == Token.id
        ).join(
            Rarity, Card.rarity_id == Rarity.id
        ).where(
            and_(
                UserCard.id.in_(deck_composition),
                UserCard.user_id == user_id
            )
        )
        cards_result = (await db.execute(cards_query)).all()
        
        # 6. Все карты принадлежат юзеру
        if len(cards_result) != 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more cards do not belong to you"
            )
        
        # 7. Валидация статуса и подсчёт веса
        total_weight = 0.0
        
        for user_card, card, token, rarity in cards_result:
            # Проверка статуса
            if user_card.status != "available":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Card #{user_card.id} ({token.name} - {rarity.name}) is not available. Status: {user_card.status}" 
                )
            
            # Проверка is_active
            if not user_card.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Card #{user_card.id} ({token.name} - {rarity.name}) is not active"
                )
            
            # Суммируем вес
            total_weight += float(token.weight)
        
        # 8. Проверка лимита веса
        if total_weight > float(tournament.weight_limit):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Deck weight {total_weight:.2f} exceeds tournament limit {float(tournament.weight_limit):.2f}"
            )
        
        # 9. Генерируем хеш деки
        deck_hash = TournamentRegistrationService.generate_deck_hash(
            tournament_id, user_id, deck_composition
        )
        
        # 10. Создаём TournamentDeck
        tournament_deck = TournamentDeck(
            tournament_id=tournament_id,
            user_id=user_id,
            deck_composition=deck_composition,
            deck_hash=deck_hash,
            total_weight=total_weight,
            is_valid=True,
            is_active=True
        )
        db.add(tournament_deck)
        
        # 11. Блокируем карты
        for user_card, card, token, rarity in cards_result:
            user_card.status = "locked"
        
        await db.commit()
        await db.refresh(tournament_deck)
        
        return tournament_deck