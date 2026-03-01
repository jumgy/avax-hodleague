import math
import random
import time

class FantasyCryptoRankSystem:
    def __init__(self, seed=None):
        if seed is None:
            seed = int(time.time()) % 1000
        random.seed(seed)
        print(f"Random seed: {seed}")
        
        self.tokens = {
            'BTC': {'market_cap': 1800000, 'start_price': 95000, 'category': 'bluechip'},
            'ETH': {'market_cap': 400000, 'start_price': 3200, 'category': 'bluechip'},
            'SOL': {'market_cap': 80000, 'start_price': 180, 'category': 'large_alt'},
            'BNB': {'market_cap': 90000, 'start_price': 600, 'category': 'large_alt'},
            'XRP': {'market_cap': 60000, 'start_price': 1.1, 'category': 'large_alt'},
            'DOGE': {'market_cap': 50000, 'start_price': 0.35, 'category': 'large_alt'},
            'ADA': {'market_cap': 40000, 'start_price': 1.2, 'category': 'large_alt'},
            'AVAX': {'market_cap': 15000, 'start_price': 40, 'category': 'mid_alt'},
            'SHIB': {'market_cap': 15000, 'start_price': 0.000025, 'category': 'mid_alt'},
            'DOT': {'market_cap': 10000, 'start_price': 8, 'category': 'mid_alt'},
            'MATIC': {'market_cap': 8000, 'start_price': 0.85, 'category': 'mid_alt'},
            'LTC': {'market_cap': 8000, 'start_price': 110, 'category': 'mid_alt'},
            'NEAR': {'market_cap': 6000, 'start_price': 5.5, 'category': 'mid_alt'},
            'UNI': {'market_cap': 5000, 'start_price': 8.5, 'category': 'mid_alt'},
            'ATOM': {'market_cap': 4000, 'start_price': 12, 'category': 'mid_alt'},
            'FTM': {'market_cap': 3000, 'start_price': 1.1, 'category': 'small_alt'},
            'SAND': {'market_cap': 1000, 'start_price': 0.45, 'category': 'small_alt'},
            'MANA': {'market_cap': 800, 'start_price': 0.42, 'category': 'small_alt'},
            'ENJ': {'market_cap': 600, 'start_price': 0.35, 'category': 'small_alt'},
            'CHZ': {'market_cap': 500, 'start_price': 0.08, 'category': 'small_alt'},
            'BAT': {'market_cap': 400, 'start_price': 0.25, 'category': 'small_alt'},
            '1INCH': {'market_cap': 350, 'start_price': 0.35, 'category': 'small_alt'},
            'SUSHI': {'market_cap': 300, 'start_price': 1.2, 'category': 'small_alt'},
            'YFI': {'market_cap': 250, 'start_price': 8500, 'category': 'small_alt'},
            'COMP': {'market_cap': 200, 'start_price': 45, 'category': 'small_alt'},
            'MKR': {'market_cap': 180, 'start_price': 1500, 'category': 'small_alt'},
            'AAVE': {'market_cap': 150, 'start_price': 90, 'category': 'small_alt'},
            'SNX': {'market_cap': 120, 'start_price': 2.8, 'category': 'small_alt'},
            'CRV': {'market_cap': 100, 'start_price': 0.75, 'category': 'small_alt'},
            'LEND': {'market_cap': 80, 'start_price': 0.12, 'category': 'small_alt'}
        }
        
        self.weekly_data = self._generate_realistic_weekly_data()
    
    def _generate_realistic_weekly_data(self):
        """Generate realistic weekly data with BTC correlation."""
        data = {}

        # BTC sets overall market tone.
        btc_weekly_change = random.uniform(-0.15, 0.25)
        market_sentiment = "bullish" if btc_weekly_change > 0.05 else "bearish" if btc_weekly_change < -0.05 else "neutral"
        
        # Pick 2-4 outlier tokens for individual moves.
        all_alts = [t for t in self.tokens.keys() if t not in ['BTC', 'ETH']]
        outlier_tokens = random.sample(all_alts, random.randint(2, 4))
        
        print(f"BTC weekly change: {btc_weekly_change:+.1%}")
        print(f"Market sentiment: {market_sentiment}")
        print(f"Outlier moves: {', '.join(outlier_tokens)}")
        
        for token, info in self.tokens.items():
            start_price = info['start_price']
            category = info['category']
            
            if token == 'BTC':
                # BTC is market base.
                weekly_change = btc_weekly_change
                daily_vol = random.uniform(0.02, 0.04)
                
            elif token == 'ETH':
                # ETH correlates with BTC at 75%.
                correlation = 0.75
                eth_independent = random.uniform(-0.06, 0.10)
                weekly_change = btc_weekly_change * correlation + eth_independent * (1 - correlation)
                daily_vol = random.uniform(0.025, 0.05)
                
            elif token in outlier_tokens:
                # Outlier tokens: individual pump/dump.
                if random.random() < 0.65:  # 65% pump
                    weekly_change = random.uniform(0.18, 0.65)
                else:  # 35% dump
                    weekly_change = random.uniform(-0.5, -0.18)
                
                # High volatility for outliers.
                if category == 'small_alt':
                    daily_vol = random.uniform(0.06, 0.14)
                else:
                    daily_vol = random.uniform(0.04, 0.10)
                    
            else:
                # Regular tokens follow BTC with varying correlation.
                if category == 'large_alt':
                    correlation = random.uniform(0.55, 0.75)
                    multiplier = random.uniform(0.9, 1.4)
                    daily_vol = random.uniform(0.04, 0.08)
                elif category == 'mid_alt':
                    correlation = random.uniform(0.35, 0.65)
                    multiplier = random.uniform(1.1, 1.8)
                    daily_vol = random.uniform(0.05, 0.09)
                else:  # small_alt
                    correlation = random.uniform(0.15, 0.55)
                    multiplier = random.uniform(1.3, 2.2)
                    daily_vol = random.uniform(0.06, 0.12)
                
                # BTC influence + independent move.
                btc_influence = btc_weekly_change * correlation * multiplier
                independent_move = random.uniform(-0.12, 0.18) * (1 - correlation)
                weekly_change = btc_influence + independent_move
                
                # Clamp extremes.
                weekly_change = max(-0.6, min(0.5, weekly_change))
            
            # Generate daily prices with trend and volatility.
            daily_trend = weekly_change / 7
            prices = [start_price]
            current_price = start_price
            
            for day in range(7):
                daily_change = daily_trend + random.uniform(-daily_vol, daily_vol)
                current_price *= (1 + daily_change)
                prices.append(current_price)
            
            data[token] = {
                'prices': prices,
                'market_cap': info['market_cap'],
                'weekly_change': weekly_change,
                'daily_volatility': daily_vol,
                'is_outlier': token in outlier_tokens,
                'category': category
            }
        
        return data
    
    def calculate_mc_factor(self, market_cap, weekly_change):
        """MC factor: asymmetric for growth vs decline."""
        market_cap_billions = market_cap / 1000
        if weekly_change >= 0:
            return (market_cap_billions ** 0.15) * 12
        else:
            return (market_cap_billions ** -0.15) * 12
    
    def calculate_daily_growth_bias(self, prices):
        """Analyze intraday moves with growth bias."""
        up_days_activity = 0
        down_days_activity = 0
        total_activity = 0
        
        for i in range(1, len(prices)):
            daily_change_pct = ((prices[i] - prices[i-1]) / prices[i-1]) * 100
            activity_magnitude = abs(daily_change_pct)
            total_activity += activity_magnitude
            
            if daily_change_pct > 0:
                # Up days get higher weight.
                up_days_activity += activity_magnitude * 1.4
            else:
                # Down days get lower weight.
                down_days_activity += activity_magnitude * 1.0
        
        weighted_activity = up_days_activity + down_days_activity
        growth_bias_ratio = up_days_activity / weighted_activity if weighted_activity > 0 else 0
        
        return {
            'total_activity': total_activity,
            'weighted_activity': weighted_activity,
            'up_days_activity': up_days_activity,
            'down_days_activity': down_days_activity,
            'growth_bias_ratio': growth_bias_ratio
        }
    
    def calculate_rank_based_scores(self):
        """Rank system: MC factor applied to rank, not to percent."""
        scores = {}

        # Stage 1: weekly ranks.
        # Gather weekly results for all tokens.
        weekly_results = []
        for token in self.tokens.keys():
            data = self.weekly_data[token]
            prices = data['prices']
            start_price = prices[0]
            end_price = prices[-1]
            weekly_change_pct = ((end_price - start_price) / start_price) * 100
            
            weekly_results.append({
                'token': token,
                'weekly_change_pct': weekly_change_pct,
                'market_cap': data['market_cap']
            })
        
        # Sort by weekly result (best = rank 1).
        weekly_results.sort(key=lambda x: x['weekly_change_pct'], reverse=True)

        # Build rank dict.
        weekly_ranks = {}
        total_tokens = len(weekly_results)
        
        print("\nWEEKLY RANKS BY RESULT:")
        print("-" * 80)
        for rank, result in enumerate(weekly_results, 1):
            token = result['token']
            change = result['weekly_change_pct']
            weekly_ranks[token] = rank
            trend = "+" if change > 0 else "-"
            print(f"   #{rank:2d} {token:<8} {change:+7.2f}%{trend}")

        # Stage 2: intraday ranks.
        # Gather intraday activity data.
        activity_results = []
        for token in self.tokens.keys():
            data = self.weekly_data[token]
            daily_data = self.calculate_daily_growth_bias(data['prices'])
            
            activity_results.append({
                'token': token,
                'weighted_activity': daily_data['weighted_activity'],
                'market_cap': data['market_cap'],
                'growth_bias_ratio': daily_data['growth_bias_ratio']
            })
        
        # Sort by weighted activity (more activity = better rank).
        activity_results.sort(key=lambda x: x['weighted_activity'], reverse=True)
        
        activity_ranks = {}

        print("\nRANKS BY INTRADAY ACTIVITY:")
        print("-" * 80)
        for rank, result in enumerate(activity_results, 1):
            token = result['token']
            activity = result['weighted_activity']
            bias_ratio = result['growth_bias_ratio']
            activity_ranks[token] = rank
            print(f"   #{rank:2d} {token:<8} {activity:6.2f}% activity (growth bias: {bias_ratio:.1%})")

        # Stage 3: final score calculation.
        
        for token in self.tokens.keys():
            data = self.weekly_data[token]
            market_cap = data['market_cap']
            prices = data['prices']
            start_price = prices[0]
            end_price = prices[-1]
            weekly_change_pct = ((end_price - start_price) / start_price) * 100
            # Asymmetric MC factor.
            mc_factor = self.calculate_mc_factor(market_cap, weekly_change_pct)
            
            # Get ranks.
            weekly_rank = weekly_ranks[token]
            activity_rank = activity_ranks[token]
            
            # Convert ranks to points (better rank = more points).
            weekly_rank_points = total_tokens - weekly_rank + 1
            activity_rank_points = total_tokens - activity_rank + 1

            weekly_score = weekly_rank_points * mc_factor
            daily_score = activity_rank_points * mc_factor * 0.3  # Lower weight for activity.
            
            raw_total = weekly_score + daily_score
            
            # Store details for analysis.
            prices = data['prices']
            start_price = prices[0]
            end_price = prices[-1]
            weekly_change_pct = ((end_price - start_price) / start_price) * 100
            daily_analysis = self.calculate_daily_growth_bias(prices)
            
            scores[token] = {
                'weekly_change_pct': weekly_change_pct,
                'weekly_rank': weekly_rank,
                'activity_rank': activity_rank,
                'weekly_rank_points': weekly_rank_points,
                'activity_rank_points': activity_rank_points,
                'mc_factor': mc_factor,
                'weekly_score': weekly_score,
                'daily_score': daily_score,
                'raw_total': raw_total,
                'market_cap': market_cap,
                'total_activity': daily_analysis['total_activity'],
                'weighted_activity': daily_analysis['weighted_activity'],
                'growth_bias_ratio': daily_analysis['growth_bias_ratio'],
                'is_outlier': data['is_outlier'],
                'category': data['category']
            }
        
        return scores
    
    def balanced_normalize(self, scores):
        """Normalize scores to 0-1000 with smooth distribution."""
        raw_values = [s['raw_total'] for s in scores.values()]
        raw_values.sort(reverse=True)

        # Target score distribution.
        target_distribution = []
        n = len(raw_values)
        
        for i in range(n):
            if i < 3:  # Top 3: 850-1000
                score = 1000 - (i * 50)
            elif i < 8:  # Places 4-8: 650-800
                score = 800 - ((i-3) * 30)
            elif i < 15:  # Places 9-15: 400-620
                score = 620 - ((i-8) * 30)
            elif i < 22:  # Places 16-22: 200-370
                score = 370 - ((i-15) * 25)
            else:  # Rest: 0-175
                score = 175 - ((i-22) * 25)
                score = max(0, score)
            
            target_distribution.append(score)
        
        # Map raw scores to target distribution.
        sorted_tokens = sorted(scores.items(), key=lambda x: x[1]['raw_total'], reverse=True)
        
        for i, (token, data) in enumerate(sorted_tokens):
            final_score = target_distribution[i]
            
            # Split final score into components proportionally.
            if data['raw_total'] > 0:
                weekly_ratio = data['weekly_score'] / data['raw_total']
                daily_ratio = data['daily_score'] / data['raw_total']
                
                weekly_final = round(final_score * weekly_ratio)
                daily_final = final_score - weekly_final
            else:
                weekly_final = daily_final = 0
            
            data['final_score'] = final_score
            data['weekly_final'] = weekly_final
            data['daily_final'] = daily_final
            data['card_weight'] = max(5, round(final_score / 100) * 5)
        
        return scores
    
    def print_detailed_analysis(self):
        print("=" * 200)
        print("FANTASY CRYPTO - RANK-BASED SCORING")
        print("   MC FACTOR APPLIED TO RANK, NOT TO PERCENT")
        print("=" * 200)
        
        scores = self.calculate_rank_based_scores()
        final_scores = self.balanced_normalize(scores)
        
        sorted_tokens = sorted(final_scores.items(), key=lambda x: x[1]['final_score'], reverse=True)
        
        print("\nFINAL FANTASY RANKING:")
        print("-" * 200)
        print(f"{'#':<3} {'Token':<8} {'Final':<7} {'Wgt':<4} {'MC(B)':<10} {'Week%':<10} "
              f"{'WkR':<5} {'ActR':<5} {'By_week':<10} {'By_swing':<10} {'MC_fact':<10} {'Status':<10}")
        print("-" * 200)
        
        for i, (token, data) in enumerate(sorted_tokens, 1):
            mc_billions = data['market_cap'] / 1000
            trend_emoji = "+" if data['weekly_change_pct'] > 0 else "-"

            status = ""
            if data['is_outlier']:
                status = "PUMP" if data['weekly_change_pct'] > 0 else "DUMP"
            elif data['category'] == 'bluechip':
                status = "BLUECHIP"
            elif data['category'] == 'large_alt':
                status = "LARGE"
            elif data['category'] == 'mid_alt':
                status = "MID"
            else:
                status = "SMALL"
            
            print(f"{i:<3} {token:<8} {data['final_score']:<7} "
                  f"{data['card_weight']:<4} ${mc_billions:<9.1f} "
                  f"{data['weekly_change_pct']:>+7.2f}%{trend_emoji} "
                  f"{data['weekly_rank']:<5} {data['activity_rank']:<5} "
                  f"{data['weekly_final']:<10} {data['daily_final']:<10} "
                  f"{data['mc_factor']:<10.0f} {status:<10}")
        
        # Fairness analysis.
        print("\nRANK SYSTEM FAIRNESS ANALYSIS:")
        print("-" * 100)

        # Find BTC and best small alt.
        btc_data = final_scores['BTC']
        small_alts = [(t, d) for t, d in final_scores.items() if d['category'] == 'small_alt']
        best_small_alt = max(small_alts, key=lambda x: x[1]['final_score']) if small_alts else None
        
        print(f"BTC result: {btc_data['weekly_change_pct']:+.2f}% (weekly rank #{btc_data['weekly_rank']})")
        print(f"BTC final score: {btc_data['final_score']} pts")
        print(f"BTC MC factor: {btc_data['mc_factor']:.0f}x")

        if best_small_alt:
            token, data = best_small_alt
            print(f"\nBest small alt: {token}")
            print(f"{token} result: {data['weekly_change_pct']:+.2f}% (weekly rank #{data['weekly_rank']})")
            print(f"{token} final score: {data['final_score']} pts")
            print(f"{token} MC factor: {data['mc_factor']:.0f}x")

            if data['weekly_change_pct'] > btc_data['weekly_change_pct'] and data['final_score'] < btc_data['final_score']:
                advantage_ratio = btc_data['mc_factor'] / data['mc_factor']
                print("\nSYSTEM IS FAIR.")
                print(f"   {token} had better result but BTC got more points")
                print(f"   BTC advantage by MC factor: {advantage_ratio:.0f}x")
            elif data['final_score'] > btc_data['final_score']:
                print("\n[WARNING] Possible unfairness: small alt ahead of BTC in final score")

        # Rank system examples.
        print("\nRANK SYSTEM EXAMPLES:")
        print("-" * 100)

        # Top 3 by result vs top 3 by score.
        top_3_performance = sorted(final_scores.items(), key=lambda x: x[1]['weekly_change_pct'], reverse=True)[:3]
        top_3_scores = sorted_tokens[:3]
        
        print("Top 3 by weekly result:")
        for i, (token, data) in enumerate(top_3_performance, 1):
            print(f"   #{i} {token}: {data['weekly_change_pct']:+.2f}%")

        print("\nTop 3 by final score:")
        for i, (token, data) in enumerate(top_3_scores, 1):
            print(f"   #{i} {token}: {data['final_score']} pts (result: {data['weekly_change_pct']:+.2f}%)")

        print("\nRANK SYSTEM EXPLANATION:")
        print("-" * 100)
        print("WkR: rank by weekly result (1 = best, 30 = worst)")
        print("ActR: rank by intraday activity (1 = most active)")
        print("By_week: (31 - WkR) x MC_factor")
        print("By_swing: (31 - ActR) x MC_factor x 0.3")
        print("MC_factor: multiplier from market cap")
        print("\nWHY IT'S FAIR:")
        print("- BTC with small decline can beat many strongly declining tokens")
        print("- BTC high MC factor compensates for average rank")
        print("- Small tokens must show exceptional result to win")

if __name__ == "__main__":
    # Run with different seeds for testing.
    calculator = FantasyCryptoRankSystem()
    calculator.print_detailed_analysis()