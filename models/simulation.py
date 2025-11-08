from dataclasses import dataclass
from typing import Dict, List
from datetime import datetime
import random
import math

@dataclass
class DailyTokenData:
    """Daily token price and market cap data"""
    symbol: str
    day: str
    price: float
    market_cap: float
    price_change_pct: float

@dataclass 
class DailyScore:
    """Daily score for a player"""
    day: str
    score: int
    tokens_performance: List[Dict]
    market_position: int

class CryptoSimulator:
    """Simulates realistic crypto price movements"""
    
    def __init__(self, simulation_tokens: List[Dict]):
        self.simulation_tokens = simulation_tokens
        self.days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']

    def generate_daily_changes(self) -> Dict[str, Dict[str, DailyTokenData]]:
        """Generate realistic daily price changes for all tokens"""
        daily_data = {}
        
        for day in self.days:
            daily_data[day] = {}
            
            # Market sentiment for the day (-1 to 1, affects all tokens)
            market_sentiment = random.uniform(-0.3, 0.3)
            
            for token in self.simulation_tokens:
                symbol = token['symbol']
                base_price = token['current_price']
                base_market_cap = token['market_cap']
                
                # Token-specific volatility based on market cap
                if base_market_cap > 100e9:  # Large cap (>100B)
                    volatility = random.uniform(0.02, 0.08)  # 2-8% daily
                elif base_market_cap > 10e9:  # Mid cap (10-100B) 
                    volatility = random.uniform(0.05, 0.15)  # 5-15% daily
                else:  # Small cap (<10B)
                    volatility = random.uniform(0.08, 0.25)  # 8-25% daily
                
                # Random walk with market sentiment bias
                individual_change = random.uniform(-volatility, volatility)
                total_change = individual_change + (market_sentiment * 0.5)
                
                # Apply some momentum (trending)
                if day != 'monday':
                    prev_day = self.days[self.days.index(day) - 1]
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
                
        return daily_data

