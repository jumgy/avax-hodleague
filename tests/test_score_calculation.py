# tests/test_score_calculation.py

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
from tabulate import tabulate

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.database import DatabaseSession
from services.score_service import ScoreService
from sqlalchemy import select, and_, func, delete
from models.token_models import Token, TokenPrice
from models.tournament_models import Tournament, TournamentTokenSnapshot, TournamentStatus
from models.token_score_models import TokenScore


# SAFE TOKENS - не были затронуты предыдущим тестом
SAFE_TOKEN_SYMBOLS = ['ENA', 'LDO', 'ZEC', 'FET', 'APT', 'KCS', 'IOTA', 'SPX', 'KAS', 'FLOKI']


async def create_test_tournament(db, start_index: int = 0, period_hours: int = 72):
    """
    Create a test tournament using historical data.
    Uses only SAFE tokens that weren't affected by previous tests.
    
    Args:
        db: Database session
        start_index: Which record to use as tournament start (0 = earliest)
        period_hours: How many records to use as "hours" (72 = 3 days)
    """
    print(f"\n{'='*80}")
    print(f"🧪 ТЕСТ РАСЧЕТА СКОРОВ: {period_hours} часов (записей)")
    print(f"{'='*80}\n")
    
    # Get SAFE tokens (not affected by previous test)
    result = await db.execute(
        select(Token)
        .where(
            and_(
                Token.is_active == True,
                Token.symbol.in_(SAFE_TOKEN_SYMBOLS)
            )
        )
        .order_by(Token.symbol)
    )
    test_tokens = result.scalars().all()
    
    print(f"📊 Выбрано БЕЗОПАСНЫХ токенов для теста: {len(test_tokens)}")
    for token in test_tokens:
        print(f"   • {token.symbol:6} - {token.name}")
    
    # Get all price records for these tokens
    token_ids = [t.id for t in test_tokens]
    
    result = await db.execute(
        select(TokenPrice)
        .where(TokenPrice.token_id.in_(token_ids))
        .order_by(TokenPrice.timestamp.asc())
    )
    all_prices = result.scalars().all()
    
    # Store original prices for restoration after test
    original_prices = []
    for price in all_prices:
        original_prices.append({
            'token_id': price.token_id,
            'price': price.price,
            'market_cap': price.market_cap,
            'change_24h': price.change_24h,
            'sources_count': price.sources_count,
            'timestamp': price.timestamp
        })
    
    # Group by token
    prices_by_token = {}
    for price in all_prices:
        if price.token_id not in prices_by_token:
            prices_by_token[price.token_id] = []
        prices_by_token[price.token_id].append(price)
    
    # Check data availability
    print(f"\n📈 Данные по ценам:")
    for token in test_tokens:
        count = len(prices_by_token.get(token.id, []))
        print(f"   • {token.symbol:6}: {count} записей")
    
    # Select test period
    min_records = min(len(prices_by_token[tid]) for tid in token_ids)
    
    if min_records < start_index + period_hours:
        print(f"\n⚠️  Недостаточно данных! Доступно: {min_records}, нужно: {start_index + period_hours}")
        period_hours = min_records - start_index - 1
        print(f"   Уменьшаю период до {period_hours} часов")
    
    print(f"\n🎯 Период теста:")
    print(f"   • Начало: запись #{start_index}")
    print(f"   • Конец: запись #{start_index + period_hours - 1}")
    print(f"   • Всего 'часов': {period_hours}")
    
    # Get snapshot prices (at start_index)
    snapshots = {}
    snapshot_time = None
    
    for token_id, prices in prices_by_token.items():
        snapshot_price = prices[start_index]
        snapshots[token_id] = snapshot_price
        if snapshot_time is None:
            snapshot_time = snapshot_price.timestamp
    
    print(f"\n📸 Snapshot время: {snapshot_time}")
    print(f"   Snapshot цены:")
    for token in test_tokens:
        snap = snapshots[token.id]
        print(f"   • {token.symbol:6}: ${snap.price:,.4f}")
    
    # Get max tournament_number
    result = await db.execute(
        select(func.max(Tournament.tournament_number))
    )
    max_number = result.scalar() or 0
    
    # Create temporary tournament
    tournament = Tournament(
        tournament_number=max_number + 999,  # High number to avoid conflicts
        status=TournamentStatus.ONGOING,
        start_date=snapshot_time,
        end_date=snapshot_time,
        gameplay_start_date=snapshot_time,
        weight_limit=30
    )
    db.add(tournament)
    await db.flush()
    
    # Create snapshots
    for token_id, snapshot_price in snapshots.items():
        snap = TournamentTokenSnapshot(
            tournament_id=tournament.id,
            token_id=token_id,
            snapshot_price=snapshot_price.price,
            snapshot_time=snapshot_time
        )
        db.add(snap)
    
    await db.commit()
    
    return tournament, test_tokens, prices_by_token, original_prices, start_index, period_hours


