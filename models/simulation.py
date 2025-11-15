from dataclasses import dataclass
from typing import Dict, List
import random
import math

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
    'IOTA': 3, 'SAND': 3, 'DCR': 3,
    # Вес 2 (3 токена) - Рисковые ставки
    'FLR': 2, 'WLFI': 2, 'SPX': 2,
    # Вес 1 (3 токена) - Максимальный риск/потенциал
    'DEXE': 1, 'KAIA': 1, 'M': 1
}

@dataclass
class DailyTokenData:
    """Daily token price and market cap data"""
    symbol: str
    day: int
    price: float
    market_cap: float
    price_change_pct: float

@dataclass 
class DailyScore:
    """Daily score for a player"""
    day: int
    score: int
    tokens_performance: List[Dict]
    market_position: int
    market_sentiment: Dict  # NEW: добавили настроение рынка

class CryptoSimulator:
    """Simulates realistic crypto price movements"""

    def __init__(self, simulation_tokens: List[Dict]):
        self.simulation_tokens = simulation_tokens
        self.days = [1, 2, 3, 4, 5]
        # Store initial prices for each token
        for token in self.simulation_tokens:
            token['initial_price'] = token['current_price']
            token['initial_market_cap'] = token['market_cap']

    def get_market_sentiment_description(self, sentiment_value: float) -> Dict:
        """Переводит числовое значение sentiment в понятное описание"""
        # Переводим в проценты для удобности
        sentiment_pct = sentiment_value * 100
        
        if sentiment_value > 0.15:
            return {
                "status": "Strong Growth",
                "description": "Strong market growth",  # Changed
                "market_change_pct": round(sentiment_pct, 1),
                "trend": "very_bullish"
            }
        elif sentiment_value > 0.05:
            return {
                "status": "Growth", 
                "description": "Market is growing",  # Changed
                "market_change_pct": round(sentiment_pct, 1),
                "trend": "bullish"
            }
        elif sentiment_value > -0.05:
            return {
                "status": "Neutral",
                "description": "Sideways market movement",  # Changed
                "market_change_pct": round(sentiment_pct, 1),
                "trend": "neutral"
            }
        elif sentiment_value > -0.15:
            return {
                "status": "Decline",
                "description": "Market is declining",  # Changed
                "market_change_pct": round(sentiment_pct, 1),
                "trend": "bearish"
            }
        else:
            return {
                "status": "Strong Decline",
                "description": "Strong market decline",  # Changed
                "market_change_pct": round(sentiment_pct, 1),
                "trend": "very_bearish"
            }

    def calculate_actual_market_performance(self, daily_data: Dict[str, DailyTokenData]) -> float:
        """Вычисляет реальное среднее изменение рынка за день"""
        if not daily_data:
            return 0.0
        
        daily_changes = []
        for token_data in daily_data.values():
            daily_changes.append(token_data.price_change_pct)
        
        if daily_changes:
            return sum(daily_changes) / len(daily_changes)
        return 0.0

    def generate_daily_changes(self) -> Dict:
        """Generate realistic daily price changes for all tokens"""
        daily_data = {}
        daily_sentiments = {}
        
        weekly_sentiment = random.uniform(-0.12, 0.12)  # Задать тренд на неделю

        for day in self.days:
            daily_data[day] = {}

            # Market sentiment for the day
            if random.random() < 0.2:  # 20% шанс на микро-отскок
                daily_sentiment = -weekly_sentiment * random.uniform(0.3, 0.7)
            else:
                daily_sentiment = weekly_sentiment + random.uniform(-0.005, 0.005)
            market_sentiment = daily_sentiment

            for token in self.simulation_tokens:
                symbol = token['symbol']
                base_price = token['current_price']
                base_market_cap = token['market_cap']

                # Token-specific volatility based on market cap
                if base_market_cap > 100e9:
                    volatility = random.uniform(0.005, 0.015)
                elif base_market_cap > 10e9:
                    volatility = random.uniform(0.02, 0.05)
                else:
                    volatility = random.uniform(0.03, 0.20)

                # Random walk with market sentiment bias
                individual_change = random.uniform(-volatility, volatility)
                
                if base_market_cap > 100e9:
                    sentiment_multiplier = 0.2  # Для BTC, ETH, BNB
                elif base_market_cap > 10e9:
                    sentiment_multiplier = 0.35  # Для средних
                else:
                    sentiment_multiplier = 0.5   # Для остальных
                    
                total_change = individual_change + (market_sentiment * sentiment_multiplier)

                # Apply momentum from previous day
                if day != 1:
                    prev_day = day - 1
                    if prev_day in daily_data and symbol in daily_data[prev_day]:
                        prev_change = daily_data[prev_day][symbol].price_change_pct / 100
                        momentum = prev_change * 0.3  # 30% momentum carryover
                        total_change += momentum

                # Clamp extreme changes
                total_change = max(-0.4, min(0.6, total_change))  # -40% to +60% max

                new_price = base_price * (1 + total_change)
                new_market_cap = base_market_cap * (1 + total_change)

                daily_data[day][symbol] = DailyTokenData(
                    symbol=symbol,
                    day=day,
                    price=new_price,
                    market_cap=new_market_cap,
                    price_change_pct=total_change * 100
                )

                # Update base price for next day
                token['current_price'] = new_price
                token['market_cap'] = new_market_cap

            # Вычисляем реальное изменение рынка и создаем sentiment
            actual_market_change = self.calculate_actual_market_performance(daily_data[day])
            daily_sentiments[day] = self.get_market_sentiment_description(actual_market_change / 100)
            
            # Обновляем market_change_pct с реальными данными
            daily_sentiments[day]['actual_market_change_pct'] = round(actual_market_change, 1)

        return {
            'daily_data': daily_data,
            'daily_sentiments': daily_sentiments
        }

