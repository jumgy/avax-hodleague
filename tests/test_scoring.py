import csv
import math
from decimal import Decimal
from typing import List, Dict

def calculate_mc_factor(market_cap: float, all_market_caps: List[float]) -> float:
    """
    Старая формула: степенная функция от капы
    Крупные токены получают больше, но не так драматично как с логарифмом
    """
    if not all_market_caps or market_cap <= 0:
        return 1.0
    
    # Переводим в миллиарды
    market_cap_billions = market_cap / 1_000_000_000
    
    # 🆕 СТАРАЯ ФОРМУЛА (без асимметрии)
    # Степень 0.15 дает плавный рост
    mc_factor = (market_cap_billions ** 0.12) * 12
    
    return mc_factor

def calculate_scores(tokens: List[Dict]) -> List[Dict]:
    total_tokens = len(tokens)
    all_market_caps = [t['market_cap'] for t in tokens]
    
    all_zero_change = all(t['tournament_change'] == 0 for t in tokens)
    if all_zero_change:
        for token in tokens:
            token['new_score'] = 0
            token['mc_factor'] = 0
            token['raw_score'] = 0
        return tokens
    
    sorted_by_change = sorted(tokens, key=lambda x: (x['tournament_change'], -x['market_cap']), reverse=True)
    for rank, token in enumerate(sorted_by_change, start=1):
        token['change_rank_calc'] = rank
    
    for token in tokens:
        token['activity_rank'] = total_tokens // 2
    
    # Рассчитываем raw scores
    for token in tokens:
        mc_factor = calculate_mc_factor(token['market_cap'], all_market_caps)
        token['mc_factor'] = round(mc_factor, 2)
        
        # Базовые очки от ранга
        rank_points = total_tokens - token['change_rank_calc'] + 1
        weekly_points = rank_points
        activity_points = total_tokens - token['activity_rank'] + 1
        
        # Базовая часть raw_score
        base_raw_score = weekly_points * mc_factor * 4
        
        # ПРЯМОЙ БОНУС ОТ ПРОЦЕНТА РОСТА
        change = token['tournament_change']
        if change > 0:
            # Рост дает бонус
            growth_raw_bonus = (change ** 1.3) * mc_factor * 1.5
        elif change < 0:
            # 🆕 ПАДЕНИЕ ДАЕТ ШТРАФ (симметрично!)
            growth_raw_bonus = (abs(change) ** 1.3) * mc_factor * (-1.5)  # Тот же множитель!
        else:
            growth_raw_bonus = 0
        
        # Activity часть
        activity_raw_score = activity_points * mc_factor * 1
        
        # ИТОГО
        raw_score = max(0, base_raw_score + growth_raw_bonus + activity_raw_score)
        
        token['raw_score'] = raw_score
        token['weekly_points'] = weekly_points
        token['activity_points'] = activity_points
        token['growth_raw_bonus'] = round(growth_raw_bonus, 1)
    
    # После расчета всех raw_scores
    raw_scores = [t['raw_score'] for t in tokens]
    median_raw = sorted(raw_scores)[len(raw_scores) // 2]

    print(median_raw)

    # Хотим, чтобы медиана давала 500 очков
    # median_raw / divider = 500
    # divider = median_raw / 500
    dynamic_divider = median_raw / 400

    print(dynamic_divider)

    # Нормализация
    for token in tokens:
        raw_score = token['raw_score']
        
        if raw_score <= 0:
            final_score = 0
        else:
            final_score = min(int(raw_score / dynamic_divider), 1000)
        
        token['new_score'] = final_score
    
    return tokens

def load_data_from_csv(filename: str) -> List[Dict]:
    """
    Читаем CSV файл
    """
    tokens = []
    with open(filename, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            tokens.append({
                'token_symbol': row['token_symbol'].strip(),
                'tournament_change': float(row['tournament_change']),
                'market_cap': int(row['market_cap']),
                'old_score': float(row['old_score']),
                'change_rank': int(row['change_rank']),
                'mc_rank': int(row['mc_rank'])
            })
    return tokens

def print_results(tokens: List[Dict]):
    """
    Выводим красивую таблицу
    """
    # Сортируем по новому скору
    sorted_tokens = sorted(tokens, key=lambda x: x['new_score'], reverse=True)
    
    print("\n" + "="*140)
    print(f"{'Symbol':<10} | {'Change %':>9} | {'Market Cap':>15} | {'Old Score':>9} | {'New Score':>9} | {'Diff':>6} | {'MC Factor':>10} | {'Raw Score':>10}")
    print("="*140)
    
    for token in sorted_tokens:
        diff = token['new_score'] - token['old_score']
        diff_str = f"{diff:+.0f}"
        
        print(f"{token['token_symbol']:<10} | "
              f"{token['tournament_change']:>9.4f} | "
              f"{token['market_cap']:>15,} | "
              f"{token['old_score']:>9.0f} | "
              f"{token['new_score']:>9.0f} | "
              f"{diff_str:>6} | "
              f"{token['mc_factor']:>10.2f} | "
              f"{token['raw_score']:>10.1f}")
    
    print("="*140)
    print(f"\nTotal tokens: {len(tokens)}")
    print(f"Min raw score: {min(t['raw_score'] for t in tokens):.1f}")
    print(f"Max raw score: {max(t['raw_score'] for t in tokens):.1f}")

if __name__ == '__main__':
    # Читаем данные
    print("Loading data from scores.csv...")
    tokens = load_data_from_csv('./tests/scores.csv')
    
    print(f"Loaded {len(tokens)} tokens")
    
    # Рассчитываем скоры
    print("Calculating scores...")
    tokens_with_scores = calculate_scores(tokens)
    
    # Выводим результаты
    print_results(tokens_with_scores)
    
    # Дополнительная статистика
    print("\n" + "="*60)
    print("TOP 5 BIGGEST DIFFERENCES:")
    print("="*60)
    sorted_by_diff = sorted(tokens_with_scores, key=lambda x: abs(x['new_score'] - x['old_score']), reverse=True)
    for token in sorted_by_diff[:5]:
        diff = token['new_score'] - token['old_score']
        print(f"{token['token_symbol']:<10} | Old: {token['old_score']:>4.0f} | New: {token['new_score']:>4.0f} | Diff: {diff:+6.0f} | Change: {token['tournament_change']:>7.2f}%")