async def simulate_and_calculate_scores(
    db, 
    tournament, 
    test_tokens, 
    prices_by_token,
    original_prices,
    start_index, 
    period_hours
):
    """
    Simulate tournament hour by hour and calculate scores using ScoreService.
    """
    score_service = ScoreService(db)
    results = []
    token_ids = [t.id for t in test_tokens]
    
    # ⭐ NEW: Extract ALL data from objects BEFORE any DB operations
    tournament_id = tournament.id
    
    # Create complete lookup with all token data
    tokens_data = {}
    for t in test_tokens:
        tokens_data[t.id] = {
            'id': t.id,
            'symbol': t.symbol,
            'name': t.name
        }
    
    print(f"\n⏳ Симуляция {period_hours} часов...\n")

    try:
        for hour in range(period_hours):
            record_index = start_index + hour
            
            # Step 1: Clear existing prices for test tokens
            await db.execute(
                delete(TokenPrice).where(TokenPrice.token_id.in_(token_ids))
            )
            
            # Step 2: Add prices from start_index to current hour
            prices_to_add = []
            for token_id in token_ids:
                prices = prices_by_token[token_id]
                
                for i in range(start_index, record_index + 1):
                    if i < len(prices):
                        original_price = prices[i]
                        new_price = TokenPrice(
                            token_id=original_price.token_id,
                            price=original_price.price,
                            market_cap=original_price.market_cap,
                            change_24h=original_price.change_24h,
                            sources_count=original_price.sources_count,
                            timestamp=original_price.timestamp
                        )
                        prices_to_add.append(new_price)
            
            if prices_to_add:
                db.add_all(prices_to_add)
                await db.commit()
            
            # Step 3: Call ScoreService
            try:
                scores_count = await score_service.calculate_and_store_scores(tournament_id)
                
                # Get calculated scores
                scores = await score_service.get_latest_scores(tournament_id)
                
                # Collect results
                for score in scores:
                    # Extract ALL values immediately to avoid lazy loading
                    token_id = score.token_id
                    current_price = float(score.current_price)
                    snapshot_price = float(score.snapshot_price)
                    calculated_score = float(score.calculated_score)
                    price_change_percent = float(score.price_change_percent)
                    
                    # Get token data from our pre-loaded dict
                    token_data = tokens_data[token_id]
                    
                    # Calculate hour change
                    if hour > 0:
                        prev_price = float(prices_by_token[token_id][start_index + hour - 1].price)
                        hour_change = ((current_price - prev_price) / prev_price) * 100
                    else:
                        hour_change = 0
                    
                    results.append({
                        'hour': hour,
                        'symbol': token_data['symbol'],  # ⭐ Use pre-loaded data
                        'price': current_price,
                        'snapshot_price': snapshot_price,
                        'hour_change_pct': float(hour_change),
                        'period_change_pct': price_change_percent,
                        'score': calculated_score,
                    })
                
                # Progress indicator
                if (hour + 1) % 10 == 0:
                    print(f"   ✓ Обработано {hour + 1}/{period_hours} часов")
            
            except Exception as e:
                print(f"❌ Ошибка на часе {hour}: {e}")
                import traceback
                traceback.print_exc()
                break
    
    finally:
        # CRITICAL: Restore original prices after test
        print(f"\n🔄 Восстановление оригинальных цен...")
        
        # Clear test prices
        await db.execute(
            delete(TokenPrice).where(TokenPrice.token_id.in_(token_ids))
        )
        
        # Restore original prices
        restored_prices = []
        for price_data in original_prices:
            restored_price = TokenPrice(**price_data)
            restored_prices.append(restored_price)
        
        if restored_prices:
            db.add_all(restored_prices)
            await db.commit()
            print(f"   ✓ Восстановлено {len(restored_prices)} записей цен")
    
    return results


