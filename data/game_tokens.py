"""Fixed list of 30 game tokens with their weights for tournament play"""
import random

# Базовые группы токенов с диапазонами весов
TOKEN_WEIGHT_RANGES = {
    'tier_1': {'tokens': ['BTC', 'ETH', 'BNB'], 'weight_range': (9, 10)},
    'tier_2': {'tokens': ['SOL', 'XRP', 'DOGE'], 'weight_range': (8, 9)},
    'tier_3': {'tokens': ['ADA', 'TRX', 'AVAX'], 'weight_range': (6, 8)},
    'tier_4': {'tokens': ['HYPE', 'POL', 'LDO'], 'weight_range': (5, 7)},
    'tier_5': {'tokens': ['FET', 'PUMP', 'APT'], 'weight_range': (4, 6)},
    'tier_6': {'tokens': ['DASH', 'XTZ', 'ZEC'], 'weight_range': (3, 5)},
    'tier_7': {'tokens': ['KCS', 'ENA', 'KAS'], 'weight_range': (2, 4)},
    'tier_8': {'tokens': ['AR', 'SAND', 'DCR'], 'weight_range': (1, 3)},
    'tier_9': {'tokens': ['FLR', 'WLFI', 'SPX'], 'weight_range': (1, 2)},
    'tier_10': {'tokens': ['DEXE', 'KAIA', 'M'], 'weight_range': (1, 2)}
}

def generate_random_token_weights():
    """Генерирует случайные веса токенов, обеспечивая по 3 токена каждого веса"""
    weights = {}
    
    # Создаем список весов: по 3 штуки каждого веса от 1 до 10
    available_weights = []
    for weight in range(1, 11):
        available_weights.extend([weight] * 3)
    
    # Перемешиваем веса
    random.shuffle(available_weights)
    
    # Собираем все токены в один список
    all_tokens = []
    token_ranges = {}
    
    for tier_info in TOKEN_WEIGHT_RANGES.values():
        for token in tier_info['tokens']:
            all_tokens.append(token)
            token_ranges[token] = tier_info['weight_range']
    
    # Распределяем веса с учетом диапазонов
    used_weights = []
    
    for token in all_tokens:
        min_weight, max_weight = token_ranges[token]
        
        # Найдем подходящий вес из доступных
        suitable_weights = [w for w in available_weights if min_weight <= w <= max_weight and w not in used_weights]
        
        # Если нет подходящих весов в диапазоне, расширяем поиск
        if not suitable_weights:
            suitable_weights = [w for w in available_weights if w not in used_weights]
        
        # Выбираем случайный подходящий вес
        if suitable_weights:
            chosen_weight = random.choice(suitable_weights)
            weights[token] = chosen_weight
            used_weights.append(chosen_weight)
            available_weights.remove(chosen_weight)
    
    return weights

# Генерируем веса при импорте модуля
TOKEN_WEIGHTS = generate_random_token_weights()
GAME_TOKENS = list(TOKEN_WEIGHTS.keys())

def regenerate_weights():
    """Перегенерирует веса токенов"""
    global TOKEN_WEIGHTS, GAME_TOKENS
    TOKEN_WEIGHTS = generate_random_token_weights()
    GAME_TOKENS = list(TOKEN_WEIGHTS.keys())
    return TOKEN_WEIGHTS

def get_game_tokens_list():
    """Return the list of game token symbols"""
    return GAME_TOKENS

def get_token_weight(symbol):
    """Get weight for a specific token"""
    return TOKEN_WEIGHTS.get(symbol.upper(), 50)  # Default weight if not found

def is_game_token(symbol):
    """Check if symbol is in game tokens"""
    return symbol.upper() in TOKEN_WEIGHTS

def get_all_token_weights():
    """Return all token weights"""
    return TOKEN_WEIGHTS

def validate_deck_weight(selected_tokens):
    """Validate if deck weight is within tournament limits"""
    total_weight = sum(get_token_weight(token) for token in selected_tokens)
    return total_weight, total_weight <= 28

def get_weight_distribution():
    """Get weight distribution statistics"""
    weights = list(TOKEN_WEIGHTS.values())
    return {
        'min_weight': min(weights),
        'max_weight': max(weights),
        'avg_weight': sum(weights) / len(weights),
        'total_tokens': len(weights),
        'tier_1': len([w for w in weights if w >= 80]),  # 80-100
        'tier_2': len([w for w in weights if 60 <= w < 80]),  # 60-79
        'tier_3': len([w for w in weights if 40 <= w < 60]),  # 40-59
        'tier_4': len([w for w in weights if 25 <= w < 40]),  # 25-39
        'tier_5': len([w for w in weights if w < 25])  # < 25
    }