class FantasyCryptoRankSystem:
    """Fantasy Crypto Ranking System with daily scoring"""

    def __init__(self, all_tokens: List[Dict]):
        self.all_tokens = all_tokens
        self.days = [1, 2, 3, 4, 5]
        self.max_deck_weight = 28
        self.deck_size = 5

    def calculate_mc_factor(self, market_cap: float, change: float) -> float:
        """Calculate MC factor based on market cap and change direction"""
        market_cap_billions = market_cap / 1_000_000_000
        if change >= 0:
            return (market_cap_billions ** 0.15) * 12
        else:
            return (market_cap_billions ** -0.05) * 12

    def calculate_activity_score(self, prices: List[float]) -> float:
        """Calculate activity score based on price changes"""
        if len(prices) < 2:
            return 0

        activity = 0
        for i in range(1, len(prices)):
            change = abs((prices[i] - prices[i-1]) / prices[i-1]) * 100
            activity += change

        return activity

    def get_token_weight(self, symbol: str) -> int:
        """Get weight for a token symbol"""
        return TOKEN_WEIGHTS.get(symbol, 5)  # Default weight 5 if not found

    def is_valid_deck(self, tokens: List[str]) -> bool:
        """Check if deck is valid (5 tokens, weight <= 28)"""
        if len(tokens) != self.deck_size:
            return False
        
        total_weight = sum(self.get_token_weight(symbol) for symbol in tokens)
        return total_weight <= self.max_deck_weight

    def find_max_possible_score(self, all_scores: Dict[str, Dict]) -> int:
        """Find maximum possible score with deck constraints"""
        from itertools import combinations
        
        # Get all available tokens sorted by score
        available_tokens = [(symbol, data['final_score']) for symbol, data in all_scores.items()]
        available_tokens.sort(key=lambda x: x[1], reverse=True)
        
        max_score = 0
        
        # Try combinations of top tokens
        top_tokens = available_tokens[:min(15, len(available_tokens))]  # Limit for performance
        
        for combination in combinations([t[0] for t in top_tokens], self.deck_size):
            if self.is_valid_deck(list(combination)):
                combo_score = sum(all_scores[symbol]['final_score'] for symbol in combination)
                if combo_score > max_score:
                    max_score = combo_score
        
        return max_score


    def calculate_scores_for_day(self, daily_data: Dict[int, Dict[str, DailyTokenData]], current_day: int) -> Dict[str, Dict]:
        """Calculate scores for all tokens up to current day"""
        scores = {}

        for token in self.all_tokens:
            symbol = token['symbol']

            # Get prices from day 1 to current_day
            prices = []
            for day in range(1, current_day + 1):
                if day in daily_data and symbol in daily_data[day]:
                    prices.append(daily_data[day][symbol].price)
                else:
                    # If no data for this day, use previous price or initial
                    if prices:
                        prices.append(prices[-1])
                    else:
                        prices.append(token['initial_price'])

            if len(prices) < 2:
                continue

            # Calculate period change (from day 1 to current day)
            period_change = ((prices[-1] - prices[0]) / prices[0]) * 100

            # Calculate activity for the period
            activity_score = self.calculate_activity_score(prices)

            # Get current market cap
            current_market_cap = token['initial_market_cap']
            if current_day in daily_data and symbol in daily_data[current_day]:
                current_market_cap = daily_data[current_day][symbol].market_cap

            scores[symbol] = {
                'period_change': period_change,
                'activity_score': activity_score,
                'market_cap': current_market_cap,
                'prices': prices
            }

        # Rank tokens by period change
        token_list = list(scores.items())
        token_list.sort(key=lambda x: x[1]['period_change'], reverse=True)
        for i, (symbol, data) in enumerate(token_list):
            scores[symbol]['change_rank'] = i + 1

        # Rank tokens by activity
        token_list.sort(key=lambda x: x[1]['activity_score'], reverse=True)
        for i, (symbol, data) in enumerate(token_list):
            scores[symbol]['activity_rank'] = i + 1

        # Calculate raw scores
        total_tokens = len(scores)
        for symbol, data in scores.items():
            weekly_points = total_tokens - data['change_rank'] + 1
            activity_points = total_tokens - data['activity_rank'] + 1
            mc_factor = self.calculate_mc_factor(data['market_cap'], data['period_change'])

            raw_score = (weekly_points * mc_factor * 4) + (activity_points * mc_factor * 1)
            scores[symbol]['raw_score'] = raw_score
            scores[symbol]['mc_factor'] = mc_factor

        # Normalize scores
        if scores:
            raw_values = [data['raw_score'] for data in scores.values()]
            min_raw = min(raw_values)
            max_raw = max(raw_values)
            range_raw = max_raw - min_raw

            for symbol, data in scores.items():
                if range_raw > 0:
                    normalized = (data['raw_score'] - min_raw) / range_raw
                    final_score = int(1000 * (normalized ** 0.7))
                else:
                    final_score = 500

                scores[symbol]['final_score'] = final_score
                
        def get_base_score(symbol, sorted_symbols):
            if symbol == "BTC":
                return 700
            elif symbol == "ETH":
                return 600
            else:
                position = sorted_symbols.index(symbol) + 1
                if position == 3:
                    return 520
                elif position == 4:
                    return 480
                else:
                    # Плавное уменьшение после 4 места (пример — экспонента или линейно)
                    # Минимум — 0, максимум — 480 (на 4-м месте)
                    base = int(480 * math.exp(-0.13 * (position - 4)))
                    return max(base, 0)
                
        sorted_symbols = [t['symbol'] for t in sorted(self.all_tokens, key=lambda x: -x['initial_market_cap'])]
        base_score = get_base_score(symbol, sorted_symbols)
        scores[symbol]['final_score'] += base_score
        scores[symbol]['base_score'] = base_score  # для отладки

        return scores

    def calculate_daily_scores(self, selected_tokens: List[Dict], daily_data: Dict[int, Dict[str, DailyTokenData]], daily_sentiments: Dict) -> List[DailyScore]:
        """Calculate fantasy scores for each day"""
        daily_scores = []

        for day in self.days:
            # Calculate scores for all tokens up to this day
            all_scores = self.calculate_scores_for_day(daily_data, day)

            # Calculate player's total score for this day
            player_score = 0
            tokens_performance = []

            for selected_token in selected_tokens:
                symbol = selected_token['symbol']

                if symbol in all_scores:
                    token_data = all_scores[symbol]
                    token_score = token_data['final_score']
                    player_score += token_score

                    # Get daily change for this specific day
                    daily_change = 0
                    if day in daily_data and symbol in daily_data[day]:
                        daily_change = daily_data[day][symbol].price_change_pct

                    # Calculate individual contributions to raw score
                    total_tokens = len(all_scores)
                    weekly_points = total_tokens - token_data['change_rank'] + 1
                    activity_points = total_tokens - token_data['activity_rank'] + 1
                    weekly_contribution = weekly_points * token_data['mc_factor'] * 4
                    activity_contribution = activity_points * token_data['mc_factor'] * 1

                    tokens_performance.append({
                        'symbol': symbol,
                        'name': selected_token.get('name', symbol),
                        'daily_change_pct': round(daily_change, 2),
                        'period_change_pct': round(token_data['period_change'], 2),
                        # Подробная разбивка скоринга
                        'change_rank': token_data['change_rank'],
                        'activity_rank': token_data['activity_rank'],
                        'weekly_points': weekly_points,
                        'activity_points': activity_points,
                        'activity_score': round(token_data['activity_score'], 2),  # сырой activity
                        'mc_factor': round(token_data['mc_factor'], 4),
                        'weekly_contribution': round(weekly_contribution, 2),      # NEW!
                        'activity_contribution': round(activity_contribution, 2), # NEW!
                        'raw_score': round(token_data['raw_score'], 2),
                        'final_score': round(token_score, 2)
                    })

            # Calculate market position (1-100 scale)
            max_possible_score = self.find_max_possible_score(all_scores)

            # Calculate market position (1-100 scale)
            if max_possible_score > 0:
                position_ratio = player_score / max_possible_score
                market_position = max(1, min(100, int((1 - position_ratio) * 100)))
            else:
                market_position = 50

            # Get market sentiment for this day
            sentiment_info = daily_sentiments.get(day, {
                "status": "Neutral",
                "description": "Боковое движение рынка", 
                "market_change_pct": 0.0,
                "trend": "neutral",
                "actual_market_change_pct": 0.0
            })

            daily_scores.append(DailyScore(
                day=day,
                score=int(player_score),
                tokens_performance=tokens_performance,
                market_position=market_position,
                market_sentiment=sentiment_info  # NEW: передаем весь словарь
            ))

        return daily_scores

    def run_full_simulation(self, selected_tokens: List[Dict], simulation_data: Dict) -> Dict:
        """Run complete simulation with detailed results"""
        daily_data = simulation_data['daily_data']
        daily_sentiments = simulation_data['daily_sentiments']

        daily_scores = self.calculate_daily_scores(selected_tokens, daily_data, daily_sentiments)

        # Get final day analysis
        final_day_scores = self.calculate_scores_for_day(daily_data, 5)

        summary = {
            'daily_scores': daily_scores,
            'final_score': daily_scores[-1].score if daily_scores else 0,
            'final_position': daily_scores[-1].market_position if daily_scores else 0,
            'selected_tokens_analysis': {},
            'market_analysis': {
                'total_tokens': len(self.all_tokens),
                'selected_tokens': len(selected_tokens),
                'avg_market_cap': sum(token['initial_market_cap'] for token in self.all_tokens) / len(self.all_tokens) if self.all_tokens else 0,
                'daily_sentiments': daily_sentiments  # NEW: добавляем sentiment info
            }
        }

        # Add detailed analysis for selected tokens
        for token in selected_tokens:
            symbol = token['symbol']
            if symbol in final_day_scores:
                summary['selected_tokens_analysis'][symbol] = final_day_scores[symbol]

        return summary

# Utility function for easy integration
def run_fantasy_simulation(selected_tokens: List[Dict], all_tokens: List[Dict]) -> Dict:
    """Run complete fantasy crypto simulation"""
    # Initialize simulator
    simulator = CryptoSimulator(all_tokens.copy())  # Copy to avoid modifying original

    # Generate daily price changes and sentiments
    simulation_data = simulator.generate_daily_changes()

    # Initialize fantasy ranking system
    fantasy_system = FantasyCryptoRankSystem(all_tokens)

    # Run simulation
    results = fantasy_system.run_full_simulation(selected_tokens, simulation_data)

    return results