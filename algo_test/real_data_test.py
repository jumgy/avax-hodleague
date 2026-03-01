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
        """Load proxies from file."""
        if not os.path.exists(self.proxy_file):
            print(f"[WARNING] File {self.proxy_file} not found. Running without proxy.")
            return
        
        try:
            with open(self.proxy_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Support various proxy formats.
                    if '://' not in line:
                        # Add http:// if no protocol.
                        proxy_url = f"http://{line}"
                    else:
                        proxy_url = line
                    
                    self.proxies.append(proxy_url)
            
            if self.proxies:
                print(f"[OK] Loaded {len(self.proxies)} proxies from {self.proxy_file}")
                random.shuffle(self.proxies)
            else:
                print(f"[WARNING] File {self.proxy_file} is empty or has no valid proxies")

        except Exception as e:
            print(f"[ERROR] Proxy load error: {e}")
    
    def get_current_proxy(self) -> Optional[Dict[str, str]]:
        """Get current proxy."""
        if not self.proxies or len(self.proxies) == len(self.failed_proxies):
            return None

        # Find working proxy.
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
        """Switch to next proxy."""
        if self.proxies:
            self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)
    
    def mark_proxy_failed(self, proxy_url: str):
        """Mark proxy as failed."""
        self.failed_proxies.add(proxy_url)
        print(f"[ERROR] Proxy {proxy_url} marked as failed")
    
    def get_random_proxy(self) -> Optional[Dict[str, str]]:
        """Get random proxy."""
        if not self.proxies:
            return None

        available_proxies = [p for p in self.proxies if p not in self.failed_proxies]
        if not available_proxies:
            print("[WARNING] All proxies exhausted. Resetting failed list.")
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
        
        # Extended list of stablecoins for filtering.
        self.stablecoins = {
            'USDT', 'USDC', 'DAI', 'BUSD', 'TUSD', 'USDP', 'USDD', 'FRAX',
            'PYUSD', 'FDUSD', 'USDE', 'CRVUSD', 'LUSD', 'GUSD', 'SUSD',
            'ALUSD', 'MIM', 'USTC', 'VAI', 'DOLA', 'OUSD', 'MUSD', 'HUSD',
            'CUSD', 'RSRUSD', 'EURS', 'EURT', 'XSGD', 'GYEN', 'ZUSD',
            'STETH', 'WSTETH', 'RETH', 'CBETH', 'SFRXETH', 'RLUSD', 'USD1'
        }
    
    def get_top_listings(self, limit: int = 200) -> Dict[str, Any]:
        """Get top listings by market cap."""
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
        """Filter stablecoins from token list."""
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
        """Get top 100 tokens excluding stablecoins."""
        try:
            print("Fetching data from CoinMarketCap...")
            data = self.get_top_listings(limit=200)

            all_tokens = data.get('data', [])
            print(f"Received {len(all_tokens)} tokens")

            filtered_tokens = self.filter_stablecoins(all_tokens)
            print(f"After filtering: {len(filtered_tokens)} tokens")
            
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
            print(f"[ERROR] Failed to get data: {e}")
            return []

