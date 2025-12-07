import asyncio

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import text, select
from models.database import AsyncSessionLocal as async_session, async_engine
from models.rarity_models import Rarity
from models.token_models import Token, TokenPrice
from models.card_models import Card
from models.pack_models import PackType
from models.pack_probability_models import PackRarityConfig, CardWeight
from models.tournament_models import Tournament, TournamentStatus
from models.user_models import User
from models.user_pack_models import UserPack, PackOpening
from models.user_card_models import UserCard
from models.tournament_deck_models import TournamentDeck, TournamentPrizeConfig, TournamentResult
from models.reward_models import RewardType, UserReward
from models.audit_models import AuditLog

class DatabaseIntegrityTest:
    def __init__(self):
        self.test_data = {}
        
    async def cleanup(self):
        """Очистка тестовых данных"""
        async with async_session() as session:
            try:
                # Удаляем в обратном порядке зависимостей
                await session.execute(text("DELETE FROM user_rewards WHERE user_id IN (SELECT id FROM users WHERE nickname LIKE 'test_%')"))
                await session.execute(text("DELETE FROM audit_logs WHERE user_id IN (SELECT id FROM users WHERE nickname LIKE 'test_%')"))
                await session.execute(text("DELETE FROM tournament_results WHERE tournament_id IN (SELECT id FROM tournaments WHERE tournament_number = 999)"))
                await session.execute(text("DELETE FROM tournament_prize_config WHERE tournament_id IN (SELECT id FROM tournaments WHERE tournament_number = 999)"))
                await session.execute(text("DELETE FROM tournament_decks WHERE tournament_id IN (SELECT id FROM tournaments WHERE tournament_number = 999)"))
                await session.execute(text("DELETE FROM user_cards WHERE user_id IN (SELECT id FROM users WHERE nickname LIKE 'test_%')"))
                await session.execute(text("DELETE FROM pack_openings WHERE user_id IN (SELECT id FROM users WHERE nickname LIKE 'test_%')"))
                await session.execute(text("DELETE FROM user_packs WHERE user_id IN (SELECT id FROM users WHERE nickname LIKE 'test_%')"))
                await session.execute(text("DELETE FROM card_weights WHERE card_id IN (SELECT id FROM cards WHERE token_id IN (SELECT id FROM tokens WHERE symbol = 'TEST'))"))
                await session.execute(text("DELETE FROM pack_rarity_configs WHERE pack_type_id IN (SELECT id FROM pack_types WHERE name LIKE 'Test%')"))
                await session.execute(text("DELETE FROM cards WHERE token_id IN (SELECT id FROM tokens WHERE symbol = 'TEST')"))
                await session.execute(text("DELETE FROM pack_types WHERE name LIKE 'Test%'"))
                await session.execute(text("DELETE FROM tournaments WHERE tournament_number = 999"))
                await session.execute(text("DELETE FROM users WHERE nickname LIKE 'test_%'"))
                await session.execute(text("DELETE FROM token_prices WHERE token_id IN (SELECT id FROM tokens WHERE symbol = 'TEST')"))
                await session.execute(text("DELETE FROM tokens WHERE symbol = 'TEST'"))
                await session.execute(text("DELETE FROM reward_types WHERE name LIKE 'Test%'"))
                await session.execute(text("DELETE FROM rarities WHERE name LIKE 'test_%'"))
                
                await session.commit()
                print("✅ Test data cleaned up")
            except Exception as e:
                await session.rollback()
                print(f"❌ Cleanup failed: {e}")

    async def create_test_rarity(self):
        """Создать тестовую редкость"""
        async with async_session() as session:
            rarity = Rarity(
                name="test_common",
                description="Test common rarity",
                score_bonus=10,
                color="#00FF00"
            )
            session.add(rarity)
            await session.commit()
            await session.refresh(rarity)
            self.test_data['rarity'] = rarity
            print(f"✅ Created rarity: {rarity.name}")
            return rarity

    async def create_test_token(self):
        """Создать тестовый токен"""
        async with async_session() as session:
            token = Token(
                name="Test Coin",
                symbol="TEST",
                weight=5,
                image_url="https://example.com/test.png"
            )
            session.add(token)
            await session.commit()
            await session.refresh(token)
            self.test_data['token'] = token
            print(f"✅ Created token: {token.symbol}")
            return token

    async def create_test_token_price(self, token):
        """Создать цену токена"""
        async with async_session() as session:
            price = TokenPrice(
                token_id=token.id,
                price=Decimal("50000.12345678"),
                market_cap=1000000000,
                change_24h=Decimal("2.5")
            )
            session.add(price)
            await session.commit()
            await session.refresh(price)
            print(f"✅ Created token price: ${price.price}")
            return price

    async def create_test_card(self, token, rarity):
        """Создать тестовую карту"""
        async with async_session() as session:
            card = Card(
                token_id=token.id,
                rarity_id=rarity.id,
                design_type="test_classic",
                background_image_url="https://example.com/card_bg.png"
            )
            session.add(card)
            await session.commit()
            await session.refresh(card)
            self.test_data['card'] = card
            print(f"✅ Created card: ID {card.id}")
            return card

    async def create_test_pack_type(self):
        """Создать тип пака"""
        async with async_session() as session:
            pack_type = PackType(
                name="Test Standard Pack",
                description="Test pack for integrity testing",
                image_url="https://example.com/pack.png",
                header_image_url="https://example.com/pack_header.png",
                cards_per_pack=5,
                price=Decimal("9.99"),
                currency="USD",
                supply=1000,
                available_from=datetime.utcnow(),
                available_until=datetime.utcnow() + timedelta(days=30)
            )
            session.add(pack_type)
            await session.commit()
            await session.refresh(pack_type)
            self.test_data['pack_type'] = pack_type
            print(f"✅ Created pack type: {pack_type.name}")
            return pack_type

    async def create_pack_probability(self, pack_type, rarity):
        """Создать конфигурацию редкости для пака"""
        async with async_session() as session:
            config = PackRarityConfig(
                pack_type_id=pack_type.id,
                rarity_id=rarity.id,
                drop_rate=Decimal("0.8000")  # 80%
            )
            session.add(config)
            await session.commit()
            print("✅ Created pack rarity config")
            return config

    async def create_card_weight(self, card):
        """Создать вес карты"""
        async with async_session() as session:
            weight = CardWeight(
                card_id=card.id,
                base_weight=Decimal("1.0000"),
                current_multiplier=Decimal("1.2000")
            )
            session.add(weight)
            await session.commit()
            print("✅ Created card weight")
            return weight

    async def create_test_user(self):
        """Создать тестового пользователя"""
        async with async_session() as session:
            user = User(
                wallet_address="0x1234567890123456789012345678901234567890",
                nickname="test_user_001",
                referral_route="TEST001",
                avatar_url="https://example.com/avatar.png"
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            self.test_data['user'] = user
            print(f"✅ Created user: {user.nickname}")
            return user

    async def create_test_tournament(self):
        """Создать тестовый турнир"""
        async with async_session() as session:
            tournament = Tournament(
                tournament_number=999,
                status=TournamentStatus.REGISTRATION,
                start_date=datetime.utcnow() + timedelta(days=1),
                end_date=datetime.utcnow() + timedelta(days=8),
                weight_limit=30
            )
            session.add(tournament)
            await session.commit()
            await session.refresh(tournament)
            self.test_data['tournament'] = tournament
            print(f"✅ Created tournament: #{tournament.tournament_number}")
            return tournament

    async def create_reward_type(self):
        """Создать тип награды"""
        async with async_session() as session:
            reward_type = RewardType(
                name="Test Tournament Prize",
                description="Test prize for winners",
                reward_category="tournament_prize",
                default_amount=Decimal("100.0"),
                currency_type="TOKENS"
            )
            session.add(reward_type)
            await session.commit()
            await session.refresh(reward_type)
            self.test_data['reward_type'] = reward_type
            print("✅ Created reward type")
            return reward_type

    async def test_full_pack_opening_flow(self, user, pack_type, card):
        """Тест полного флоу открытия пака"""
        async with async_session() as session:
            # Создаем пак пользователю
            user_pack = UserPack(
                user_id=user.id,
                pack_type_id=pack_type.id,
                source="purchase"
            )
            session.add(user_pack)
            await session.commit()
            await session.refresh(user_pack)
            print("✅ Created user pack")

            # Открываем пак
            pack_opening = PackOpening(
                user_id=user.id,
                pack_id=user_pack.id,
                cards_count=1,
                transaction_hash="0xtest123456789"
            )
            session.add(pack_opening)
            await session.commit()
            await session.refresh(pack_opening)
            print("✅ Created pack opening")

            # Добавляем карту пользователю
            user_card = UserCard(
                user_id=user.id,
                card_id=card.id,
                pack_opening_id=pack_opening.id,
                source="pack_opening"
            )
            session.add(user_card)
            await session.commit()
            print("✅ Created user card")

            # Обновляем статус пака
            user_pack.is_opened = True
            await session.commit()
            print("✅ Updated pack status")

            return user_pack, pack_opening, user_card

    async def test_tournament_flow(self, user, tournament, card, reward_type):
        """Тест турнирного флоу"""
        async with async_session() as session:
            # Создаем колоду
            deck = TournamentDeck(
                tournament_id=tournament.id,
                user_id=user.id,
                deck_composition=[{"card_id": card.id, "quantity": 3}],
                deck_hash="hash123456789"
            )
            session.add(deck)
            await session.commit()
            await session.refresh(deck)
            print("✅ Created tournament deck")

            # Создаем призовую конфигурацию
            prize_config = TournamentPrizeConfig(
                tournament_id=tournament.id,
                position_from=1,
                position_to=1,
                reward_type_id=reward_type.id,
                reward_amount=Decimal("500.0")
            )
            session.add(prize_config)
            await session.commit()
            print("✅ Created prize config")

            # Создаем результат турнира
            result = TournamentResult(
                tournament_id=tournament.id,
                tournament_deck_id=deck.id,
                final_position=1
            )
            session.add(result)
            await session.commit()
            await session.refresh(result)
            print("✅ Created tournament result")

            # Создаем награду
            reward = UserReward(
                user_id=user.id,
                reward_type_id=reward_type.id,
                amount=Decimal("500.0"),
                tournament_result_id=result.id
            )
            session.add(reward)
            await session.commit()
            print("✅ Created user reward")

            return deck, result, reward

    async def create_audit_log(self, user, card):
        """Создать аудит лог"""
        async with async_session() as session:
            audit = AuditLog(
                user_id=user.id,
                action_type="pack_open",
                entity_type="card",
                entity_id=card.id,
                old_data=None,
                new_data={"card_id": card.id, "obtained": True},
                ip_address="127.0.0.1"
            )
            session.add(audit)
            await session.commit()
            print("✅ Created audit log")
            return audit

    async def test_view_query(self, user):
        """Тест представления user_balances_view"""
        async with async_session() as session:
            result = await session.execute(
                text("SELECT * FROM user_balances_view WHERE user_id = :user_id"),
                {"user_id": user.id}
            )
            balances = result.fetchall()
            print(f"✅ User balances view returned {len(balances)} records")
            for balance in balances:
                print(f"   - Category: {balance.reward_category}, Available: {balance.available_balance}, Pending: {balance.pending_balance}")

    async def verify_foreign_keys(self):
        """Проверка всех внешних ключей"""
        async with async_session() as session:
            fk_queries = [
                "SELECT COUNT(*) FROM cards c JOIN tokens t ON c.token_id = t.id",
                "SELECT COUNT(*) FROM cards c JOIN rarities r ON c.rarity_id = r.id", 
                "SELECT COUNT(*) FROM user_cards uc JOIN users u ON uc.user_id = u.id",
                "SELECT COUNT(*) FROM user_cards uc JOIN cards c ON uc.card_id = c.id",
                "SELECT COUNT(*) FROM user_packs up JOIN pack_types pt ON up.pack_type_id = pt.id",
                "SELECT COUNT(*) FROM tournament_decks td JOIN tournaments t ON td.tournament_id = t.id",
                "SELECT COUNT(*) FROM user_rewards ur JOIN reward_types rt ON ur.reward_type_id = rt.id"
            ]
            
            for query in fk_queries:
                try:
                    result = await session.execute(text(query))
                    count = result.scalar()
                    print(f"✅ FK Check: {query.split('FROM')[1].split('JOIN')[0].strip()} - {count} valid records")
                except Exception as e:
                    print(f"❌ FK Check failed: {e}")

    async def run_all_tests(self):
        """Запуск всех тестов"""
        try:
            print("🚀 Starting database integrity tests...\n")
            
            # Очистка перед тестами
            await self.cleanup()
            
            # Создание базовых данных
            print("📦 Creating base test data...")
            rarity = await self.create_test_rarity()
            token = await self.create_test_token()
            await self.create_test_token_price(token)
            card = await self.create_test_card(token, rarity)
            await self.create_card_weight(card)
            
            pack_type = await self.create_test_pack_type()
            await self.create_pack_probability(pack_type, rarity)
            
            user = await self.create_test_user()
            tournament = await self.create_test_tournament()
            reward_type = await self.create_reward_type()
            
            print("\n🔄 Testing complex flows...")
            # Тест открытия паков
            await self.test_full_pack_opening_flow(user, pack_type, card)
            
            # Тест турниров
            await self.test_tournament_flow(user, tournament, card, reward_type)
            
            # Аудит лог
            await self.create_audit_log(user, card)
            
            print("\n🔍 Testing queries and relationships...")
            # Тест представления
            await self.test_view_query(user)
            
            # Проверка внешних ключей
            await self.verify_foreign_keys()
            
            print("\n✅ All integrity tests passed!")
            
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            raise
        finally:
            # Очистка после тестов
            print("\n🧹 Cleaning up test data...")
            await self.cleanup()

# Функция для запуска
async def run_integrity_test():
    test = DatabaseIntegrityTest()
    await test.run_all_tests()

if __name__ == "__main__":
    asyncio.run(run_integrity_test())