class FantasyCryptoRankSystem:
    """Fantasy Crypto Ranking System with asymmetric MC factors and proper scoring"""
    
    def __init__(self, all_tokens: List[Dict]):
        self.all_tokens = all_tokens
        self.days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
    
    def calculate_mc_factor(self, market_cap: float, weekly_change: float) -> float:
        """Asymmetric MC factor based on market cap and change direction"""
        market_cap_billions = market_cap / 1_000_000_000
        
        if weekly_change >= 0:
            # Growth boost: (market_cap ** 0.15) * 12
            return (market_cap_billions ** 0.15) * 12
        else:
            # Decline penalty for large caps: (market_cap ** -0.05) * 12
            return (market_cap_billions ** -0.05) * 12
    
    def calculate_activity_score(self, daily_changes: List[float]) -> float:
        """Calculate token activity/volatility score based on daily changes"""
        if not daily_changes:
            return 0
        
        # Sum of absolute daily changes as activity measure
        activity = sum(abs(change) for change in daily_changes)
        return activity
    
    def calculate_weekly_change(self, daily_data: Dict[str, DailyTokenData], symbol: str) -> float:
        """Calculate weekly percentage change for a token"""
        # Get data from Tuesday to Friday (Monday is start with 0 score)
        trading_days = ['tuesday', 'wednesday', 'thursday', 'friday']
        
        if 'tuesday' not in daily_data or symbol not in daily_data['tuesday']:
            return 0
        
        start_price = daily_data['tuesday'][symbol].price
        end_price = daily_data['friday'][symbol].price if 'friday' in daily_data and symbol in daily_data['friday'] else start_price
        
        if start_price == 0:
            return 0
        
        return ((end_price - start_price) / start_price) * 100
    
    def calculate_raw_scores(self, daily_data: Dict[str, Dict[str, DailyTokenData]]) -> Dict[str, Dict]:
        """Calculate raw scores for all tokens"""
        raw_scores = {}
        
        for token in self.all_tokens:
            symbol = token['symbol']
            
            # Get weekly change (Tuesday to Friday)
            weekly_change = self.calculate_weekly_change(daily_data, symbol)
            
            # Get daily changes for activity calculation
            daily_changes = []
            for day in ['tuesday', 'wednesday', 'thursday', 'friday']:
                if day in daily_data and symbol in daily_data[day]:
                    daily_changes.append(daily_data[day][symbol].price_change_pct)
            
            # Calculate activity score
            activity_score = self.calculate_activity_score(daily_changes)
            
            # Get current market cap (from Friday or latest available)
            current_market_cap = token['market_cap']
            for day in reversed(['friday', 'thursday', 'wednesday', 'tuesday']):
                if day in daily_data and symbol in daily_data[day]:
                    current_market_cap = daily_data[day][symbol].market_cap
                    break
            
            # Calculate MC factor
            mc_factor = self.calculate_mc_factor(current_market_cap, weekly_change)
            
            # Calculate weighted scores
            weekly_score = weekly_change * mc_factor
            activity_weighted_score = activity_score * 0.3  # 30% weight for activity
            
            # Raw score combines weekly performance and activity
            raw_score = weekly_score + activity_weighted_score
            
            raw_scores[symbol] = {
                'weekly_change': weekly_change,
                'activity_score': activity_score,
                'mc_factor': mc_factor,
                'weekly_score': weekly_score,
                'activity_weighted_score': activity_weighted_score,
                'raw_score': raw_score,
                'market_cap': current_market_cap
            }
        
        return raw_scores
    
    def normalize_scores(self, raw_scores: Dict[str, Dict]) -> Dict[str, Dict]:
        """Normalize scores using percentile-based approach with power smoothing"""
        if not raw_scores:
            return {}
        
        # Get all raw score values
        all_raw_values = [data['raw_score'] for data in raw_scores.values()]
        sorted_values = sorted(all_raw_values)
        
        normalized_scores = {}
        for symbol, data in raw_scores.items():
            # Calculate percentile rank
            if len(sorted_values) > 1:
                rank = sorted_values.index(data['raw_score'])
                percentile = rank / (len(sorted_values) - 1)
            else:
                percentile = 0.5
            
            # Apply power smoothing (power 0.7)
            smoothed = percentile ** 0.7
            
            # Scale to 1000 points maximum
            final_score = smoothed * 1000
            
            normalized_scores[symbol] = {
                **data,
                'percentile': percentile,
                'smoothed_score': smoothed,
                'final_score': final_score
            }
        
        return normalized_scores
    
    def calculate_daily_scores(self, selected_tokens: List[Dict], daily_data: Dict[str, Dict[str, DailyTokenData]]) -> List[DailyScore]:
        """Calculate fantasy scores for each day of the week"""
        daily_scores = []
        
        # Monday = starting day, score = 0 for all
        daily_scores.append(DailyScore(
            day='monday',
            score=0,
            tokens_performance=[],
            market_position=0
        ))
        
        # Calculate raw scores for all tokens
        raw_scores = self.calculate_raw_scores(daily_data)
        
        # Normalize scores
        normalized_scores = self.normalize_scores(raw_scores)
        
        # Calculate cumulative scores for each day
        cumulative_score = 0
        
        for day in ['tuesday', 'wednesday', 'thursday', 'friday']:
            day_score = 0
            tokens_performance = []
            
            # Calculate scores for selected tokens only
            for selected_token in selected_tokens:
                symbol = selected_token['symbol']
                
                if symbol in normalized_scores:
                    token_data = normalized_scores[symbol]
                    
                    # Use final normalized score
                    token_score = token_data['final_score']
                    day_score += token_score
                    
                    # Get daily performance data
                    daily_change = 0
                    if day in daily_data and symbol in daily_data[day]:
                        daily_change = daily_data[day][symbol].price_change_pct
                    
                    tokens_performance.append({
                        'symbol': symbol,
                        'name': selected_token.get('name', symbol),
                        'daily_change_pct': round(daily_change, 2),
                        'weekly_change_pct': round(token_data['weekly_change'], 2),
                        'activity_score': round(token_data['activity_score'], 2),
                        'mc_factor': round(token_data['mc_factor'], 4),
                        'raw_score': round(token_data['raw_score'], 2),
                        'final_score': round(token_score, 2)
                    })
            
            cumulative_score += day_score
            
            # Calculate market position (1-100 scale based on cumulative performance)
            max_possible_cumulative = len(selected_tokens) * 1000 * (self.days.index(day))
            if max_possible_cumulative > 0:
                market_position = min(100, max(1, int((cumulative_score / max_possible_cumulative) * 100)))
            else:
                market_position = 50
            
            daily_scores.append(DailyScore(
                day=day,
                score=int(cumulative_score),
                tokens_performance=tokens_performance,
                market_position=market_position
            ))
        
        return daily_scores
    
    def run_full_simulation(self, selected_tokens: List[Dict], daily_data: Dict[str, Dict[str, DailyTokenData]]) -> Dict:
        """Run complete simulation with detailed results"""
        
        # Calculate daily scores
        daily_scores = self.calculate_daily_scores(selected_tokens, daily_data)
        
        # Calculate raw scores for analysis
        raw_scores = self.calculate_raw_scores(daily_data)
        normalized_scores = self.normalize_scores(raw_scores)
        
        # Create summary
        summary = {
            'daily_scores': daily_scores,
            'final_score': daily_scores[-1].score if daily_scores else 0,
            'final_position': daily_scores[-1].market_position if daily_scores else 0,
            'selected_tokens_analysis': {},
            'market_analysis': {
                'total_tokens': len(self.all_tokens),
                'selected_tokens': len(selected_tokens),
                'avg_market_cap': sum(token['market_cap'] for token in self.all_tokens) / len(self.all_tokens) if self.all_tokens else 0
            }
        }
        
        # Add detailed analysis for selected tokens
        for token in selected_tokens:
            symbol = token['symbol']
            if symbol in normalized_scores:
                summary['selected_tokens_analysis'][symbol] = normalized_scores[symbol]
        
        return summary

