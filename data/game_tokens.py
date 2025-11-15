"""Fixed list of 30 game tokens with their weights for tournament play"""

# Token weights for tournament restrictions (higher weight = stronger/more expensive token)
TOKEN_WEIGHTS = {
    # Вес 10
    'BTC': 10, 'ETH': 10, 'XRP': 10,

    # Вес 9
    'BNB': 9, 'SOL': 9, 'TRX': 9,

    # Вес 8
    'DOGE': 8, 'ADA': 8, 'AVAX': 8,

    # Вес 7
    'HYPE': 7, 'WLFI': 7, 'ZEC': 7,

    # Вес 6
    'ENA': 6, 'APT': 6, 'M': 6,

    # Вес 5
    'PUMP': 5, 'KCS': 5, 'POL': 5,

    # Вес 4
    'KAS': 4, 'FLR': 4, 'DASH': 4,

    # Вес 3
    'FET': 3, 'LDO': 3, 'XTZ': 3,

    # Вес 2
    'DCR': 2, 'IOTA': 2, 'AB': 2,

    # Вес 1
    'KAIA': 1, 'FLOKI': 1, 'SPX': 1,
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
