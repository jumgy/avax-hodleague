"""Fixed list of 30 game tokens with their weights for tournament play"""

# Token weights for tournament restrictions (higher weight = stronger/more expensive token)
TOKEN_WEIGHTS = {
    # Вес 10 (3 токена) - Абсолютные короли
    'BTC': 10, 'ETH': 10, 'BNB': 10,
    
    # Вес 9 (3 токена) - Топ экосистемы
    'SOL': 9, 'XRP': 9, 'DOGE': 9,
    
    # Вес 8 (3 токена) - Крупные установленные
    'ADA': 8, 'TRX': 8, 'AVAX': 8,
    
    # Вес 7 (3 токена) - Сильные проекты
    'HYPE': 7, 'POL': 7, 'LDO': 7,
    
    # Вес 6 (3 токена) - Перспективные средние
    'FET': 6, 'PUMP': 6, 'APT': 6,
    
    # Вес 5 (3 токена) - Средний сегмент
    'DASH': 5, 'XTZ': 5, 'ZEC': 5,
    
    # Вес 4 (3 токена) - Растущие проекты  
    'KCS': 4, 'ENA': 4, 'KAS': 4,
    
    # Вес 3 (3 токена) - Спекулятивные
    'AR': 3, 'SAND': 3, 'DCR': 3,
    
    # Вес 2 (3 токена) - Рисковые ставки
    'FLR': 2, 'WLFI': 2, 'SPX': 2,
    
    # Вес 1 (3 токена) - Максимальный риск/потенциал
    'DEXE': 1, 'KAIA': 1, 'M': 1
}

GAME_TOKENS = list(TOKEN_WEIGHTS.keys())

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