# Utility function for easy integration
def run_fantasy_simulation(selected_tokens: List[Dict], all_tokens: List[Dict]) -> Dict:
    """Run complete fantasy crypto simulation"""
    
    # Initialize simulator
    simulator = CryptoSimulator(all_tokens.copy())  # Copy to avoid modifying original
    
    # Generate daily price changes
    daily_data = simulator.generate_daily_changes()
    
    # Initialize fantasy ranking system
    fantasy_system = FantasyCryptoRankSystem(all_tokens)
    
    # Run simulation
    results = fantasy_system.run_full_simulation(selected_tokens, daily_data)
    
    return results

# Example usage and testing
def test_simulation():
    """Test the simulation system"""
    
    # Sample token data
    sample_tokens = [
        {'symbol': 'BTC', 'name': 'Bitcoin', 'current_price': 45000, 'market_cap': 850_000_000_000},
        {'symbol': 'ETH', 'name': 'Ethereum', 'current_price': 3000, 'market_cap': 360_000_000_000},
        {'symbol': 'BNB', 'name': 'BNB', 'current_price': 300, 'market_cap': 45_000_000_000},
        {'symbol': 'ADA', 'name': 'Cardano', 'current_price': 0.45, 'market_cap': 15_000_000_000},
        {'symbol': 'SOL', 'name': 'Solana', 'current_price': 100, 'market_cap': 30_000_000_000},
        {'symbol': 'DOT', 'name': 'Polkadot', 'current_price': 7.5, 'market_cap': 8_000_000_000},
        {'symbol': 'MATIC', 'name': 'Polygon', 'current_price': 0.85, 'market_cap': 6_000_000_000},
        {'symbol': 'AVAX', 'name': 'Avalanche', 'current_price': 35, 'market_cap': 12_000_000_000},
        {'symbol': 'LINK', 'name': 'Chainlink', 'current_price': 12, 'market_cap': 6_500_000_000},
        {'symbol': 'UNI', 'name': 'Uniswap', 'current_price': 6, 'market_cap': 3_600_000_000}
    ]
    
    # Selected tokens for fantasy portfolio
    selected_tokens = sample_tokens[:5]  # First 5 tokens
    
    # Run simulation
    results = run_fantasy_simulation(selected_tokens, sample_tokens)
    
    print("=== Fantasy Crypto Simulation Results ===")
    print(f"Final Score: {results['final_score']}")
    print(f"Market Position: {results['final_position']}/100")
    print("\nDaily Progression:")
    
    for daily_score in results['daily_scores']:
        print(f"{daily_score.day.capitalize()}: {daily_score.score} points (Position: {daily_score.market_position})")
    
    print("\nToken Analysis:")
    for symbol, analysis in results['selected_tokens_analysis'].items():
        print(f"{symbol}: Weekly Change: {analysis['weekly_change']:.2f}%, Final Score: {analysis['final_score']:.2f}")
    
    return results

if __name__ == "__main__":
    test_simulation()