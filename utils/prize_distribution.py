import math
from typing import List, Tuple

def distribute_prizes(pool: float, total_players: int, verbose: bool = False) -> List[Tuple[int, float]]:
    """
    Distribute the prize pool among participants.

    Args:
        pool: Total prize pool.
        total_players: Total number of tournament participants.
        verbose: Whether to print logs.

    Returns:
        List of (position, prize_amount) for each position.
    """
    winners = int(total_players * 0.33)
    if winners < 3:
        winners = min(3, total_players)
    
    prizes = []
    remaining_pool = pool
    position = 1
    remaining_winners = winners
    
    if verbose:
        print(f"\n=== Prize distribution ===")
        print(f"Prize pool: {pool}")
        print(f"Participants: {total_players}")
        print(f"Winners (33%): {winners}\n")
    
    # Scale factor for top places.
    scale_factor = max(0.6, 1 - (winners / 2000))
    
    # Top 10 individually (smoother decay).
    top_base_percents = [
        0.14,   # 1st
        0.105,  # 2nd (75% of 1st)
        0.085,  # 3rd
        0.07,   # 4th
        0.057,  # 5th
        0.047,  # 6th
        0.039,  # 7th
        0.033,  # 8th
        0.028,  # 9th
        0.024   # 10th
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
            print(f"Position {position}: {prize}")
        position += 1
    
    if verbose:
        print()
    
    # Remaining groups with smooth decay.
    if remaining_winners > 0:
        # Group sizes (percent of winners).
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
        
        # Last group gets all remaining.
        if temp_remaining > 0:
            groups.append(temp_remaining)
        
        # Plan prizes for all groups.
        decay_rate = 0.75
        first_group_prize = int(prizes[-1][1] * 0.85)
        
        planned_prizes = []
        for i, group_size in enumerate(groups):
            prize_per_person = int(first_group_prize * (decay_rate ** i))
            if prize_per_person < 1:
                prize_per_person = 1
            planned_prizes.append((group_size, prize_per_person))
        
        # Total planned amount.
        total_planned = sum(size * prize for size, prize in planned_prizes)
        
        # If plan exceeds budget, scale all prizes proportionally.
        if total_planned > remaining_pool:
            scale = remaining_pool / total_planned
            planned_prizes = [(size, max(1, int(prize * scale))) for size, prize in planned_prizes]
        
        # Assign prizes according to plan.
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
                    print(f"Position {start_pos}: {prize_per_person} (total: {actual_total})")
                else:
                    print(f"Positions {start_pos}-{end_pos}: {prize_per_person} each (total: {actual_total})")
    
    # Distribute remainder to top 5 (proportional to their current prizes).
    if remaining_pool > 0:
        if verbose:
            print(f"\nRemainder distribution ({remaining_pool}):")
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
                    print(f"  Position {pos}: +{share} (was {old_prize}, now {old_prize + share})")
    
    total_distributed = sum(p for _, p in prizes)
    if verbose:
        print(f"\nTotal distributed: {total_distributed} of {pool}")
        print(f"Remaining: {pool - total_distributed}\n")
    
    return prizes