def print_results(results, test_tokens):
    """
    Print results in a nice table format.
    """
    if not results:
        print("\n⚠️  Нет результатов для отображения")
        return
    
    print(f"\n{'='*120}")
    print(f"📊 РЕЗУЛЬТАТЫ РАСЧЕТА СКОРОВ")
    print(f"{'='*120}\n")
    
    # Group by token
    by_token = {}
    for r in results:
        symbol = r['symbol']
        if symbol not in by_token:
            by_token[symbol] = []
        by_token[symbol].append(r)
    
    # Print each token
    for token_symbol in sorted(by_token.keys()):
        token_results = by_token[token_symbol]
        
        print(f"\n🪙 {token_symbol}")
        print(f"{'─'*120}")
        
        # Sample: every 6th hour (to fit in terminal)
        sample_hours = [0, 6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 71]
        
        table_data = []
        for r in token_results:
            if r['hour'] in sample_hours or r['hour'] == len(token_results) - 1:
                table_data.append([
                    f"Hour {r['hour']:2d}",
                    f"${r['price']:>12,.4f}",
                    f"{r['hour_change_pct']:>7.2f}%",
                    f"{r['period_change_pct']:>8.2f}%",
                    f"{r['score']:>6.0f}",
                ])
        
        headers = ["Time", "Price", "Δ Hour", "Δ Period", "Score"]
        print(tabulate(table_data, headers=headers, tablefmt="simple"))
    
    # Summary statistics
    print(f"\n{'='*120}")
    print(f"📈 ИТОГОВАЯ СТАТИСТИКА")
    print(f"{'='*120}\n")
    
    summary_data = []
    for token_symbol in sorted(by_token.keys()):
        token_results = by_token[token_symbol]
        last = token_results[-1]
        
        scores = [r['score'] for r in token_results]
        
        summary_data.append([
            token_symbol,
            f"${last['snapshot_price']:,.4f}",
            f"${last['price']:,.4f}",
            f"{last['period_change_pct']:>8.2f}%",
            f"{min(scores):.0f}",
            f"{max(scores):.0f}",
            f"{last['score']:.0f}",
        ])
    
    headers = ["Token", "Start Price", "End Price", "Total Δ%", "Min Score", "Max Score", "Final Score"]
    print(tabulate(summary_data, headers=headers, tablefmt="grid"))


async def main():
    """
    Main test function.
    """
    async with DatabaseSession() as db:
        # Create test tournament
        tournament, test_tokens, prices_by_token, original_prices, start_index, period_hours = await create_test_tournament(
            db,
            start_index=100,
            period_hours=72
        )
        
        tournament_id = tournament.id
        
        # Simulate and calculate
        results = await simulate_and_calculate_scores(
            db,
            tournament,
            test_tokens,
            prices_by_token,
            original_prices,
            start_index,
            period_hours
        )
        
        # Print results
        print_results(results, test_tokens)
        
        # Cleanup
        print(f"\n🧹 Очистка тестовых данных...")
        

        await db.execute(
            delete(TokenScore).where(TokenScore.tournament_id == tournament_id)
        )
        
        # Delete snapshots
        await db.execute(
            delete(TournamentTokenSnapshot).where(TournamentTokenSnapshot.tournament_id == tournament_id)
        )
        
        # Delete tournament
        await db.execute(
            delete(Tournament).where(Tournament.id == tournament_id)
        )
        
        await db.commit()
        
        print(f"✅ Тест завершен! Оригинальные данные восстановлены.\n")


if __name__ == "__main__":
    asyncio.run(main())