class CoinPaprikaClient:
    def __init__(self, proxy_manager: ProxyManager):
        self.base_url = "https://api.coinpaprika.com/v1"
        self.proxy_manager = proxy_manager
        
    def _make_request_with_retries(self, url: str, params: Dict = None, max_retries: int = 3) -> Optional[requests.Response]:
        """Execute request with retries and proxy rotation."""

        for attempt in range(max_retries):
            # Each request gets its own proxy.
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
        """Find coin ID by symbol in CoinPaprika."""
        try:
            url = f"{self.base_url}/coins"
            response = self._make_request_with_retries(url)
            
            if not response:
                return None
            
            coins = response.json()
            
            # Find active coin with matching symbol.
            for coin in coins:
                if (coin.get('symbol', '').upper() == symbol.upper() and 
                    coin.get('is_active', False)):
                    return coin.get('id')
            
            return None
            
        except Exception as e:
            print(f"[WARNING] Error finding ID for {symbol}: {e}")
            return None

    def get_historical_data(self, coin_id: str, start_date: str, end_date: str) -> Optional[Dict]:
        """Get historical data for coin."""
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
            
            # Sort by date.
            data.sort(key=lambda x: x.get('timestamp', ''))

            # Filter data strictly by date range.
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
            print(f"[WARNING] Error getting data for {coin_id}: {e}")
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
        
        # Initialize weekly_data from passed data.
        for symbol, data in tokens_data.items():
            self.weekly_data[symbol] = {
                'market_cap': data['market_cap'],
                'prices': data['prices'],
                'name': data.get('name', symbol)
            }
    
    def calculate_mc_factor(self, market_cap: float, weekly_change: float) -> float:
        """
        Asymmetric MC factor:
        - On growth: (market_cap_billions ** 0.15) * 12
        - On decline: (market_cap_billions ** -0.15) * 12
        """
        market_cap_billions = market_cap / 1e9
        market_cap_billions = max(market_cap_billions, 0.001)

        if weekly_change >= 0:
            return (market_cap_billions ** 0.15) * 12
        else:
            return (market_cap_billions ** -0.05) * 12
    
    def calculate_daily_growth_bias(self, prices: List[float]) -> float:
        """Calculate growth bias over days (activity/volatility)."""
        if len(prices) < 2:
            return 0
        
        daily_changes = []
        for i in range(1, len(prices)):
            if prices[i-1] != 0:
                change = ((prices[i] - prices[i-1]) / prices[i-1]) * 100
                daily_changes.append(abs(change))
        
        return sum(daily_changes) if daily_changes else 0
    
    def calculate_rank_based_scores(self) -> Dict[str, Dict]:
        """Main rank-based score calculation."""

        # 1. Gather data for ranking.
        token_metrics = []
        
        for token, data in self.weekly_data.items():
            prices = data['prices']
            market_cap = data['market_cap']
            
            if len(prices) < 2:
                continue
                
            # Weekly change (start to end of period).
            start_price = prices[0]
            end_price = prices[-1]
            weekly_change_pct = ((end_price - start_price) / start_price) * 100 if start_price > 0 else 0
            
            # Activity (volatility).
            activity_score = self.calculate_daily_growth_bias(prices)
            
            token_metrics.append({
                'symbol': token,
                'weekly_change_pct': weekly_change_pct,
                'activity_score': activity_score,
                'market_cap': market_cap,
                'name': data['name'],
                'prices': prices
            })
        
        # 2. Rank by weekly change (best = rank 1).
        token_metrics.sort(key=lambda x: x['weekly_change_pct'], reverse=True)
        for i, token_data in enumerate(token_metrics):
            token_data['weekly_rank'] = i + 1
        
        # 3. Rank by activity (most active = rank 1).
        token_metrics.sort(key=lambda x: x['activity_score'], reverse=True)
        for i, token_data in enumerate(token_metrics):
            token_data['activity_rank'] = i + 1
        
        # 4. Calculate points and final scores.
        total_tokens = len(token_metrics)
        results = {}
        
        for token_data in token_metrics:
            symbol = token_data['symbol']
            weekly_change = token_data['weekly_change_pct']
            market_cap = token_data['market_cap']
            weekly_rank = token_data['weekly_rank']
            activity_rank = token_data['activity_rank']
            
            # Points by rank (better rank = more points).
            weekly_rank_points = total_tokens - weekly_rank + 1
            activity_rank_points = total_tokens - activity_rank + 1

            mc_factor = self.calculate_mc_factor(market_cap, weekly_change)

            # Final raw score.
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
        """Scale scores based on real differences with decomposition."""

        # Sort by raw_score.
        sorted_tokens = sorted(scores.items(), key=lambda x: x[1]['raw_score'], reverse=True)
        total_tokens = len(sorted_tokens)
        
        if not sorted_tokens:
            return scores
        
        # Get raw_score values.
        raw_scores = [data[1]['raw_score'] for data in sorted_tokens]
        max_raw = max(raw_scores)
        min_raw = min(raw_scores)
        raw_range = max_raw - min_raw
        
        for i, (symbol, data) in enumerate(sorted_tokens):
            rank = i + 1
            raw_score = data['raw_score']
            
            # Compute raw_score components.
            weekly_component = data['weekly_rank_points'] * data['mc_factor'] * 4
            activity_component = data['activity_rank_points'] * data['mc_factor'] * 1
            
            if raw_range > 0:
                # Normalize raw_score 0 to 1.
                normalized = (raw_score - min_raw) / raw_range
                smooth_normalized = normalized ** 0.7
                final_score = int(1000 * smooth_normalized)
                
                # Split final_score between components proportionally.
                total_components = weekly_component + activity_component
                if total_components > 0:
                    weekly_score = int(final_score * (weekly_component / total_components))
                    activity_score = final_score - weekly_score
                else:
                    weekly_score = final_score // 2
                    activity_score = final_score // 2
                    
            else:
                # All raw_scores equal.
                final_score = 500
                weekly_score = 250
                activity_score = 250
            
            scores[symbol].update({
                'final_rank': rank,
                'final_score': final_score,
                'weekly_score': weekly_score,
                'activity_score_points': activity_score,
                'card_weight': 50  # placeholder
            })
        
        return scores
    
    def calculate_daily_progression(self, tokens_data: Dict[str, Dict]) -> Dict[str, Dict]:
        """Calculate intermediate scores by day."""
        daily_results = {}
        
        for symbol, data in tokens_data.items():
            prices = data['prices']
            if len(prices) < 2:
                continue
                
            daily_progression = []
            
            # For each day compute intermediate result.
            for day in range(1, len(prices)):
                # Prices from start to current day.
                partial_prices = prices[:day+1]
                
                # Change over this period.
                start_price = partial_prices[0]
                current_price = partial_prices[-1]
                partial_change = ((current_price - start_price) / start_price) * 100 if start_price > 0 else 0
                
                # Activity over period.
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
        """Run full simulation with intermediate results."""
        print("Calculating rank-based scores...")
        raw_scores = self.calculate_rank_based_scores()

        print("Normalizing scores...")
        final_scores = self.balanced_normalize(raw_scores)

        print("Calculating daily progression...")
        daily_data = self.calculate_daily_progression(self.tokens)

        # Add intermediate data to results.
        for symbol in final_scores:
            if symbol in daily_data:
                final_scores[symbol]['daily_progression'] = daily_data[symbol]['daily_progression']
        
        return final_scores

