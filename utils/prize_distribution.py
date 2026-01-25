import math
from typing import List, Tuple

def distribute_prizes(pool: float, total_players: int, verbose: bool = False) -> List[Tuple[int, float]]:
    """
    Распределяет призовой фонд между участниками.
    
    Args:
        pool: Общий призовой фонд
        total_players: Общее количество участников турнира
        verbose: Выводить ли логи
    
    Returns:
        List[(position, prize_amount)] - список призов для каждой позиции
    """
    winners = int(total_players * 0.33)
    if winners < 3:
        winners = min(3, total_players)
    
    prizes = []
    remaining_pool = pool
    position = 1
    remaining_winners = winners
    
    if verbose:
        print(f"\n=== Распределение призов ===")
        print(f"Призовой фонд: {pool}")
        print(f"Участников: {total_players}")
        print(f"Призёров (33%): {winners}\n")
    
    # Масштабирование для топов
    scale_factor = max(0.6, 1 - (winners / 2000))
    
    # Топ-10 индивидуально (более плавное убывание)
    top_base_percents = [
        0.14,   # 1 место
        0.105,  # 2 место (75% от первого)
        0.085,  # 3 место
        0.07,   # 4 место
        0.057,  # 5 место
        0.047,  # 6 место
        0.039,  # 7 место
        0.033,  # 8 место
        0.028,  # 9 место
        0.024   # 10 место
    ]
    
    for i, base_percent in enumerate(top_base_percents):
        if remaining_winners <= 0:
            break
        percent = base_percent * scale_factor
        prize = int(pool * percent)
        prizes.append((position, prize))
        remaining_pool -= prize
        remaining_winners -= 1
        if verbose:
            print(f"Место {position}: {prize}")
        position += 1
    
    if verbose:
        print()
    
    # Дальше группы с плавным убыванием
    if remaining_winners > 0:
        # Размеры групп (процент от winners)
        group_sizes_pct = [0.02, 0.03, 0.05, 0.08, 0.12, 0.20]
        groups = []
        temp_remaining = remaining_winners
        
        for pct in group_sizes_pct:
            if temp_remaining <= 0:
                break
            size = max(1, int(winners * pct))
            size = min(size, temp_remaining)
            groups.append(size)
            temp_remaining -= size
        
        # Последняя группа - все оставшиеся
        if temp_remaining > 0:
            groups.append(temp_remaining)
        
        # ПЛАНИРУЕМ призы для всех групп
        decay_rate = 0.75
        first_group_prize = int(prizes[-1][1] * 0.85)
        
        planned_prizes = []
        for i, group_size in enumerate(groups):
            prize_per_person = int(first_group_prize * (decay_rate ** i))
            if prize_per_person < 1:
                prize_per_person = 1
            planned_prizes.append((group_size, prize_per_person))
        
        # Считаем ОБЩУЮ сумму по плану
        total_planned = sum(size * prize for size, prize in planned_prizes)
        
        # Если план превышает бюджет - масштабируем ВСЕ призы пропорционально
        if total_planned > remaining_pool:
            scale = remaining_pool / total_planned
            planned_prizes = [(size, max(1, int(prize * scale))) for size, prize in planned_prizes]
        
        # Теперь выдаём по плану
        for group_size, prize_per_person in planned_prizes:
            start_pos = position
            actual_total = 0
            
            for _ in range(group_size):
                prizes.append((position, prize_per_person))
                actual_total += prize_per_person
                position += 1
                remaining_winners -= 1
            
            end_pos = position - 1
            remaining_pool -= actual_total
            
            if verbose:
                if start_pos == end_pos:
                    print(f"Место {start_pos}: {prize_per_person} (всего: {actual_total})")
                else:
                    print(f"Места {start_pos}-{end_pos}: по {prize_per_person} каждому (всего: {actual_total})")
    
    # Распределяем остаток на топ-5 (пропорционально их текущим призам)
    if remaining_pool > 0:
        if verbose:
            print(f"\nРаспределение остатка ({remaining_pool}):")
        top_count = min(5, len(prizes))
        weights = [5, 3, 2, 1, 1][:top_count]
        total_weight = sum(weights)
        original_remainder = remaining_pool
        
        for i in range(top_count):
            pos, old_prize = prizes[i]
            if i == top_count - 1:
                share = remaining_pool
            else:
                share = int((weights[i] / total_weight) * original_remainder)
            
            if share > 0:
                prizes[i] = (pos, old_prize + share)
                remaining_pool -= share
                if verbose:
                    print(f"  Место {pos}: +{share} (было {old_prize}, стало {old_prize + share})")
    
    total_distributed = sum(p for _, p in prizes)
    if verbose:
        print(f"\nВсего распределено: {total_distributed} из {pool}")
        print(f"Осталось: {pool - total_distributed}\n")
    
    return prizes