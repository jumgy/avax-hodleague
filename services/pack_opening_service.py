# services/pack_opening_service.py

from sqlalchemy import select, func, update, or_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, List, Optional, Any
import random
import logging
from datetime import datetime, timezone, timedelta

from models.pack_models import PackType
from models.user_pack_models import UserPack, PackOpening
from models.user_card_models import UserCard
from models.card_models import Card

logger = logging.getLogger(__name__)

class PackOpeningService:
    """Service for pack opening logic"""

    async def check_pack_availability(
        self, 
        user_id: int, 
        pack_type_id: Optional[int], 
        db: AsyncSession
    ) -> Dict:
        """
        Check available packs for user
        
        Args:
            user_id: User ID
            pack_type_id: Specific pack type ID (optional)
            db: Database session
            
        Returns:
            Dict with available packs info
        """
        try:
            query = select(
                UserPack.pack_type_id,
                func.count(UserPack.id).label('count')
            ).where(
                UserPack.user_id == user_id,
                UserPack.is_opened == False
            )
            
            if pack_type_id:
                query = query.where(UserPack.pack_type_id == pack_type_id)
            
            query = query.group_by(UserPack.pack_type_id)
            
            result = await db.execute(query)
            rows = result.all()
            
            packs_by_type = {row.pack_type_id: row.count for row in rows}
            total = sum(packs_by_type.values())
            
            return {
                "total": total,
                "by_type": packs_by_type
            }
            
        except Exception as e:
            logger.error(f"Error checking pack availability for user {user_id}: {e}")
            return {"total": 0, "by_type": {}}

    async def get_pack_type_details(
        self, 
        pack_type_id: int, 
        db: AsyncSession
    ) -> Optional[PackType]:
        """Get pack type configuration"""
        try:
            result = await db.execute(
                select(PackType).where(
                    PackType.id == pack_type_id,
                    PackType.is_active == True
                )
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting pack type {pack_type_id}: {e}")
            return None

    async def generate_cards_for_pack(
        self, 
        pack_type: PackType, 
        db: AsyncSession
    ) -> List[int]:
        """
        Generate card IDs based on pack type rules
        
        Args:
            pack_type: PackType object with guaranteed_slots
            db: Database session
            
        Returns:
            List of card_ids
        """
        try:
            guaranteed_slots = pack_type.guaranteed_slots
            
            # Детальная валидация конфигурации
            if not guaranteed_slots:
                logger.error(f"Pack type {pack_type.id} ({pack_type.name}) has NULL guaranteed_slots")
                raise ValueError(f"Pack type '{pack_type.name}' has no configuration (guaranteed_slots is NULL)")
            
            if not isinstance(guaranteed_slots, dict):
                logger.error(f"Pack type {pack_type.id} guaranteed_slots is not a dict: {type(guaranteed_slots)}")
                raise ValueError(f"Pack type '{pack_type.name}' has invalid configuration format")
            
            if 'card_pools' not in guaranteed_slots:
                logger.error(f"Pack type {pack_type.id} missing 'card_pools': {guaranteed_slots}")
                raise ValueError(f"Pack type '{pack_type.name}' missing 'card_pools' in configuration")
            
            if 'drop_rules' not in guaranteed_slots:
                logger.error(f"Pack type {pack_type.id} missing 'drop_rules': {guaranteed_slots}")
                raise ValueError(f"Pack type '{pack_type.name}' missing 'drop_rules' in configuration")
            
            card_pools = guaranteed_slots['card_pools']
            drop_rules = guaranteed_slots['drop_rules']
            
            logger.info(f"Opening pack type {pack_type.id} ({pack_type.name})")
            logger.info(f"Card pools: {card_pools}")
            logger.info(f"Drop rules: {drop_rules}")
            
            selected_card_ids = []
            
            # Process each category (top, mid, low, etc.)
            for category, count in drop_rules.items():
                if category not in card_pools:
                    logger.warning(f"Category '{category}' in drop_rules but not in card_pools - skipping")
                    continue
                
                token_symbols = card_pools[category]
                
                if not token_symbols:
                    logger.warning(f"Category '{category}' has empty token list - skipping")
                    continue
                
                if len(token_symbols) < count:
                    logger.warning(f"Category '{category}': need {count} cards, but only {len(token_symbols)} available - taking all")
                    selected_symbols = token_symbols
                else:
                    # Random selection without replacement
                    selected_symbols = random.sample(token_symbols, count)
                
                logger.info(f"Category '{category}': selected {selected_symbols}")
                
                # Get card_id for each selected token
                for symbol in selected_symbols:
                    card_id = await self._get_card_id_by_symbol(symbol, db)
                    if card_id:
                        selected_card_ids.append(card_id)
                        logger.info(f"  {symbol} → card_id {card_id}")
                    else:
                        logger.warning(f"  {symbol} → NOT FOUND (skipping)")
            
            if len(selected_card_ids) != pack_type.cards_per_pack:
                logger.warning(
                    f"Generated {len(selected_card_ids)} cards, expected {pack_type.cards_per_pack}"
                )
            
            if not selected_card_ids:
                raise ValueError(f"Failed to generate any cards for pack '{pack_type.name}' - check token symbols")
            
            logger.info(f"Final card_ids: {selected_card_ids}")
            return selected_card_ids
            
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error generating cards for pack {pack_type.id}: {e}")
            raise ValueError(f"Failed to generate cards for pack '{pack_type.name}': {str(e)}")

    async def _get_card_id_by_symbol(
        self, 
        token_symbol: str, 
        db: AsyncSession
    ) -> Optional[int]:
        """
        Find active card by token symbol
        Since each token has only one card, we just pick the first active one
        """
        try:
            # Join Card with Token to find by symbol
            from models.token_models import Token
            
            result = await db.execute(
                select(Card.id)
                .join(Token, Card.token_id == Token.id)
                .where(
                    Token.symbol == token_symbol,
                    Token.is_active == True,
                    Card.is_active == True
                )
                .limit(1)
            )
            
            card_id = result.scalar_one_or_none()
            return card_id
            
        except Exception as e:
            logger.error(f"Error finding card for symbol {token_symbol}: {e}")
            return None
        
    async def _calculate_expires_at(self, db: AsyncSession) -> datetime:
        """
        Рассчитывает expires_at для карт.
        Логика:
        - Если есть турнир в REGISTRATION → ближайшая пятница 17:00 UTC
        - Если НЕТ → пятница через неделю 17:00 UTC
        """
        from sqlalchemy import select
        from models.tournament_models import Tournament, TournamentStatus
        
        # Проверяем, есть ли турнир с ОТКРЫТОЙ регистрацией
        result = await db.execute(
            select(Tournament).where(
                Tournament.status == TournamentStatus.REGISTRATION,
                Tournament.is_active == True
            ).order_by(Tournament.start_date.asc())
        )
        open_tournament = result.scalars().first()
        
        # Получаем ближайшую пятницу 17:00
        nearest_friday = self._get_next_friday_17utc()
        
        if open_tournament:
            # Есть турнир с ОТКРЫТОЙ регистрацией → карты до ближайшей пятницы
            logger.info(f"📅 Open REGISTRATION tournament found → expires_at: nearest Friday {nearest_friday}")
            return nearest_friday
        else:
            # Нет турнира с открытой регистрацией → карты до пятницы через неделю
            next_week_friday = nearest_friday + timedelta(days=7)
            logger.info(f"📅 No open REGISTRATION tournament → expires_at: next week Friday {next_week_friday}")
            return next_week_friday


    def _get_next_friday_17utc(self) -> datetime:
        """Возвращает ближайшую пятницу 17:00 UTC"""
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        current_weekday = now.weekday()  # 0 = Monday, 4 = Friday
        
        # Если сегодня пятница
        if current_weekday == 4:
            friday_17 = now.replace(hour=17, minute=0, second=0, microsecond=0)
            if now < friday_17:
                # Ещё не 17:00 → возвращаем сегодня
                return friday_17
            else:
                # Уже после 17:00 → следующая пятница
                return friday_17 + timedelta(days=7)
        
        # Если понедельник-четверг → ближайшая пятница
        if current_weekday < 4:
            days_until_friday = 4 - current_weekday
        # Если суббота-воскресенье → следующая пятница
        else:
            days_until_friday = 7 - current_weekday + 4
        
        next_friday = now + timedelta(days=days_until_friday)
        return next_friday.replace(hour=17, minute=0, second=0, microsecond=0)

    async def open_pack(
        self, 
        user_id: int, 
        pack_type_id: Optional[int],
        db: AsyncSession
    ) -> Dict:
        """
        Complete pack opening process
        
        Args:
            user_id: User ID
            pack_type_id: Specific pack type (if None, opens first available)
            db: Database session
            
        Returns:
            Dict with opening results
        """
        try:
            async with db.begin_nested():
                # 1. Find unopened pack
                query = select(UserPack).where(
                    UserPack.user_id == user_id,
                    UserPack.is_opened == False
                )
                
                if pack_type_id:
                    query = query.where(UserPack.pack_type_id == pack_type_id)
                
                query = query.limit(1)
                
                result = await db.execute(query)
                user_pack = result.scalar_one_or_none()
                
                if not user_pack:
                    raise ValueError("No unopened packs available")
                
                # 2. Get pack type configuration
                pack_type = await self.get_pack_type_details(user_pack.pack_type_id, db)
                if not pack_type:
                    raise ValueError(f"Pack type {user_pack.pack_type_id} not found or inactive")
                
                # 3. Generate cards
                card_ids = await self.generate_cards_for_pack(pack_type, db)
                
                if not card_ids:
                    raise ValueError("Failed to generate cards")
                
                # 4. Create pack opening record
                pack_opening = PackOpening(
                    user_id=user_id,
                    pack_id=user_pack.id,
                    opened_at=datetime.utcnow(),
                    cards_count=len(card_ids)
                )
                db.add(pack_opening)
                await db.flush()  # Get pack_opening.id
                
                # 5. Create user_cards
                created_cards = []

                expires_at = await self._calculate_expires_at(db)

                for card_id in card_ids:
                    user_card = UserCard(
                        user_id=user_id,
                        card_id=card_id,
                        pack_opening_id=pack_opening.id,
                        obtained_at=datetime.utcnow(),
                        source="pack_opening",
                        status="available",
                        is_active=True,
                        expires_at=expires_at
                    )
                    db.add(user_card)
                    created_cards.append(user_card)
                
                await db.flush()  # Get user_card IDs
                
                # 6. Mark pack as opened
                user_pack.is_opened = True
                
                await db.flush()
                
                # 7. Get full card details for response
                cards_data = await self._get_cards_details(
                    [uc.id for uc in created_cards], 
                    db
                )
                
                return {
                    "pack_opening_id": pack_opening.id,
                    "pack_type_name": pack_type.name,
                    "opened_at": pack_opening.opened_at.isoformat(),
                    "cards_received": cards_data
                }
                
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error opening pack for user {user_id}: {e}")
            raise

    async def _get_cards_details(
        self, 
        user_card_ids: List[int], 
        db: AsyncSession
    ) -> List[Dict]:
        """Get full card details for opened cards"""
        try:
            from sqlalchemy import text
            
            query = text("""
                SELECT 
                    uc.id as user_card_id,
                    acs.card_id,
                    acs.token_symbol,
                    acs.token_name,
                    acs.token_image_url,
                    acs.rarity_name,
                    acs.rarity_color,
                    acs.design_type,
                    acs.rendered_image_url
                FROM user_cards uc
                JOIN active_cards_with_score acs ON uc.card_id = acs.card_id
                WHERE uc.id = ANY(:user_card_ids)
            """)
            
            result = await db.execute(query, {"user_card_ids": user_card_ids})
            rows = result.fetchall()
            
            cards = []
            for row in rows:
                cards.append({
                    "user_card_id": row.user_card_id,
                    "card_id": row.card_id,
                    "token_symbol": row.token_symbol,
                    "token_name": row.token_name,
                    "token_image_url": row.token_image_url,
                    "rarity_name": row.rarity_name,
                    "rarity_color": row.rarity_color,
                    "design_type": row.design_type,
                    "rendered_image_url": row.rendered_image_url
                })
            
            return cards
            
        except Exception as e:
            logger.error(f"Error getting card details: {e}")
            return []

    async def get_pack_history(
        self, 
        user_id: int, 
        limit: int, 
        offset: int, 
        db: AsyncSession
    ) -> Dict:
        """Get pack opening history with cards received"""
        try:
            from sqlalchemy import func, text
            
            # Count total openings
            count_result = await db.execute(
                select(func.count(PackOpening.id))
                .where(PackOpening.user_id == user_id)
            )
            total = count_result.scalar() or 0
            
            # Get paginated history
            query = select(
                PackOpening.id,
                PackOpening.opened_at,
                PackOpening.cards_count,
                PackType.name.label('pack_type_name')
            ).join(
                UserPack, PackOpening.pack_id == UserPack.id
            ).join(
                PackType, UserPack.pack_type_id == PackType.id
            ).where(
                PackOpening.user_id == user_id
            ).order_by(
                PackOpening.opened_at.desc()
            ).limit(limit).offset(offset)
            
            result = await db.execute(query)
            rows = result.all()
            
            openings = []
            for row in rows:
                # Get cards for this opening
                cards = await self._get_opening_cards(row.id, db)
                
                openings.append({
                    "pack_opening_id": row.id,
                    "pack_type_name": row.pack_type_name,
                    "opened_at": row.opened_at.isoformat(),
                    "cards_count": row.cards_count,
                    "cards_received": cards
                })
            
            return {
                "total": total,
                "openings": openings
            }
            
        except Exception as e:
            logger.error(f"Error getting pack history for user {user_id}: {e}")
            return {"total": 0, "openings": []}
    
    async def get_pack_opening_by_id(
        self,
        pack_opening_id: int,
        user_id: int,
        db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """
        Get specific pack opening by ID
        Returns None if not found or user doesn't have access
        """
        from models.user_pack_models import PackOpening, UserPack  # Исправленный импорт
        from models.user_card_models import UserCard
        from models.card_models import Card
        from models.token_models import Token
        from models.rarity_models import Rarity
        from models.pack_models import PackType
        
        # Get pack opening with verification that it belongs to user
        result = await db.execute(
            select(PackOpening, UserPack, PackType)
            .join(UserPack, PackOpening.pack_id == UserPack.id)
            .join(PackType, UserPack.pack_type_id == PackType.id)
            .where(
                PackOpening.id == pack_opening_id,
                PackOpening.user_id == user_id
            )
        )
        pack_data = result.first()
        
        if not pack_data:
            return None
        
        pack_opening, user_pack, pack_type = pack_data
        
        # Get cards from this opening
        result = await db.execute(
            select(UserCard, Card, Token, Rarity)
            .join(Card, UserCard.card_id == Card.id)
            .join(Token, Card.token_id == Token.id)
            .join(Rarity, Card.rarity_id == Rarity.id)
            .where(UserCard.pack_opening_id == pack_opening_id)
            .order_by(UserCard.id)
        )
        cards_data = result.all()
        
        # Format cards
        cards_received = []
        for user_card, card, token, rarity in cards_data:
            cards_received.append({
                "user_card_id": user_card.id,
                "card_id": card.id,
                "token_symbol": token.symbol,
                "token_name": token.name,
                "token_image_url": token.image_url,
                "rarity_name": rarity.name,
                "rarity_color": rarity.color,
                "design_type": card.design_type,
                "rendered_image_url": card.rendered_image_url
            })
        
        return {
            "pack_opening_id": pack_opening.id,
            "pack_type_name": pack_type.name,
            "opened_at": pack_opening.opened_at.isoformat(),
            "cards_received": cards_received
        }

    async def _get_opening_cards(
        self, 
        pack_opening_id: int, 
        db: AsyncSession
    ) -> List[Dict]:
        """Get cards received from a specific pack opening"""
        try:
            from sqlalchemy import text
            
            query = text("""
                SELECT 
                    uc.id as user_card_id,
                    acs.card_id,
                    acs.token_symbol,
                    acs.token_name,
                    acs.token_image_url,
                    acs.rarity_name,
                    acs.rarity_color,
                    acs.design_type,
                    acs.rendered_image_url
                FROM user_cards uc
                JOIN active_cards_with_score acs ON uc.card_id = acs.card_id
                WHERE uc.pack_opening_id = :pack_opening_id
                ORDER BY acs.rarity_name DESC, acs.token_symbol ASC
            """)
            
            result = await db.execute(query, {"pack_opening_id": pack_opening_id})
            rows = result.fetchall()
            
            cards = []
            for row in rows:
                cards.append({
                    "user_card_id": row.user_card_id,
                    "card_id": row.card_id,
                    "token_symbol": row.token_symbol,
                    "token_name": row.token_name,
                    "token_image_url": row.token_image_url,
                    "rarity_name": row.rarity_name,
                    "rarity_color": row.rarity_color,
                    "design_type": row.design_type,
                    "rendered_image_url": row.rendered_image_url
                })
            
            return cards
            
        except Exception as e:
            logger.error(f"Error getting cards for opening {pack_opening_id}: {e}")
            return []


# Singleton instance
pack_opening_service = PackOpeningService()