def select_30_tokens_for_game(top_100: List[Dict]) -> List[str]:
    """Select 30 tokens for game: top + middle + bottom."""

    # Top 10 (positions 1-10).
    top_tokens = [token['symbol'] for token in top_100[:10]]
    
    # Middle (positions 30-59), pick 10.
    middle_start = min(29, len(top_100) - 1)
    middle_end = min(59, len(top_100))
    middle_tokens = [token['symbol'] for token in top_100[middle_start:middle_end:3]][:10]
    
    # Bottom (positions 70-100), pick 10.
    bottom_start = min(69, len(top_100) - 1)
    bottom_tokens = [token['symbol'] for token in top_100[bottom_start::3]][:10]
    
    # Combine and take exactly 30.
    selected = (top_tokens + middle_tokens + bottom_tokens)[:30]

    print(f"Selected {len(selected)} tokens for game:")
    print(f"   Top 10: {', '.join(top_tokens)}")
    print(f"   Middle: {', '.join(middle_tokens)}")
    print(f"   Bottom: {', '.join(bottom_tokens)}")
    
    return selected

def create_sample_proxy_file():
    """Create sample proxy file."""
    sample_proxies = """# Sample proxy file (proxies.txt)
# Supported formats:
# http://proxy_ip:port
# http://user:pass@proxy_ip:port
# https://proxy_ip:port
# proxy_ip:port (http:// will be added automatically)

# Examples:
# 192.168.1.1:8080
# http://123.456.789.012:3128
# http://user:password@proxy.example.com:8080
# https://secure.proxy.com:8443

# Add your proxies below (one per line):
"""

    if not os.path.exists("proxies.txt"):
        with open("proxies.txt", "w", encoding="utf-8") as f:
            f.write(sample_proxies)
        print("Created sample file proxies.txt")
        print("   Add your proxy servers and restart the script")

