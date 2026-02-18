import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import Config
from models.card_models import Card
from models.rarity_models import Rarity
from models.token_models import Token
from models.tournament_deck_models import TournamentDeck
from models.tournament_models import Tournament
from models.user_card_models import UserCard
from services.chain_balance_service import get_native_balance_wei
from services.web3_verification_service import Web3VerificationService

logger = logging.getLogger(__name__)


class TournamentRegistrationService:
    """
    Сервис для управления регистрацией игроков в турниры с блокчейн-верификацией
    """

    @staticmethod
    def generate_deck_hash(tournament_id: int, user_id: int, deck_composition: list[int]) -> str:
        """Генерирует SHA256 хеш деки"""
        sorted_deck = sorted(deck_composition)
        hash_string = f"{tournament_id}:{user_id}:{':'.join(map(str, sorted_deck))}"
        return hashlib.sha256(hash_string.encode()).hexdigest()

    @staticmethod
    async def _validate_deck_common(
        db: AsyncSession, tournament_id: int, user_id: int, deck_composition: list[int]
    ) -> tuple:
        """
        Общая валидация деки (используется и для preview, и для финальной регистрации).
        Возвращает: (tournament, cards_result, total_weight)
        """
        # 1. Проверка: ровно 5 карт
        if len(deck_composition) != 5:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Deck must contain exactly 5 cards")

        # 2. Проверка: нет дубликатов user_card_id
        if len(set(deck_composition)) != 5:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Deck cannot contain duplicate cards")

        # 3. Турнир существует и status = "registration"
        tournament_query = select(Tournament).where(Tournament.id == tournament_id)
        tournament = (await db.execute(tournament_query)).scalar_one_or_none()

        if not tournament:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tournament not found")

        if tournament.status != "registration":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tournament registration is closed. Current status: {tournament.status}",
            )

        # 4. Юзер еще не зарегистрирован
        existing_deck_query = select(TournamentDeck).where(
            and_(
                TournamentDeck.tournament_id == tournament_id,
                TournamentDeck.user_id == user_id,
                TournamentDeck.is_active == True,
            )
        )
        existing_deck = (await db.execute(existing_deck_query)).scalar_one_or_none()

        if existing_deck:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="You are already registered for this tournament"
            )

        # 5. Получаем карты с join к Card и Token
        cards_query = (
            select(UserCard, Card, Token, Rarity)
            .join(Card, UserCard.card_id == Card.id)
            .join(Token, Card.token_id == Token.id)
            .join(Rarity, Card.rarity_id == Rarity.id)
            .where(and_(UserCard.id.in_(deck_composition), UserCard.user_id == user_id))
        )
        cards_result = (await db.execute(cards_query)).all()

        # 6. Все карты принадлежат юзеру
        if len(cards_result) != 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="One or more cards do not belong to you"
            )

        # 7. Проверка: нет двух карт одного токена
        token_ids = [token.id for _, _, token, _ in cards_result]
        if len(set(token_ids)) != 5:
            # Находим дубликаты для сообщения об ошибке
            from collections import Counter

            token_counts = Counter(token_ids)
            duplicate_tokens = [token.name for _, _, token, _ in cards_result if token_counts[token.id] > 1]
            duplicate_tokens_unique = list(set(duplicate_tokens))

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Deck cannot contain multiple cards of the same token. Duplicate token(s): {', '.join(duplicate_tokens_unique)}",
            )

        # 8. Валидация статуса и подсчёт веса
        total_weight = 0.0
        now = datetime.now(UTC)

        for user_card, card, token, rarity in cards_result:
            # Проверка expires_at
            if user_card.expires_at and user_card.expires_at <= now:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Card #{user_card.id} ({token.name} - {rarity.name}) has expired",
                )

            # Проверка статуса
            if user_card.status != "available":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Card #{user_card.id} ({token.name} - {rarity.name}) is not available. Status: {user_card.status}",
                )

            # Проверка is_active
            if not user_card.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Card #{user_card.id} ({token.name} - {rarity.name}) is not active",
                )

            # Суммируем вес
            total_weight += float(token.weight)

        # 9. Проверка лимита веса
        if total_weight > float(tournament.weight_limit):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Deck weight {total_weight:.2f} exceeds tournament limit {float(tournament.weight_limit):.2f}",
            )

        return tournament, cards_result, total_weight

    @staticmethod
    async def validate_deck_preview(
        db: AsyncSession, tournament_id: int, user_id: int, deck_composition: list[int]
    ) -> dict:
        """
        ПРЕ-ВАЛИДАЦИЯ деки БЕЗ ЗАПИСИ В БД.

        Используется фронтендом ПЕРЕД вызовом смарт-контракта.
        Возвращает deck_hash который нужно передать в контракт.

        :return: {
            "valid": True,
            "deck_hash": "0x...",
            "total_weight": float,
            "weight_limit": float,
            "cards": [...]
        }
        """

        # Выполняем все проверки (без записи в БД)
        tournament, cards_result, total_weight = await TournamentRegistrationService._validate_deck_common(
            db, tournament_id, user_id, deck_composition
        )

        # Генерируем deck_hash
        deck_hash = TournamentRegistrationService.generate_deck_hash(tournament_id, user_id, deck_composition)

        # Формируем ответ
        cards_info = [
            {"user_card_id": uc.id, "card_name": token.name, "rarity": rarity.name, "weight": float(token.weight)}
            for uc, card, token, rarity in cards_result
        ]

        return {
            "valid": True,
            "deck_hash": f"0x{deck_hash}",  # Добавляем 0x для контракта
            "total_weight": total_weight,
            "weight_limit": float(tournament.weight_limit),
            "cards": cards_info,
            "message": "Deck is valid. You can now register on-chain with this deck_hash.",
        }

    @staticmethod
    async def get_registration_network_recommendation(wallet_address: str) -> dict[str, Any]:
        """
        Рекомендация сети для регистрации по балансу газа.
        Если на Abstract нет газа, но есть на Avalanche — рекомендуем переключиться на Avalanche.
        При ошибках RPC или при отсутствии конфига Avalanche — fallback на Abstract.

        :return: preferred_network, switch_network_required, avalanche_chain_id, avalanche_contract_address, message
        """
        result: dict[str, Any] = {
            "preferred_network": "abstract",
            "switch_network_required": False,
            "avalanche_chain_id": None,
            "avalanche_contract_address": None,
            "message": None,
        }

        wallet = (wallet_address or "").strip()
        if not wallet:
            logger.warning(
                "get_registration_network_recommendation: wallet_address is empty, cannot check gas; defaulting to Abstract"
            )
            return result

        if not Config.WEB3_PROVIDER_URL_AVALANCHE or not Config.TOURNAMENT_CONTRACT_ADDRESS_AVALANCHE:
            logger.info(
                "Avalanche not configured (WEB3_PROVIDER_URL_AVALANCHE or TOURNAMENT_CONTRACT_ADDRESS_AVALANCHE missing); "
                "network recommendation defaults to Abstract"
            )
            return result

        try:
            balance_abstract = await get_native_balance_wei(Config.WEB3_PROVIDER_URL, wallet)
            balance_avax = await get_native_balance_wei(Config.WEB3_PROVIDER_URL_AVALANCHE, wallet)
        except Exception as e:
            logger.warning("Balance check failed, defaulting to Abstract: %s", e)
            return result

        has_gas_abstract = balance_abstract is not None and balance_abstract >= Config.MIN_GAS_BALANCE_ABSTRACT
        has_gas_avax = balance_avax is not None and balance_avax >= Config.MIN_GAS_BALANCE_AVALANCHE

        logger.debug(
            "Gas check: abstract=%s (min=%s), avax=%s (min=%s); has_abstract=%s, has_avax=%s",
            balance_abstract,
            Config.MIN_GAS_BALANCE_ABSTRACT,
            balance_avax,
            Config.MIN_GAS_BALANCE_AVALANCHE,
            has_gas_abstract,
            has_gas_avax,
        )

        if has_gas_abstract:
            return result
        if has_gas_avax:
            result["preferred_network"] = "avalanche"
            result["switch_network_required"] = True
            result["avalanche_chain_id"] = Config.AVALANCHE_CHAIN_ID
            result["avalanche_contract_address"] = Config.TOURNAMENT_CONTRACT_ADDRESS_AVALANCHE
            result["message"] = "Not enough gas on Abstract. Switch to Avalanche to register."
            logger.info(
                "Network recommendation: no gas on Abstract, gas on Avalanche → preferred_network=avalanche, "
                "switch_network_required=True"
            )
            return result
        return result

    @staticmethod
    def _web3_config_for_network(network: str) -> tuple[str, str, int]:
        """Return (provider_url, contract_address, chain_id) for the given network."""
        if network == "avalanche":
            if not Config.WEB3_PROVIDER_URL_AVALANCHE or not Config.TOURNAMENT_CONTRACT_ADDRESS_AVALANCHE:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Avalanche is not configured. Use network=abstract.",
                )
            return (
                Config.WEB3_PROVIDER_URL_AVALANCHE,
                Config.TOURNAMENT_CONTRACT_ADDRESS_AVALANCHE,
                Config.AVALANCHE_CHAIN_ID,
            )
        return (
            Config.WEB3_PROVIDER_URL,
            Config.TOURNAMENT_CONTRACT_ADDRESS,
            Config.ABSTRACT_CHAIN_ID,
        )

    @staticmethod
    async def register_deck_with_verification(
        db: AsyncSession,
        tournament_id: int,
        user_id: int,
        user_wallet: str,
        deck_composition: list[int],
        tx_hash: str,
        network: str = "abstract",
    ) -> TournamentDeck:
        """
        ФИНАЛЬНАЯ РЕГИСТРАЦИЯ с проверкой блокчейн-транзакции.

        Вызывается ПОСЛЕ того как юзер подписал транзакцию в контракте.

        :param network: "abstract" или "avalanche" — сеть, в которой подписана транзакция
        :return: TournamentDeck
        """

        # 1. Базовая валидация деки
        tournament, cards_result, total_weight = await TournamentRegistrationService._validate_deck_common(
            db, tournament_id, user_id, deck_composition
        )

        # 2. Генерируем deck_hash
        deck_hash = TournamentRegistrationService.generate_deck_hash(tournament_id, user_id, deck_composition)

        # 3. ПРОВЕРЯЕМ БЛОКЧЕЙН-ТРАНЗАКЦИЮ в выбранной сети
        provider_url, contract_address, chain_id = TournamentRegistrationService._web3_config_for_network(network)
        web3_service = Web3VerificationService(
            web3_provider_url=provider_url,
            contract_address=contract_address,
            contract_abi=Config.TOURNAMENT_CONTRACT_ABI,
        )

        verification = await web3_service.verify_register_transaction(
            tx_hash=tx_hash, tournament_id=tournament_id, expected_deck_hash=deck_hash, user_wallet=user_wallet
        )

        if not verification["valid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Transaction verification failed: {verification['error']}",
            )

        # 4. Создаём TournamentDeck (сохраняем chain_id для аудита)
        tournament_deck = TournamentDeck(
            tournament_id=tournament_id,
            user_id=user_id,
            deck_composition=deck_composition,
            deck_hash=deck_hash,
            transaction_hash=tx_hash,
            total_weight=total_weight,
            is_valid=True,
            is_active=True,
            registration_chain_id=chain_id,
        )

        db.add(tournament_deck)

        # 5. Блокируем карты
        for user_card, card, token, rarity in cards_result:
            user_card.status = "locked"

        await db.commit()
        await db.refresh(tournament_deck)

        return tournament_deck

    @staticmethod
    async def unregister_deck_with_verification(
        db: AsyncSession,
        tournament_id: int,
        user_id: int,
        user_wallet: str,
        tx_hash: str,
        network: str = "abstract",
    ) -> dict:
        """
        Отмена регистрации с проверкой блокчейн-транзакции.

        Юзер должен сначала вызвать unregisterDeck в контракте (в той же сети, что и при регистрации),
        потом передать tx_hash и network сюда для разблокировки карт.

        :param network: "abstract" или "avalanche" — сеть, в которой подписана unregister-транзакция
        :return: {"success": True, "cards_unlocked": int, "tx_hash": str}
        """

        # 1. Проверяем что турнир в статусе registration
        tournament_query = select(Tournament).where(Tournament.id == tournament_id)
        tournament = (await db.execute(tournament_query)).scalar_one_or_none()

        if not tournament:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tournament not found")

        if tournament.status != "registration":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot unregister after registration closed"
            )

        # 2. Найти активную деку
        deck_query = select(TournamentDeck).where(
            and_(
                TournamentDeck.tournament_id == tournament_id,
                TournamentDeck.user_id == user_id,
                TournamentDeck.is_active == True,
            )
        )
        deck = (await db.execute(deck_query)).scalar_one_or_none()

        if not deck:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not registered in this tournament")

        # 3. ПРОВЕРЯЕМ ТРАНЗАКЦИЮ UNREGISTER в выбранной сети
        provider_url, contract_address, _ = TournamentRegistrationService._web3_config_for_network(network)
        web3_service = Web3VerificationService(
            web3_provider_url=provider_url,
            contract_address=contract_address,
            contract_abi=Config.TOURNAMENT_CONTRACT_ABI,
        )

        verification = await web3_service.verify_unregister_transaction(
            tx_hash=tx_hash, tournament_id=tournament_id, user_wallet=user_wallet
        )

        if not verification["valid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unregister verification failed: {verification['error']}",
            )

        # 4. РАЗБЛОКИРУЕМ КАРТЫ
        cards_query = select(UserCard).where(UserCard.id.in_(deck.deck_composition))
        cards = (await db.execute(cards_query)).scalars().all()

        unlocked_count = 0
        for card in cards:
            if card.status == "locked":
                card.status = "available"
                unlocked_count += 1

        # 5. ДЕАКТИВИРУЕМ ДЕКУ
        deck.is_active = False

        await db.commit()

        return {
            "success": True,
            "cards_unlocked": unlocked_count,
            "tx_hash": tx_hash,
            "message": f"Successfully unregistered from tournament. {unlocked_count} cards unlocked.",
        }
