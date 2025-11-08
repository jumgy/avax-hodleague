import requests
import time
import logging
from typing import Dict, List, Optional, Tuple
from config import Config
from data.game_tokens import GAME_TOKENS, get_token_weight
logger = logging.getLogger(__name__)

class CoinMarketCapService:
    """Service for interacting with CoinMarketCap API"""
    
    def __init__(self):
        self.api_key = Config.COINMARKETCAP_API_KEY
        self.base_url = Config.COINMARKETCAP_BASE_URL
        self.headers = {
            'X-CMC_PRO_API_KEY': self.api_key,
            'Accept': 'application/json'
        }
        self.last_request_time = 0
        self.rate_limit_delay = 1  # 1 second between requests
    
    def _rate_limit(self):
        """Ensure we don't exceed rate limits"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - time_since_last)
        self.last_request_time = time.time()
    
    def get_top_cryptocurrencies(self, limit: int = 200) -> Optional[List[Dict]]:
        """Get top cryptocurrencies by market cap"""
        try:
            self._rate_limit()
            
            url = f"{self.base_url}/cryptocurrency/listings/latest"
            params = {
                'start': 1,
                'limit': limit,
                'convert': 'USD',
                'sort': 'market_cap',
                'sort_dir': 'desc'
            }
            
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status', {}).get('error_code') == 0:
                return data.get('data', [])
            else:
                logger.error(f"CoinMarketCap API error: {data.get('status', {}).get('error_message')}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return None
    
    def get_specific_cryptocurrencies(self, symbols: List[str]) -> Optional[Dict]:
        """Get specific cryptocurrencies by symbols"""
        try:
            self._rate_limit()
            
            url = f"{self.base_url}/cryptocurrency/quotes/latest"
            params = {
                'symbol': ','.join(symbols),
                'convert': 'USD'
            }
            
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status', {}).get('error_code') == 0:
                return data.get('data', {})
            else:
                logger.error(f"CoinMarketCap API error: {data.get('status', {}).get('error_message')}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return None
    
    def filter_stable_coins(self, cryptocurrencies: List[Dict]) -> List[Dict]:
        """Filter out stablecoins and unwanted tokens"""
        stable_coins = {
            'USDT', 'USDC', 'DAI', 'BUSD', 'TUSD', 'USDP', 'USDD', 'FRAX',
            'PYUSD', 'FDUSD', 'USDE', 'CRVUSD', 'LUSD', 'GUSD', 'SUSD',
            'ALUSD', 'MIM', 'USTC', 'VAI', 'DOLA', 'OUSD', 'MUSD', 'HUSD',
            'CUSD', 'RSRUSD', 'EURS', 'EURT', 'XSGD', 'GYEN', 'ZUSD',
            'STETH', 'WSTETH', 'RETH', 'CBETH', 'SFRXETH', 'RLUSD', 'USD1'
        }
        
        filtered = []
        for crypto in cryptocurrencies:
            symbol = crypto.get('symbol', '')
            # Skip stablecoins
            if symbol in stable_coins:
                continue
            filtered.append(crypto)
        
        return filtered
    
    def _create_token_data(self, crypto: Dict, is_game_token: bool = False) -> Dict:
        """Create standardized token data dictionary"""
        token_weight = get_token_weight(crypto['symbol']) if is_game_token else 0
        
        return {
            'symbol': crypto['symbol'],
            'name': crypto['name'],
            'cmc_rank': crypto.get('cmc_rank', 999),
            'market_cap': crypto['quote']['USD']['market_cap'],
            'market_cap_formatted': self.format_market_cap(crypto['quote']['USD']['market_cap']),
            'current_price': crypto['quote']['USD']['price'],
            'circulating_supply': crypto.get('circulating_supply', 0),
            'total_supply': crypto.get('total_supply'),
            'max_supply': crypto.get('max_supply'),
            'logo_url': f"https://s2.coinmarketcap.com/static/img/coins/64x64/{crypto['id']}.png",
            'is_game_token': is_game_token,
            'tournament_weight': token_weight
        }
    
    def get_all_tokens_data(self) -> Tuple[List[Dict], List[Dict]]:
        """Get both game tokens (30) and simulation tokens (100)
        
        Returns:
            Tuple[List[Dict], List[Dict]]: (game_tokens, simulation_tokens)
        """
        try:
            # Step 1: Get top-200 to maximize chances of finding all tokens
            all_cryptos = self.get_top_cryptocurrencies(limit=200)
            if not all_cryptos:
                logger.error("Failed to get top cryptocurrencies")
                return [], []
            
            # Filter out stablecoins
            filtered_cryptos = self.filter_stable_coins(all_cryptos)
            
            # Step 2: Separate game tokens and other tokens
            game_tokens = []
            other_tokens = []
            found_game_symbols = set()
            
            for crypto in filtered_cryptos:
                token_data = self._create_token_data(crypto, is_game_token=crypto['symbol'] in GAME_TOKENS)
                
                if crypto['symbol'] in GAME_TOKENS:
                    game_tokens.append(token_data)
                    found_game_symbols.add(crypto['symbol'])
                else:
                    other_tokens.append(token_data)
            
            # Step 3: Fetch missing game tokens separately
            missing_game_symbols = [symbol for symbol in GAME_TOKENS if symbol not in found_game_symbols]
            
            if missing_game_symbols:
                logger.info(f"Missing game tokens from top-200: {missing_game_symbols}. Fetching separately...")
                
                missing_data = self.get_specific_cryptocurrencies(missing_game_symbols)
                
                if missing_data:
                    for symbol in missing_game_symbols:
                        if symbol in missing_data:
                            crypto = missing_data[symbol]
                            token_data = self._create_token_data(crypto, is_game_token=True)
                            game_tokens.append(token_data)
                            found_game_symbols.add(symbol)
                
                # Add placeholders for tokens we still can't find
                still_missing = [symbol for symbol in GAME_TOKENS if symbol not in found_game_symbols]
                for symbol in still_missing:
                    logger.warning(f"Adding {symbol} with placeholder data")
                    placeholder_token = {
                        'symbol': symbol,
                        'name': f"{symbol} Token",
                        'cmc_rank': 1000,
                        'market_cap': 100000000,  # 100M placeholder
                        'market_cap_formatted': "$100M",
                        'current_price': 1.0,
                        'circulating_supply': 100000000,
                        'total_supply': 100000000,
                        'max_supply': None,
                        'logo_url': f"https://s2.coinmarketcap.com/static/img/coins/64x64/1.png",
                        'is_game_token': True
                    }
                    game_tokens.append(placeholder_token)
            
            # Step 4: Create simulation tokens list (100 tokens total)
            # Start with all game tokens, then fill with top other tokens
            simulation_tokens = game_tokens.copy()  # All 30 game tokens
            
            # Add top other tokens to reach 100 total
            remaining_slots = 100 - len(simulation_tokens)
            top_other_tokens = sorted(other_tokens, key=lambda x: x['market_cap'], reverse=True)[:remaining_slots]
            simulation_tokens.extend(top_other_tokens)
            
            # Sort both lists by market cap
            game_tokens.sort(key=lambda x: x['market_cap'], reverse=True)
            simulation_tokens.sort(key=lambda x: x['market_cap'], reverse=True)
            
            logger.info(f"Successfully created token lists:")
            logger.info(f"- Game tokens: {len(game_tokens)} (target: 30)")
            logger.info(f"- Simulation tokens: {len(simulation_tokens)} (target: 100)")
            logger.info(f"- Game tokens in simulation: {len([t for t in simulation_tokens if t['is_game_token']])}")
            
            return game_tokens, simulation_tokens
            
        except Exception as e:
            logger.error(f"Error getting token data: {e}")
            return [], []
    
    def get_available_game_tokens(self) -> List[Dict]:
        """Get only the 30 game tokens for user selection"""
        game_tokens, _ = self.get_all_tokens_data()
        return game_tokens
    
    def get_simulation_tokens(self) -> List[Dict]:
        """Get 100 tokens for simulation calculations (includes 30 game tokens + 70 others)"""
        _, simulation_tokens = self.get_all_tokens_data()
        return simulation_tokens
    
    def format_market_cap(self, market_cap: float) -> str:
        """Format market cap to human readable string"""
        if market_cap >= 1e12:
            return f"${market_cap/1e12:.1f}T"
        elif market_cap >= 1e9:
            return f"${market_cap/1e9:.1f}B"
        elif market_cap >= 1e6:
            return f"${market_cap/1e6:.0f}M"
        else:
            return f"${market_cap:.0f}"