def process_single_token(args):
    """Process single token (for multithreading)."""
    token, coinpaprika_client, start_date, end_date = args
    symbol = token['symbol']
    
    try:
        # Find ID.
        coin_id = coinpaprika_client.find_coin_id(symbol)
        if not coin_id:
            return symbol, None, "ID not found"

        # Get historical data.
        historical_data = coinpaprika_client.get_historical_data(coin_id, start_date, end_date)
        if historical_data and len(historical_data['prices']) > 0:
            result = {
                'market_cap': token['market_cap'],
                'prices': historical_data['prices'],
                'name': token['name'],
                'dates': historical_data['dates'],
                'volumes': historical_data['volumes']
            }
            return symbol, result, f"{len(historical_data['prices'])} days"
        else:
            return symbol, None, "No data"

    except Exception as e:
        return symbol, None, f"Error: {str(e)[:30]}..."

def main():
    # Replace with your real CoinMarketCap API key.
    CMC_API_KEY = "cc981d6b1e204a0e9edf9bc940a38f54"

    if CMC_API_KEY == "YOUR_API_KEY_HERE":
        print("[ERROR] Set a real CoinMarketCap API key.")
        print("Register at https://coinmarketcap.com/api/ and get a free key")
        return

    # Create sample proxy file if missing.
    create_sample_proxy_file()
    
    start_date = "2025-11-03"
    end_date = "2025-11-07"

    print(f"Running full top-100 token analysis for {start_date} - {end_date}")
    print("   Expecting 5 days of data: Nov 3, 4, 5, 6, 7")
    print("=" * 80)

    print("\nInitializing proxy...")
    proxy_manager = ProxyManager("proxies.txt")
    
    cmc_client = CoinMarketCapClient(CMC_API_KEY)
    coinpaprika_client = CoinPaprikaClient(proxy_manager)

    # 1. Get top 100 tokens.
    print("\nStep 1: Fetching top 100 tokens...")
    top_100 = cmc_client.get_top_100_non_stablecoins()
    if not top_100:
        print("[ERROR] Failed to get token list")
        return

    print(f"[OK] Got list of {len(top_100)} tokens")

    # 2. Select 30 tokens for game.
    print("\nStep 2: Selecting 30 tokens for game...")
    game_tokens = select_30_tokens_for_game(top_100)
    
    token_lookup = {token['symbol']: token for token in top_100}

    # 3. Fetch historical data in parallel.
    print(f"\nStep 3: Parallel load of historical data for {start_date} - {end_date}...")
    print("   Using multithreading for 100 tokens...")
    
    all_historical_data = {}
    failed_tokens = []
    successful_requests = 0
    
    task_args = [(token, coinpaprika_client, start_date, end_date) for token in top_100]

    max_workers = min(50, len(proxy_manager.proxies) if proxy_manager.proxies else 10)
    print(f"   Starting {max_workers} parallel threads...")
    
    completed = 0
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_symbol = {executor.submit(process_single_token, args): args[0]['symbol']
                           for args in task_args}

        # Process results as they complete.
        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            completed += 1
            
            try:
                symbol_result, data, status = future.result()
                
                progress = (completed / len(top_100)) * 100
                elapsed = time.time() - start_time
                eta = (elapsed / completed) * (len(top_100) - completed) if completed > 0 else 0

                print(f"\r[{completed:3d}/100] {progress:5.1f}% | {symbol:<8} {status:<20} | "
                      f"{elapsed:.1f}s | ETA: {eta:.1f}s", end='', flush=True)
                
                if data:
                    all_historical_data[symbol_result] = data
                    successful_requests += 1
                else:
                    failed_tokens.append(symbol_result)
                    
            except Exception as e:
                failed_tokens.append(symbol)
                print(f"\n[WARNING] Error processing {symbol}: {e}")

    print()

    total_time = time.time() - start_time
    success_rate = (successful_requests / len(top_100)) * 100

    print(f"\nParallel load completed in {total_time:.1f}s")
    print(f"   Success: {successful_requests}/100 tokens ({success_rate:.1f}%)")
    print(f"   Failed: {len(failed_tokens)} tokens")
    print(f"   Rate: {successful_requests/total_time:.1f} tokens/s")

    print()

    if failed_tokens:
        print(f"   Tokens without data: {', '.join(failed_tokens[:15])}{'...' if len(failed_tokens) > 15 else ''}")

    if len(all_historical_data) < 30:
        print("[ERROR] Too little historical data for analysis")
        print(f"   Got data for only {len(all_historical_data)} tokens out of {len(top_100)}")
        return
    
    # Data quality.
    data_quality_info = {}
    for symbol, data in all_historical_data.items():
        days_count = len(data['prices'])
        data_quality_info[days_count] = data_quality_info.get(days_count, 0) + 1
    
    print("\nHistorical data quality:")
    for days, count in sorted(data_quality_info.items(), reverse=True):
        print(f"   {days} days: {count} tokens")

    # 4. Run simulation with all data.
    print("\nStep 4: Running FantasyCryptoRankSystem simulation...")
    print("=" * 60)
    print("   Calculating asymmetric MC factors...")
    print("   Ranking by weekly change and activity...")
    print("   Normalizing scores...")
    
    fantasy_system = FantasyCryptoRankSystem(all_historical_data)
    results = fantasy_system.run_simulation()
    
    if not results:
        print("[ERROR] Simulation failed")
        return

    # 5. Analyze results.
    print("\nStep 5: Analyzing results...")

    # Change statistics.
    positive_changes = sum(1 for data in results.values() if data['weekly_change_pct'] > 0)
    negative_changes = len(results) - positive_changes
    
    changes = [data['weekly_change_pct'] for data in results.values()]
    avg_change = sum(changes) / len(changes) if changes else 0
    max_gain = max(changes) if changes else 0
    max_loss = min(changes) if changes else 0
    
    print(f"   Tokens in plus: {positive_changes}")
    print(f"   Tokens in minus: {negative_changes}")
    print(f"   Avg change: {avg_change:+.2f}%")
    print(f"   Max gain: {max_gain:+.2f}%")
    print(f"   Max loss: {max_loss:+.2f}%")

    # 6. Show results for all tokens.
    print("\nFULL SIMULATION RESULTS (TOP 50)")
    print("=" * 110)
    print(f"{'Rank':<4} {'Symbol':<8} {'Name':<25} {'Chg %':<8} {'Activ':<8} {'Score':<8} {'Wgt':<4} {'MC Factor':<10}")
    print("-" * 110)
    
    sorted_results = sorted(results.items(), key=lambda x: x[1]['final_rank'])
    
    for symbol, data in sorted_results[:50]:
        name_truncated = data['name'][:24] + "…" if len(data['name']) > 24 else data['name']
        print(f"{data['final_rank']:<4} {symbol:<8} {name_truncated:<25} "
              f"{data['weekly_change_pct']:+6.2f}% {data['activity_score']:<8.1f} "
              f"{data['final_score']:<8.0f} {data['card_weight']:<4} {data['mc_factor']:<10.2f}")
    
    if len(sorted_results) > 50:
        print(f"   ... and {len(sorted_results) - 50} more tokens")

    # 7. Results for game tokens only.
    print("\nRESULTS FOR GAME TOKENS (30)")
    print("=" * 180)
    print(f"{'Overall':<6} {'Game':<4} {'Symbol':<8} {'Name':<25} {'Market cap':<12} {'Chg %':<8} {'Rank':<4} {'Growth':<8} {'Activ':<7} {'Rank':<4} {'Score':<6} {'Wgt':<4}")
    print(f"{'rank':<6} {'rank':<4} {'':<8} {'':<25} {'':<12} {'':<8} {'chg':<4} {'pts':<8} {'pts':<7} {'act':<4} {'':<6} {'':<4}")
    print("-"*180)

    game_results = []
    for symbol, data in results.items():
        if symbol in game_tokens:
            game_results.append((symbol, data))

    # Sort game results by overall rank.
    game_results.sort(key=lambda x: x[1]['final_rank'])

    for game_rank, (symbol, data) in enumerate(game_results, 1):
        name_truncated = data['name'][:24] + "…" if len(data['name']) > 24 else data['name']
        
        # Format market cap.
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

    # 8. Daily progression for top 10 game tokens.
    print("\nDAILY PROGRESSION (TOP 10 GAME TOKENS)")
    print("="*120)

    top_10_game = game_results[:10]
    for i, (symbol, data) in enumerate(top_10_game, 1):
        print(f"\n{i:2d}. {symbol} - {data['name']}")
        print("-" * 80)
        
        if 'daily_progression' in data:
            print(f"{'Day':<4} {'Price':<12} {'Chg %':<8} {'Activity':<12} {'Status':<20}")
            print("-" * 80)
            
            for day_data in data['daily_progression']:
                day = day_data['day']
                price = day_data['price']
                change = day_data['change_pct']
                activity = day_data['activity']
                
                if change > 5:
                    status = "Strong growth"
                elif change > 0:
                    status = "Growth"
                elif change > -5:
                    status = "Decline"
                else:
                    status = "Strong decline"
                
                print(f"{day:<4} ${price:<11.4f} {change:+6.2f}% {activity:<12.1f} {status}")
        else:
            print("   No intermediate data")

    # 9. Save results.
    print("\nStep 6: Saving results...")
    os.makedirs('crypto_game_results', exist_ok=True)
    
    # Save all results.
    all_results_export = {}
    for symbol, data in results.items():
        # Remove non-JSON-serializable fields.
        export_data = {k: v for k, v in data.items() if k != 'prices'}
        all_results_export[symbol] = export_data
    
    with open('crypto_game_results/all_results.json', 'w', encoding='utf-8') as f:
        json.dump(all_results_export, f, indent=2, ensure_ascii=False, default=str)
    
    # Save game tokens separately.
    game_only_results = {symbol: all_results_export[symbol] for symbol, data in results.items() if symbol in game_tokens}
    with open('crypto_game_results/game_tokens_results.json', 'w', encoding='utf-8') as f:
        json.dump(game_only_results, f, indent=2, ensure_ascii=False, default=str)
    
    # Save historical data.
    with open('crypto_game_results/historical_data.json', 'w', encoding='utf-8') as f:
        json.dump(all_historical_data, f, indent=2, ensure_ascii=False, default=str)
    
    # Save game token list.
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
    
    # Detailed CSV for analysis.
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
    
    # Simplified CSV for game tokens only.
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
    
    print("Results saved to 'crypto_game_results/':")
    print("   all_results.json - full results for all tokens")
    print("   game_tokens_results.json - game tokens only")
    print("   historical_data.json - price history")
    print("   selected_game_tokens.json - selected game tokens info")
    print("   detailed_simulation_results.csv - detailed CSV")
    print("   game_tokens_only.csv - game tokens CSV")

    # 10. Final stats and recommendations.
    print("\nFINAL STATISTICS AND SUMMARY")
    print("=" * 60)
    
    top_5_game = game_results[:5]
    print("Top 5 game tokens by final score:")
    for i, (symbol, data) in enumerate(top_5_game, 1):
        print(f"  {i}. {symbol} ({data['name'][:20]}...)")
        print(f"      {data['weekly_change_pct']:+.2f}% | {data['final_score']:.0f} pts | Weight {data['card_weight']}")

    worst_3_game = game_results[-3:]
    print("\nWorst 3 game tokens:")
    for i, (symbol, data) in enumerate(worst_3_game, len(game_results) - 2):
        print(f"  {i}. {symbol} ({data['name'][:20]}...)")
        print(f"      {data['weekly_change_pct']:+.2f}% | {data['final_score']:.0f} pts | Weight {data['card_weight']}")

    print("\nGame token distribution by rank:")
    rank_categories = {
        'Top 10 (rank 1-10)': len([s for s, d in game_results if d['final_rank'] <= 10]),
        'Middle (rank 11-50)': len([s for s, d in game_results if 11 <= d['final_rank'] <= 50]),
        'Bottom (rank 51+)': len([s for s, d in game_results if d['final_rank'] > 50])
    }

    for category, count in rank_categories.items():
        print(f"   {category}: {count} tokens")

    print("\nGAME RECOMMENDATIONS:")
    print("-" * 40)
    print("System ready for real game run")
    print(f"Processed {len(results)} tokens, selected {len(game_tokens)} for game")
    print(f"Data quality: {success_rate:.1f}% successful requests")

    high_potential = [s for s, d in game_results[:10] if d['weekly_change_pct'] > avg_change]
    if high_potential:
        print(f"High potential tokens: {', '.join(high_potential[:5])}")

    stable_tokens = [s for s, d in game_results if d['activity_score'] < 10 and d['weekly_change_pct'] > 0]
    if stable_tokens:
        print(f"Stable tokens: {', '.join(stable_tokens[:3])}")

    print("\nAnalysis completed successfully.")
    print("All data saved to 'crypto_game_results/'")
    print("System ready for production use.")

if __name__ == "__main__":
    main()