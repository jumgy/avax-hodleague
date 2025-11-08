import math
import random
import time

class FantasyCryptoBalanced:
    def __init__(self, seed=None):
        if seed is None:
            seed = int(time.time()) % 1000
        random.seed(seed)
        print(f"🎲 Random seed: {seed}")
        
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
        data = {}
        
        # BTC задает тон рынку
        btc_weekly_change = random.uniform(-0.15, 0.25)
        market_sentiment = "bullish" if btc_weekly_change > 0.05 else "bearish" if btc_weekly_change < -0.05 else "neutral"
        
        # 2-4 outlier токена
        all_alts = [t for t in self.tokens.keys() if t not in ['BTC', 'ETH']]
        outlier_tokens = random.sample(all_alts, random.randint(2, 4))
        
        print(f"📊 BTC: {btc_weekly_change:+.1%}, рынок: {market_sentiment}")
        print(f"🎯 Индивидуальные движения: {', '.join(outlier_tokens)}")
        
        for token, info in self.tokens.items():
            start_price = info['start_price']
            category = info['category']
            
            if token == 'BTC':
                weekly_change = btc_weekly_change
                daily_vol = random.uniform(0.02, 0.04)
                
            elif token == 'ETH':
                correlation = 0.75
                eth_independent = random.uniform(-0.06, 0.10)
                weekly_change = btc_weekly_change * correlation + eth_independent * (1 - correlation)
                daily_vol = random.uniform(0.025, 0.05)
                
            elif token in outlier_tokens:
                if random.random() < 0.65:  # Памп
                    weekly_change = random.uniform(0.18, 0.65)
                else:  # Дамп
                    weekly_change = random.uniform(-0.5, -0.18)
                
                daily_vol = random.uniform(0.06, 0.14) if category == 'small_alt' else random.uniform(0.04, 0.10)
                
            else:
                # Корреляция с BTC по категориям
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
                
                btc_influence = btc_weekly_change * correlation * multiplier
                independent_move = random.uniform(-0.12, 0.18) * (1 - correlation)
                weekly_change = btc_influence + independent_move
                weekly_change = max(-0.6, min(0.5, weekly_change))  # Лимиты
            
            # Генерация дневных цен
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
    
    def calculate_price_per_percent(self, market_cap):
        """MC фактор с более сбалансированной кривой"""
        market_cap_billions = market_cap / 1000
        return (market_cap_billions ** 0.65) * 10
    
    def calculate_total_movement(self, prices):
        """Сумма всех внутридневных движений"""
        total_movement = 0
        for i in range(1, len(prices)):
            daily_change_pct = abs((prices[i] - prices[i-1]) / prices[i-1]) * 100
            total_movement += daily_change_pct
        return total_movement
    
    def calculate_balanced_scores(self):
        """Расчет с раздельными компонентами"""
        scores = {}
        
        for token in self.tokens.keys():
            data = self.weekly_data[token]
            prices = data['prices']
            market_cap = data['market_cap']
            
            start_price = prices[0]
            end_price = prices[-1]
            weekly_change_pct = ((end_price - start_price) / start_price) * 100
            
            price_per_percent = self.calculate_price_per_percent(market_cap)
            direction_multiplier = 4 if weekly_change_pct > 0 else 1
            
            # КОМПОНЕНТ 1: Скор от недельного результата
            weekly_score = abs(weekly_change_pct) * price_per_percent * direction_multiplier
            
            # КОМПОНЕНТ 2: Скор от внутридневных качелей
            total_movement = self.calculate_total_movement(prices)
            daily_score = total_movement * price_per_percent * 0.15
            
            # Суммарный сырой скор
            raw_total = weekly_score + daily_score
            
            scores[token] = {
                'weekly_change_pct': weekly_change_pct,
                'total_movement': total_movement,
                'price_per_percent': price_per_percent,
                'weekly_score': weekly_score,
                'daily_score': daily_score,
                'raw_total': raw_total,
                'market_cap': market_cap,
                'is_outlier': data['is_outlier'],
                'category': data['category']
            }
        
        return scores
    
    def balanced_normalize(self, scores):
        """НОВАЯ нормализация с лучшим распределением"""
        raw_values = [s['raw_total'] for s in scores.values()]
        raw_values.sort(reverse=True)
        
        # Создаем более плавное распределение очков
        target_distribution = []
        n = len(raw_values)
        
        for i in range(n):
            if i < 3:  # Топ-3: 850-1000
                score = 1000 - (i * 50)
            elif i < 8:  # 4-8 место: 650-800
                score = 800 - ((i-3) * 30)
            elif i < 15:  # 9-15 место: 400-620
                score = 620 - ((i-8) * 30)
            elif i < 22:  # 16-22 место: 200-370
                score = 370 - ((i-15) * 25)
            else:  # Остальные: 0-175
                score = 175 - ((i-22) * 25)
                score = max(0, score)
            
            target_distribution.append(score)
        
        # Привязываем сырые скоры к целевому распределению
        sorted_tokens = sorted(scores.items(), key=lambda x: x[1]['raw_total'], reverse=True)
        
        for i, (token, data) in enumerate(sorted_tokens):
            final_score = target_distribution[i]
            
            # Распределяем финальный скор на компоненты пропорционально сырым скорам
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
    
    def print_analysis(self):
        print("=" * 160)
        print("🎮 FANTASY CRYPTO - СБАЛАНСИРОВАННОЕ РАСПРЕДЕЛЕНИЕ ОЧКОВ")
        print("=" * 160)
        
        scores = self.calculate_balanced_scores()
        final_scores = self.balanced_normalize(scores)
        
        sorted_tokens = sorted(final_scores.items(), key=lambda x: x[1]['final_score'], reverse=True)
        
        print(f"\n🏆 ИТОГОВЫЙ РЕЙТИНГ:")
        print("-" * 160)
        print(f"{'#':<3} {'Токен':<8} {'Финал':<7} {'Вес':<4} {'MC(млрд)':<10} {'Недел.%':<10} "
              f"{'За_неделю':<10} {'За_качели':<10} {'Волат.%':<8} {'Статус':<7}")
        print("-" * 160)
        
        for i, (token, data) in enumerate(sorted_tokens, 1):
            mc_billions = data['market_cap'] / 1000
            trend_emoji = "📈" if data['weekly_change_pct'] > 0 else "📉"
            
            status = ""
            if data['is_outlier']:
                status = "🎯ПАМП" if data['weekly_change_pct'] > 0 else "💥ДАМП"
            elif data['category'] == 'bluechip':
                status = "💎БЛЮЧИП"
            elif data['category'] == 'large_alt':
                status = "🟢КРУПН"
            elif data['category'] == 'mid_alt':
                status = "🟡СРЕДН"
            else:
                status = "🔴МЕЛК"
            
            print(f"{i:<3} {token:<8} {data['final_score']:<7} "
                  f"{data['card_weight']:<4} ${mc_billions:<9.1f} "
                  f"{data['weekly_change_pct']:>+7.2f}%{trend_emoji} "
                  f"{data['weekly_final']:<10} {data['daily_final']:<10} "
                  f"{data['total_movement']:<8.1f} {status:<7}")
        
        # Проверка распределения
        score_ranges = {
            "800-1000": len([s for s in final_scores.values() if s['final_score'] >= 800]),
            "600-799": len([s for s in final_scores.values() if 600 <= s['final_score'] < 800]),
            "400-599": len([s for s in final_scores.values() if 400 <= s['final_score'] < 600]),
            "200-399": len([s for s in final_scores.values() if 200 <= s['final_score'] < 400]),
            "0-199": len([s for s in final_scores.values() if s['final_score'] < 200])
        }
        
        print(f"\n📊 РАСПРЕДЕЛЕНИЕ ОЧКОВ:")
        print("-" * 60)
        for range_name, count in score_ranges.items():
            print(f"{range_name}: {count} токенов")
        
        btc_pos = next(i for i, (t, _) in enumerate(sorted_tokens, 1) if t == 'BTC')
        eth_pos = next(i for i, (t, _) in enumerate(sorted_tokens, 1) if t == 'ETH')
        print(f"\n💎 BTC позиция: #{btc_pos} | ETH позиция: #{eth_pos}")
        
        print(f"\n💡 ОБЪЯСНЕНИЕ СТОЛБЦОВ:")
        print("За_неделю: очки за итоговое недельное изменение цены")
        print("За_качели: очки за внутринедельные движения (волатильность)")
        print("Финал = За_неделю + За_качели")

if __name__ == "__main__":
    calculator = FantasyCryptoBalanced()
    calculator.print_analysis()