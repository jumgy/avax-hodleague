import requests
import json
import time
import random
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from dataclasses import dataclass
import os
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

class ProxyManager:
    def __init__(self, proxy_file: str = "proxies.txt"):
        self.proxy_file = proxy_file
        self.proxies = []
        self.current_proxy_index = 0
        self.failed_proxies = set()
        self.load_proxies()
    
    def load_proxies(self):
        """Загрузка прокси из файла"""
        if not os.path.exists(self.proxy_file):
            print(f"⚠️ Файл {self.proxy_file} не найден. Работаем без прокси.")
            return
        
        try:
            with open(self.proxy_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Поддерживаем различные форматы прокси
                    if '://' not in line:
                        # Если нет протокола, добавляем http://
                        proxy_url = f"http://{line}"
                    else:
                        proxy_url = line
                    
                    self.proxies.append(proxy_url)
            
            if self.proxies:
                print(f"✅ Загружено {len(self.proxies)} прокси из {self.proxy_file}")
                random.shuffle(self.proxies)  # Перемешиваем для случайности
            else:
                print(f"⚠️ Файл {self.proxy_file} пуст или не содержит валидных прокси")
                
        except Exception as e:
            print(f"❌ Ошибка загрузки прокси: {str(e)}")
    
    def get_current_proxy(self) -> Optional[Dict[str, str]]:
        """Получить текущий прокси"""
        if not self.proxies or len(self.proxies) == len(self.failed_proxies):
            return None
        
        # Ищем рабочий прокси
        attempts = 0
        while attempts < len(self.proxies):
            proxy_url = self.proxies[self.current_proxy_index]
            
            if proxy_url not in self.failed_proxies:
                parsed = urlparse(proxy_url)
                return {
                    'http': proxy_url,
                    'https': proxy_url
                }
            
            self.switch_proxy()
            attempts += 1
        
        return None
    
    def switch_proxy(self):
        """Переключение на следующий прокси"""
        if self.proxies:
            self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)
    
    def mark_proxy_failed(self, proxy_url: str):
        """Отметить прокси как неработающий"""
        self.failed_proxies.add(proxy_url)
        print(f"❌ Прокси {proxy_url} помечен как неработающий")
    
    def get_random_proxy(self) -> Optional[Dict[str, str]]:
        """Получить случайный прокси"""
        if not self.proxies:
            return None
        
        available_proxies = [p for p in self.proxies if p not in self.failed_proxies]
        if not available_proxies:
            print("⚠️ Все прокси исчерпаны. Сброс списка неудачных прокси.")
            self.failed_proxies.clear()
            available_proxies = self.proxies
        
        if available_proxies:
            proxy_url = random.choice(available_proxies)
            return {
                'http': proxy_url,
                'https': proxy_url
            }
        
        return None

class CoinMarketCapClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://pro-api.coinmarketcap.com/v1"
        self.headers = {
            'Accepts': 'application/json',
            'X-CMC_PRO_API_KEY': api_key,
        }
        
        # Расширенный список стейблкоинов для фильтрации
        self.stablecoins = {
            'USDT', 'USDC', 'DAI', 'BUSD', 'TUSD', 'USDP', 'USDD', 'FRAX',
            'PYUSD', 'FDUSD', 'USDE', 'CRVUSD', 'LUSD', 'GUSD', 'SUSD',
            'ALUSD', 'MIM', 'USTC', 'VAI', 'DOLA', 'OUSD', 'MUSD', 'HUSD',
            'CUSD', 'RSRUSD', 'EURS', 'EURT', 'XSGD', 'GYEN', 'ZUSD',
            'STETH', 'WSTETH', 'RETH', 'CBETH', 'SFRXETH', 'RLUSD', 'USD1'
        }
    
    def get_top_listings(self, limit: int = 200) -> Dict[str, Any]:
        """Получить топ листинги по маркет капу"""
        url = f"{self.base_url}/cryptocurrency/listings/latest"
        parameters = {
            'start': '1',
            'limit': str(limit),
            'convert': 'USD',
            'sort': 'market_cap',
            'sort_dir': 'desc'
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=parameters, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status', {}).get('error_code') == 0:
                return data
            else:
                error_msg = data.get('status', {}).get('error_message', 'Unknown error')
                raise Exception(f"API Error: {error_msg}")
                
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {str(e)}")
        except json.JSONDecodeError as e:
            raise Exception(f"JSON decode error: {str(e)}")
    
    def filter_stablecoins(self, tokens: List[Dict]) -> List[Dict]:
        """Фильтрация стейблкоинов из списка токенов"""
        filtered_tokens = []
        
        for token in tokens:
            symbol = token.get('symbol', '').upper()
            name = token.get('name', '').upper()
            
            if symbol in self.stablecoins:
                continue
            
            if any(stable_word in name for stable_word in ['USD COIN', 'TETHER', 'DAI']):
                continue
            
            filtered_tokens.append(token)
        
        return filtered_tokens
    
    def get_top_100_non_stablecoins(self) -> List[Dict[str, Any]]:
        """Получить топ-100 токенов исключая стейблкоины"""
        try:
            print("📊 Получение данных из CoinMarketCap...")
            data = self.get_top_listings(limit=200)
            
            all_tokens = data.get('data', [])
            print(f"Получено {len(all_tokens)} токенов")
            
            filtered_tokens = self.filter_stablecoins(all_tokens)
            print(f"После фильтрации осталось {len(filtered_tokens)} токенов")
            
            top_100 = filtered_tokens[:100]
            
            result = []
            for i, token in enumerate(top_100, 1):
                quote = token.get('quote', {}).get('USD', {})
                
                token_info = {
                    'rank': i,
                    'original_rank': token.get('cmc_rank', 0),
                    'name': token.get('name', ''),
                    'symbol': token.get('symbol', ''),
                    'market_cap': quote.get('market_cap', 0),
                    'price': quote.get('price', 0),
                    'percent_change_24h': quote.get('percent_change_24h', 0),
                    'percent_change_7d': quote.get('percent_change_7d', 0),
                    'id': token.get('id', 0),
                    'slug': token.get('slug', '')
                }
                result.append(token_info)
            
            return result
            
        except Exception as e:
            print(f"❌ Ошибка при получении данных: {str(e)}")
            return []

class CoinPaprikaClient:
    def __init__(self, proxy_manager: ProxyManager):
        self.base_url = "https://api.coinpaprika.com/v1"
        self.proxy_manager = proxy_manager
        
    def _make_request_with_retries(self, url: str, params: Dict = None, max_retries: int = 3) -> Optional[requests.Response]:
        """Выполнить запрос с повторными попытками и сменой прокси"""
        
        for attempt in range(max_retries):
            # Каждый запрос получает свой прокси
            proxy = self.proxy_manager.get_random_proxy()
            
            try:
                session = requests.Session()
                if proxy:
                    session.proxies.update(proxy)
                
                response = session.get(url, params=params, timeout=15)
                
                if response.status_code == 402:  # Payment Required
                    if proxy:
                        current_proxy_url = list(proxy.values())[0]
                        self.proxy_manager.mark_proxy_failed(current_proxy_url)
                    time.sleep(random.uniform(1, 2))
                    continue
                
                elif response.status_code == 429:  # Too Many Requests
                    time.sleep(random.uniform(3, 6))
                    continue
                
                elif response.status_code == 403:  # Forbidden
                    if proxy:
                        current_proxy_url = list(proxy.values())[0]
                        self.proxy_manager.mark_proxy_failed(current_proxy_url)
                    continue
                
                response.raise_for_status()
                return response
                
            except (requests.exceptions.ProxyError, requests.exceptions.Timeout, 
                   requests.exceptions.RequestException):
                if proxy:
                    current_proxy_url = list(proxy.values())[0]
                    self.proxy_manager.mark_proxy_failed(current_proxy_url)
                
                if attempt < max_retries - 1:
                    time.sleep(random.uniform(0.5, 1))
        
        return None
        
    def find_coin_id(self, symbol: str) -> Optional[str]:
        """Найти ID монеты по символу в CoinPaprika"""
        try:
            url = f"{self.base_url}/coins"
            response = self._make_request_with_retries(url)
            
            if not response:
                return None
            
            coins = response.json()
            
            # Ищем активную монету с подходящим символом
            for coin in coins:
                if (coin.get('symbol', '').upper() == symbol.upper() and 
                    coin.get('is_active', False)):
                    return coin.get('id')
            
            return None
            
        except Exception as e:
            print(f"⚠️ Ошибка поиска ID для {symbol}: {str(e)}")
            return None
    
    def get_historical_data(self, coin_id: str, start_date: str, end_date: str) -> Optional[Dict]:
        """Получить исторические данные для монеты"""
        try:
            url = f"{self.base_url}/tickers/{coin_id}/historical"
            params = {
                'start': start_date,
                'end': end_date,
                'limit': 10,
                'interval': '1d'
            }
            
            response = self._make_request_with_retries(url, params)
            
            if not response:
                return None
            
            data = response.json()
            
            if not data or not isinstance(data, list):
                return None
            
            # Сортируем по дате
            data.sort(key=lambda x: x.get('timestamp', ''))
            
            # Фильтруем данные строго по диапазону дат
            filtered_data = []
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            
            for item in data:
                timestamp = item.get('timestamp', '')
                if timestamp:
                    item_date = datetime.strptime(timestamp.split('T')[0], '%Y-%m-%d')
                    if start_dt <= item_date <= end_dt:
                        filtered_data.append(item)
            
            if not filtered_data:
                return None
            
            prices = []
            dates = []
            market_caps = []
            volumes = []
            
            for item in filtered_data:
                prices.append(float(item.get('price', 0)))
                dates.append(item.get('timestamp', '').split('T')[0])
                market_caps.append(float(item.get('market_cap', 0)))
                volumes.append(float(item.get('volume_24h', 0)))
            
            return {
                'prices': prices,
                'dates': dates,
                'market_caps': market_caps,
                'volumes': volumes
            }
            
        except Exception as e:
            print(f"⚠️ Ошибка получения данных для {coin_id}: {str(e)}")
            return None

class FantasyCryptoRankSystem:
    def __init__(self, tokens_data: Dict[str, Dict]):
        """
        tokens_data: {
            'BTC': {
                'market_cap': 2060000000000,
                'prices': [100000, 101000, 99000, 102000, 103000],
                'name': 'Bitcoin'
            },
            ...
        }
        """
        self.tokens = tokens_data
        self.weekly_data = {}
        self.scores = {}
        
        # Инициализируем weekly_data из переданных данных
        for symbol, data in tokens_data.items():
            self.weekly_data[symbol] = {
                'market_cap': data['market_cap'],
                'prices': data['prices'],
                'name': data.get('name', symbol)
            }
    
    def calculate_mc_factor(self, market_cap: float, weekly_change: float) -> float:
        """
        Асимметричный MC фактор: 
        - При росте: обычная формула (market_cap_billions ** 0.15) * 12
        - При падении: обратная формула (market_cap_billions ** -0.15) * 12
        """
        market_cap_billions = market_cap / 1e9  # Приводим к миллиардам
        market_cap_billions = max(market_cap_billions, 0.001)  # Избегаем деления на ноль
        
        if weekly_change >= 0:
            # При росте - стандартный фактор
            return (market_cap_billions ** 0.15) * 12
        else:
            # При падении - обратный фактор (штраф для крупных токенов)
            return (market_cap_billions ** -0.05) * 12
    
    def calculate_daily_growth_bias(self, prices: List[float]) -> float:
        """Рассчитать bias роста за дни (активность/волатильность)"""
        if len(prices) < 2:
            return 0
        
        daily_changes = []
        for i in range(1, len(prices)):
            if prices[i-1] != 0:
                change = ((prices[i] - prices[i-1]) / prices[i-1]) * 100
                daily_changes.append(abs(change))
        
        return sum(daily_changes) if daily_changes else 0
    
    def calculate_rank_based_scores(self) -> Dict[str, Dict]:
        """Основная функция расчета скоров с ранжированием"""
        
        # 1. Собираем данные для ранжирования
        token_metrics = []
        
        for token, data in self.weekly_data.items():
            prices = data['prices']
            market_cap = data['market_cap']
            
            if len(prices) < 2:
                continue
                
            # Рассчитываем недельное изменение (с начала до конца периода)
            start_price = prices[0]
            end_price = prices[-1]
            weekly_change_pct = ((end_price - start_price) / start_price) * 100 if start_price > 0 else 0
            
            # Рассчитываем активность (волатильность)
            activity_score = self.calculate_daily_growth_bias(prices)
            
            token_metrics.append({
                'symbol': token,
                'weekly_change_pct': weekly_change_pct,
                'activity_score': activity_score,
                'market_cap': market_cap,
                'name': data['name'],
                'prices': prices
            })
        
        # 2. Ранжируем по недельному изменению (лучший = ранг 1)
        token_metrics.sort(key=lambda x: x['weekly_change_pct'], reverse=True)
        for i, token_data in enumerate(token_metrics):
            token_data['weekly_rank'] = i + 1
        
        # 3. Ранжируем по активности (самый активный = ранг 1)
        token_metrics.sort(key=lambda x: x['activity_score'], reverse=True)
        for i, token_data in enumerate(token_metrics):
            token_data['activity_rank'] = i + 1
        
        # 4. Рассчитываем очки и финальные скоры
        total_tokens = len(token_metrics)
        results = {}
        
        for token_data in token_metrics:
            symbol = token_data['symbol']
            weekly_change = token_data['weekly_change_pct']
            market_cap = token_data['market_cap']
            weekly_rank = token_data['weekly_rank']
            activity_rank = token_data['activity_rank']
            
            # Очки за ранг (чем лучше ранг, тем больше очков)
            weekly_rank_points = total_tokens - weekly_rank + 1  # 100 для 1-го места, 1 для 100-го
            activity_rank_points = total_tokens - activity_rank + 1
            
            # Применяем асимметричный MC фактор
            mc_factor = self.calculate_mc_factor(market_cap, weekly_change)
            
            # Итоговый raw score
            raw_score = (weekly_rank_points * mc_factor * 4) + (activity_rank_points * mc_factor * 1)
            
            results[symbol] = {
                'weekly_change_pct': weekly_change,
                'activity_score': token_data['activity_score'],
                'weekly_rank': weekly_rank,
                'activity_rank': activity_rank,
                'weekly_rank_points': weekly_rank_points,
                'activity_rank_points': activity_rank_points,
                'mc_factor': mc_factor,
                'raw_score': raw_score,
                'market_cap': market_cap,
                'name': token_data['name'],
                'prices': token_data['prices']
            }
        
        return results
    
    def balanced_normalize(self, scores: Dict[str, Dict]) -> Dict[str, Dict]:
        """Масштабирование скоров на основе реальных различий с декомпозицией"""
        
        # Сортируем по raw_score
        sorted_tokens = sorted(scores.items(), key=lambda x: x[1]['raw_score'], reverse=True)
        total_tokens = len(sorted_tokens)
        
        if not sorted_tokens:
            return scores
        
        # Получаем raw_score значения
        raw_scores = [data[1]['raw_score'] for data in sorted_tokens]
        max_raw = max(raw_scores)
        min_raw = min(raw_scores)
        raw_range = max_raw - min_raw
        
        for i, (symbol, data) in enumerate(sorted_tokens):
            rank = i + 1
            raw_score = data['raw_score']
            
            # Вычисляем компоненты raw_score
            weekly_component = data['weekly_rank_points'] * data['mc_factor'] * 4
            activity_component = data['activity_rank_points'] * data['mc_factor'] * 1
            
            if raw_range > 0:
                # Нормализуем raw_score от 0 до 1
                normalized = (raw_score - min_raw) / raw_range
                smooth_normalized = normalized ** 0.7
                final_score = int(1000 * smooth_normalized)
                
                # Пропорционально делим final_score между компонентами
                total_components = weekly_component + activity_component
                if total_components > 0:
                    weekly_score = int(final_score * (weekly_component / total_components))
                    activity_score = final_score - weekly_score
                else:
                    weekly_score = final_score // 2
                    activity_score = final_score // 2
                    
            else:
                # Если все raw_score одинаковые
                final_score = 500
                weekly_score = 250
                activity_score = 250
            
            scores[symbol].update({
                'final_rank': rank,
                'final_score': final_score,
                'weekly_score': weekly_score,
                'activity_score_points': activity_score,
                'card_weight': 50  # заглушка
            })
        
        return scores
    
    def calculate_daily_progression(self, tokens_data: Dict[str, Dict]) -> Dict[str, Dict]:
        """Рассчитать промежуточные скоры по дням"""
        daily_results = {}
        
        for symbol, data in tokens_data.items():
            prices = data['prices']
            if len(prices) < 2:
                continue
                
            daily_progression = []
            
            # Для каждого дня рассчитываем промежуточный результат
            for day in range(1, len(prices)):
                # Берем цены от начала до текущего дня
                partial_prices = prices[:day+1]
                
                # Рассчитываем изменение за этот период
                start_price = partial_prices[0]
                current_price = partial_prices[-1]
                partial_change = ((current_price - start_price) / start_price) * 100 if start_price > 0 else 0
                
                # Рассчитываем активность за период
                partial_activity = self.calculate_daily_growth_bias(partial_prices)
                
                daily_progression.append({
                    'day': day,
                    'change_pct': partial_change,
                    'activity': partial_activity,
                    'price': current_price
                })
            
            daily_results[symbol] = {
                'daily_progression': daily_progression,
                'final_data': data
            }
        
        return daily_results
    
    def run_simulation(self) -> Dict[str, Dict]:
        """Запуск полной симуляции с промежуточными результатами"""
        print("🔄 Расчет rank-based скоров...")
        raw_scores = self.calculate_rank_based_scores()
        
        print("⚖️ Нормализация скоров...")
        final_scores = self.balanced_normalize(raw_scores)
        
        print("📅 Расчет промежуточных результатов по дням...")
        daily_data = self.calculate_daily_progression(self.tokens)
        
        # Добавляем промежуточные данные в результаты
        for symbol in final_scores:
            if symbol in daily_data:
                final_scores[symbol]['daily_progression'] = daily_data[symbol]['daily_progression']
        
        return final_scores

def select_30_tokens_for_game(top_100: List[Dict]) -> List[str]:
    """Выбираем 30 токенов для игры: топ + середина + низ"""
    
    # Топ-10 (позиции 1-10)
    top_tokens = [token['symbol'] for token in top_100[:10]]
    
    # Середина (позиции 30-59) - выбираем 10
    middle_start = min(29, len(top_100) - 1)
    middle_end = min(59, len(top_100))
    middle_tokens = [token['symbol'] for token in top_100[middle_start:middle_end:3]][:10]
    
    # Нижняя часть (позиции 70-100) - выбираем 10
    bottom_start = min(69, len(top_100) - 1)
    bottom_tokens = [token['symbol'] for token in top_100[bottom_start::3]][:10]
    
    # Объединяем и берем ровно 30
    selected = (top_tokens + middle_tokens + bottom_tokens)[:30]
    
    print(f"🎯 Выбрано {len(selected)} токенов для игры:")
    print(f"   Топ-10: {', '.join(top_tokens)}")
    print(f"   Середина: {', '.join(middle_tokens)}")  
    print(f"   Низ: {', '.join(bottom_tokens)}")
    
    return selected

def create_sample_proxy_file():
    """Создать пример файла прокси"""
    sample_proxies = """# Пример файла прокси (proxies.txt)
# Поддерживаемые форматы:
# http://proxy_ip:port
# http://user:pass@proxy_ip:port
# https://proxy_ip:port
# proxy_ip:port (автоматически добавится http://)

# Примеры:
# 192.168.1.1:8080
# http://123.456.789.012:3128
# http://user:password@proxy.example.com:8080
# https://secure.proxy.com:8443

# Добавьте свои прокси ниже (по одному на строку):
"""
    
    if not os.path.exists("proxies.txt"):
        with open("proxies.txt", "w", encoding="utf-8") as f:
            f.write(sample_proxies)
        print("📝 Создан пример файла proxies.txt")
        print("   Добавьте в него свои прокси-серверы и перезапустите скрипт")

def process_single_token(args):
    """Обработка одного токена - для многопоточности"""
    token, coinpaprika_client, start_date, end_date = args
    symbol = token['symbol']
    
    try:
        # Находим ID
        coin_id = coinpaprika_client.find_coin_id(symbol)
        if not coin_id:
            return symbol, None, f"ID не найден"
        
        # Получаем исторические данные
        historical_data = coinpaprika_client.get_historical_data(coin_id, start_date, end_date)
        if historical_data and len(historical_data['prices']) > 0:
            result = {
                'market_cap': token['market_cap'],
                'prices': historical_data['prices'],
                'name': token['name'],
                'dates': historical_data['dates'],
                'volumes': historical_data['volumes']
            }
            return symbol, result, f"✅ {len(historical_data['prices'])} дней"
        else:
            return symbol, None, "Нет данных"
            
    except Exception as e:
        return symbol, None, f"Ошибка: {str(e)[:30]}..."

def main():
    # ВАЖНО: Замените на ваш реальный API ключ от CoinMarketCap
    CMC_API_KEY = "cc981d6b1e204a0e9edf9bc940a38f54"
    
    if CMC_API_KEY == "YOUR_API_KEY_HERE":
        print("❌ Необходимо указать реальный API ключ от CoinMarketCap!")
        print("Зарегистрируйтесь на https://coinmarketcap.com/api/ и получите бесплатный ключ")
        return
    
    # Создаем пример файла прокси если его нет
    create_sample_proxy_file()
    
    # Исправленные даты для получения ровно 5 дней (3-7 ноября включительно)
    start_date = "2025-11-03"
    end_date = "2025-11-07"
    
    print(f"🚀 Запуск полного анализа топ-100 токенов за период {start_date} - {end_date}")
    print("   📅 Ожидаем получить данные за 5 дней: 3, 4, 5, 6, 7 ноября")
    print("=" * 80)
    
    # Инициализируем менеджер прокси
    print("\n🌐 Инициализация прокси...")
    proxy_manager = ProxyManager("proxies.txt")
    
    # Инициализируем клиентов
    cmc_client = CoinMarketCapClient(CMC_API_KEY)
    coinpaprika_client = CoinPaprikaClient(proxy_manager)
    
    # 1. Получаем топ-100 токенов
    print("\n📊 Шаг 1: Получение топ-100 токенов...")
    top_100 = cmc_client.get_top_100_non_stablecoins()
    if not top_100:
        print("❌ Не удалось получить список токенов")
        return
    
    print(f"✅ Получен список из {len(top_100)} токенов")
    
    # 2. Выбираем 30 токенов для игры
    print("\n🎯 Шаг 2: Выбор 30 токенов для игры...")
    game_tokens = select_30_tokens_for_game(top_100)
    
    # Создаем словарь для быстрого поиска данных токенов
    token_lookup = {token['symbol']: token for token in top_100}
    
    # 3. Получаем исторические данные параллельно
    print(f"\n📈 Шаг 3: Параллельная загрузка исторических данных за {start_date} - {end_date}...")
    print("   🚀 Используем многопоточность для быстрой обработки 100 токенов...")
    
    all_historical_data = {}
    failed_tokens = []
    successful_requests = 0
    
    # Подготавливаем аргументы для каждого токена
    task_args = [(token, coinpaprika_client, start_date, end_date) for token in top_100]
    
    # Определяем количество потоков (не больше количества прокси)
    max_workers = min(50, len(proxy_manager.proxies) if proxy_manager.proxies else 10)
    print(f"   🔧 Запускаем {max_workers} параллельных потоков...")
    
    completed = 0
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Запускаем все задачи
        future_to_symbol = {executor.submit(process_single_token, args): args[0]['symbol'] 
                           for args in task_args}
        
        # Обрабатываем результаты по мере выполнения
        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            completed += 1
            
            try:
                symbol_result, data, status = future.result()
                
                # Обновляем прогресс
                progress = (completed / len(top_100)) * 100
                elapsed = time.time() - start_time
                eta = (elapsed / completed) * (len(top_100) - completed) if completed > 0 else 0
                
                print(f"\r[{completed:3d}/100] {progress:5.1f}% | {symbol:<8} {status:<20} | "
                      f"⏱️ {elapsed:.1f}s | ETA: {eta:.1f}s", end='', flush=True)
                
                if data:
                    all_historical_data[symbol_result] = data
                    successful_requests += 1
                else:
                    failed_tokens.append(symbol_result)
                    
            except Exception as e:
                failed_tokens.append(symbol)
                print(f"\n⚠️ Ошибка обработки {symbol}: {str(e)}")
    
    print()  # Новая строка после прогресс-бара
    
    total_time = time.time() - start_time
    success_rate = (successful_requests / len(top_100)) * 100
    
    print(f"\n🏁 Параллельная загрузка завершена за {total_time:.1f} секунд!")
    print(f"   ✅ Успешно: {successful_requests}/100 токенов ({success_rate:.1f}%)")
    print(f"   ❌ Неудачно: {len(failed_tokens)} токенов")
    print(f"   ⚡ Скорость: {successful_requests/total_time:.1f} токенов/сек")
    
    print()  # Новая строка после прогресс-бара
    
    
    if failed_tokens:
        print(f"   ⚠️ Токены без данных: {', '.join(failed_tokens[:15])}{'...' if len(failed_tokens) > 15 else ''}")
    
    if len(all_historical_data) < 30:
        print("❌ Критически мало исторических данных для качественного анализа")
        print(f"   Получено данных только для {len(all_historical_data)} токенов из {len(top_100)}")
        return
    
    # Проверяем качество данных
    data_quality_info = {}
    for symbol, data in all_historical_data.items():
        days_count = len(data['prices'])
        data_quality_info[days_count] = data_quality_info.get(days_count, 0) + 1
    
    print(f"\n📈 Качество исторических данных:")
    for days, count in sorted(data_quality_info.items(), reverse=True):
        print(f"   📅 {days} дней: {count} токенов")
    
    # 4. Запускаем симуляцию со всеми данными
    print(f"\n🎮 Шаг 4: Запуск симуляции с алгоритмом FantasyCryptoRankSystem...")
    print("=" * 60)
    print("   🔄 Расчет асимметричных MC-факторов...")
    print("   📊 Ранжирование по недельным изменениям и активности...")
    print("   ⚖️ Нормализация скоров в систему очков...")
    
    fantasy_system = FantasyCryptoRankSystem(all_historical_data)
    results = fantasy_system.run_simulation()
    
    if not results:
        print("❌ Не удалось выполнить симуляцию")
        return
    
    # 5. Анализируем результаты
    print(f"\n🏆 Шаг 5: Анализ результатов...")
    
    # Статистика по изменениям
    positive_changes = sum(1 for data in results.values() if data['weekly_change_pct'] > 0)
    negative_changes = len(results) - positive_changes
    
    changes = [data['weekly_change_pct'] for data in results.values()]
    avg_change = sum(changes) / len(changes) if changes else 0
    max_gain = max(changes) if changes else 0
    max_loss = min(changes) if changes else 0
    
    print(f"   📈 Токенов в плюсе: {positive_changes}")
    print(f"   📉 Токенов в минусе: {negative_changes}")
    print(f"   📊 Среднее изменение: {avg_change:+.2f}%")
    print(f"   🚀 Максимальный рост: {max_gain:+.2f}%")
    print(f"   💥 Максимальное падение: {max_loss:+.2f}%")
    
    # 6. Показываем результаты для всех токенов
    print(f"\n🏆 ПОЛНЫЕ РЕЗУЛЬТАТЫ СИМУЛЯЦИИ (ТОП-50)")
    print("=" * 110)
    print(f"{'Ранг':<4} {'Символ':<8} {'Название':<25} {'Изм %':<8} {'Активн':<8} {'Скор':<8} {'Вес':<4} {'MC Фактор':<10}")
    print("-" * 110)
    
    sorted_results = sorted(results.items(), key=lambda x: x[1]['final_rank'])
    
    for symbol, data in sorted_results[:50]:  # Показываем топ-50
        name_truncated = data['name'][:24] + "…" if len(data['name']) > 24 else data['name']
        print(f"{data['final_rank']:<4} {symbol:<8} {name_truncated:<25} "
              f"{data['weekly_change_pct']:+6.2f}% {data['activity_score']:<8.1f} "
              f"{data['final_score']:<8.0f} {data['card_weight']:<4} {data['mc_factor']:<10.2f}")
    
    if len(sorted_results) > 50:
        print(f"   ... и еще {len(sorted_results) - 50} токенов")
    
    # 7. Показываем результаты только для игровых токенов
    print(f"\n🎯 РЕЗУЛЬТАТЫ ДЛЯ ИГРОВЫХ ТОКЕНОВ (30 штук)")
    print("="*180)
    print(f"{'Общий':<6} {'Игр.':<4} {'Символ':<8} {'Название':<25} {'Маркет кап':<12} {'Изм %':<8} {'Ранг':<4} {'За рост':<8} {'За акт':<7} {'Ранг':<4} {'Скор':<6} {'Вес':<4}")
    print(f"{'ранг':<6} {'ранг':<4} {'':<8} {'':<25} {'':<12} {'':<8} {'рост':<4} {'очки':<8} {'очки':<7} {'акт':<4} {'':<6} {'':<4}")
    print("-"*180)

    game_results = []
    for symbol, data in results.items():
        if symbol in game_tokens:
            game_results.append((symbol, data))

    # Сортируем игровые результаты по общему рангу
    game_results.sort(key=lambda x: x[1]['final_rank'])

    for game_rank, (symbol, data) in enumerate(game_results, 1):
        name_truncated = data['name'][:24] + "…" if len(data['name']) > 24 else data['name']
        
        # Форматируем маркет кап
        mc = data['market_cap']
        if mc >= 1e12:
            mc_str = f"${mc/1e12:.1f}T"
        elif mc >= 1e9:
            mc_str = f"${mc/1e9:.1f}B"
        elif mc >= 1e6:
            mc_str = f"${mc/1e6:.0f}M"
        else:
            mc_str = f"${mc:.0f}"
        
        print(f"{data['final_rank']:<6} {game_rank:<4} {symbol:<8} {name_truncated:<25} "
            f"{mc_str:<12} {data['weekly_change_pct']:+6.2f}% {data['weekly_rank']:<4} "
            f"{data['weekly_score']:<8} {data['activity_score_points']:<7} {data['activity_rank']:<4} "
            f"{data['final_score']:<6} {data['card_weight']:<4}")

    # 8. Показываем промежуточные результаты по дням для топ-10 игровых токенов
    print(f"\n📅 ПРОМЕЖУТОЧНЫЕ РЕЗУЛЬТАТЫ ПО ДНЯМ (ТОП-10 ИГРОВЫХ ТОКЕНОВ)")
    print("="*120)

    top_10_game = game_results[:10]
    for i, (symbol, data) in enumerate(top_10_game, 1):
        print(f"\n{i:2d}. {symbol} - {data['name']}")
        print("-" * 80)
        
        if 'daily_progression' in data:
            print(f"{'День':<4} {'Цена':<12} {'Изм %':<8} {'Активность':<12} {'Статус':<20}")
            print("-" * 80)
            
            for day_data in data['daily_progression']:
                day = day_data['day']
                price = day_data['price']
                change = day_data['change_pct']
                activity = day_data['activity']
                
                # Определяем статус
                if change > 5:
                    status = "🚀 Сильный рост"
                elif change > 0:
                    status = "📈 Рост"
                elif change > -5:
                    status = "📉 Падение"
                else:
                    status = "💥 Сильное падение"
                
                print(f"{day:<4} ${price:<11.4f} {change:+6.2f}% {activity:<12.1f} {status}")
        else:
            print("   Нет промежуточных данных")
    
    # 9. Сохраняем результаты
    print(f"\n💾 Шаг 6: Сохранение результатов...")
    os.makedirs('crypto_game_results', exist_ok=True)
    
    # Сохраняем все результаты
    all_results_export = {}
    for symbol, data in results.items():
        # Убираем объекты, которые не сериализуются в JSON
        export_data = {k: v for k, v in data.items() if k != 'prices'}
        all_results_export[symbol] = export_data
    
    with open('crypto_game_results/all_results.json', 'w', encoding='utf-8') as f:
        json.dump(all_results_export, f, indent=2, ensure_ascii=False, default=str)
    
    # Сохраняем игровые токены отдельно
    game_only_results = {symbol: all_results_export[symbol] for symbol, data in results.items() if symbol in game_tokens}
    with open('crypto_game_results/game_tokens_results.json', 'w', encoding='utf-8') as f:
        json.dump(game_only_results, f, indent=2, ensure_ascii=False, default=str)
    
    # Сохраняем исторические данные
    with open('crypto_game_results/historical_data.json', 'w', encoding='utf-8') as f:
        json.dump(all_historical_data, f, indent=2, ensure_ascii=False, default=str)
    
    # Сохраняем список игровых токенов
    game_tokens_info = []
    for symbol in game_tokens:
        if symbol in token_lookup:
            token_info = token_lookup[symbol].copy()
            if symbol in results:
                token_info.update({
                    'game_rank': next(i for i, (s, _) in enumerate(game_results, 1) if s == symbol),
                    'final_score': results[symbol]['final_score'],
                    'weekly_change_pct': results[symbol]['weekly_change_pct']
                })
            game_tokens_info.append(token_info)
    
    with open('crypto_game_results/selected_game_tokens.json', 'w', encoding='utf-8') as f:
        json.dump(game_tokens_info, f, indent=2, ensure_ascii=False, default=str)
    
    # Создаем подробный CSV для анализа
    csv_data = []
    for symbol, data in results.items():
        row = {
            'symbol': symbol,
            'name': data['name'],
            'overall_rank': data['final_rank'],
            'weekly_change_pct': data['weekly_change_pct'],
            'activity_score': data['activity_score'],
            'weekly_rank': data['weekly_rank'],
            'activity_rank': data['activity_rank'],
            'weekly_rank_points': data['weekly_rank_points'],
            'activity_rank_points': data['activity_rank_points'],
            'mc_factor': data['mc_factor'],
            'raw_score': data['raw_score'],
            'final_score': data['final_score'],
            'card_weight': data['card_weight'],
            'market_cap': data['market_cap'],
            'in_game': symbol in game_tokens,
            'game_rank': next((i for i, (s, _) in enumerate(game_results, 1) if s == symbol), None) if symbol in game_tokens else None
        }
        csv_data.append(row)
    
    df = pd.DataFrame(csv_data)
    df.to_csv('crypto_game_results/detailed_simulation_results.csv', index=False)
    
    # Создаем упрощенный CSV только для игровых токенов
    game_csv_data = []
    for i, (symbol, data) in enumerate(game_results, 1):
        row = {
            'game_rank': i,
            'symbol': symbol,
            'name': data['name'],
            'overall_rank': data['final_rank'],
            'weekly_change_pct': data['weekly_change_pct'],
            'final_score': data['final_score'],
            'card_weight': data['card_weight'],
            'market_cap': data['market_cap']
        }
        game_csv_data.append(row)
    
    game_df = pd.DataFrame(game_csv_data)
    game_df.to_csv('crypto_game_results/game_tokens_only.csv', index=False)
    
    print(f"✅ Результаты сохранены в папку 'crypto_game_results/':")
    print(f"   📊 all_results.json - полные результаты всех токенов")
    print(f"   🎯 game_tokens_results.json - результаты только игровых токенов")
    print(f"   📈 historical_data.json - исторические данные цен")
    print(f"   📝 selected_game_tokens.json - информация о выбранных игровых токенах")
    print(f"   📋 detailed_simulation_results.csv - подробный CSV для анализа")
    print(f"   🎮 game_tokens_only.csv - упрощенный CSV только игровых токенов")
    
    # 10. Итоговая статистика и рекомендации
    print(f"\n📈 ИТОГОВАЯ СТАТИСТИКА И ВЫВОДЫ")
    print("=" * 60)
    
    # Топ-5 игровых токенов
    top_5_game = game_results[:5]
    print("🏆 Топ-5 игровых токенов по итоговому скору:")
    for i, (symbol, data) in enumerate(top_5_game, 1):
        trend_emoji = "📈" if data['weekly_change_pct'] > 0 else "📉"
        print(f"  {i}. {symbol} ({data['name'][:20]}...)")
        print(f"      {trend_emoji} {data['weekly_change_pct']:+.2f}% | "
              f"🏆 {data['final_score']:.0f} очков | ⚖️ Вес {data['card_weight']}")
    
    # Худшие 3 игровых токена
    worst_3_game = game_results[-3:]
    print(f"\n📉 Худшие 3 игровых токена:")
    for i, (symbol, data) in enumerate(worst_3_game, len(game_results) - 2):
        trend_emoji = "📈" if data['weekly_change_pct'] > 0 else "📉"
        print(f"  {i}. {symbol} ({data['name'][:20]}...)")
        print(f"      {trend_emoji} {data['weekly_change_pct']:+.2f}% | "
              f"🏆 {data['final_score']:.0f} очков | ⚖️ Вес {data['card_weight']}")
    
    # Статистика по категориям токенов
    print(f"\n📊 Распределение игровых токенов по рангам:")
    rank_categories = {
        'Топ-10 (1-10 ранг)': len([s for s, d in game_results if d['final_rank'] <= 10]),
        'Середина (11-50 ранг)': len([s for s, d in game_results if 11 <= d['final_rank'] <= 50]),
        'Низ (51+ ранг)': len([s for s, d in game_results if d['final_rank'] > 50])
    }
    
    for category, count in rank_categories.items():
        print(f"   {category}: {count} токенов")
    
    # Рекомендации для игры
    print(f"\n🎯 РЕКОМЕНДАЦИИ ДЛЯ ИГРЫ:")
    print("-" * 40)
    print("✅ Система готова для запуска реальной игры")
    print(f"📊 Обработано {len(results)} токенов, выбрано {len(game_tokens)} для игры")
    print(f"🎮 Качество данных: {success_rate:.1f}% успешных запросов")
    
    # Самые перспективные токены
    high_potential = [s for s, d in game_results[:10] if d['weekly_change_pct'] > avg_change]
    if high_potential:
        print(f"🚀 Высокопотенциальные токены: {', '.join(high_potential[:5])}")
    
    # Самые стабильные токены
    stable_tokens = [s for s, d in game_results if d['activity_score'] < 10 and d['weekly_change_pct'] > 0]
    if stable_tokens:
        print(f"🛡️ Стабильные токены: {', '.join(stable_tokens[:3])}")
    
    print(f"\n🎊 Анализ успешно завершен!")
    print(f"📁 Все данные сохранены в папке 'crypto_game_results/'")
    print(f"🚀 Система готова для реального использования!")

if __name__ == "__main__":
    main()