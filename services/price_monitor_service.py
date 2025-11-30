# services/price_monitor_service.py
import asyncio
import aiohttp
import logging
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from models.database import get_sync_db
from models.token_models import Token, TokenPrice
from config import Config

logger = logging.getLogger(__name__)

class PriceMonitorService:
    def __init__(self):
        self.session: aiohttp.ClientSession = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_binance_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get prices from Binance API"""
        try:
            # Binance - пары типа BTCUSDT
            binance_symbols = [f"{symbol.upper()}USDT" for symbol in symbols]
            
            url = "https://api.binance.com/api/v3/ticker/24hr"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    result = {}
                    
                    for ticker in data:
                        symbol_pair = ticker['symbol']
                        if symbol_pair.endswith('USDT'):
                            symbol = symbol_pair.replace('USDT', '')
                            if symbol in [s.upper() for s in symbols]:
                                result[symbol] = {
                                    'price': float(ticker['lastPrice']),
                                    'change_24h': float(ticker['priceChangePercent']),
                                    'volume': float(ticker['volume']),
                                    'source': 'binance'
                                }
                    return result
                else:
                    logger.error(f"Binance API error: {response.status}")
                    return {}
        except Exception as e:
            logger.error(f"Error fetching Binance prices: {e}")
            return {}
    
    async def get_bybit_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get prices from Bybit API"""
        try:
            url = "https://api.bybit.com/v5/market/tickers"
            params = {'category': 'spot'}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    result = {}
                    
                    for ticker in data['result']['list']:
                        symbol_pair = ticker['symbol']
                        if symbol_pair.endswith('USDT'):
                            symbol = symbol_pair.replace('USDT', '')
                            if symbol in [s.upper() for s in symbols]:
                                result[symbol] = {
                                    'price': float(ticker['lastPrice']),
                                    'change_24h': float(ticker['price24hPcnt']) * 100,  # Bybit дает в долях
                                    'volume': float(ticker['volume24h']),
                                    'source': 'bybit'
                                }
                    return result
                else:
                    logger.error(f"Bybit API error: {response.status}")
                    return {}
        except Exception as e:
            logger.error(f"Error fetching Bybit prices: {e}")
            return {}
    
    async def get_coinbase_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get prices from Coinbase API"""
        try:
            # Coinbase Pro - пары типа BTC-USD
            result = {}
            
            # Делаем запросы для каждой пары (у Coinbase нет bulk API)
            for symbol in symbols:
                try:
                    pair = f"{symbol.upper()}-USD"
                    
                    # Получаем ticker
                    ticker_url = f"https://api.exchange.coinbase.com/products/{pair}/ticker"
                    async with self.session.get(ticker_url) as response:
                        if response.status == 200:
                            ticker_data = await response.json()
                            
                            # Получаем 24h stats
                            stats_url = f"https://api.exchange.coinbase.com/products/{pair}/stats"
                            async with self.session.get(stats_url) as stats_response:
                                if stats_response.status == 200:
                                    stats_data = await stats_response.json()
                                    
                                    # Вычисляем изменение за 24ч
                                    current_price = float(ticker_data['price'])
                                    open_24h = float(stats_data['open'])
                                    change_24h = ((current_price - open_24h) / open_24h) * 100 if open_24h > 0 else 0
                                    
                                    result[symbol.upper()] = {
                                        'price': current_price,
                                        'change_24h': change_24h,
                                        'volume': float(stats_data['volume']),
                                        'source': 'coinbase'
                                    }
                                    
                    await asyncio.sleep(0.1)  # Небольшая задержка между запросами
                    
                except Exception as e:
                    logger.warning(f"Error fetching {symbol} from Coinbase: {e}")
                    continue
            
            return result
        except Exception as e:
            logger.error(f"Error fetching Coinbase prices: {e}")
            return {}
    
    async def get_kucoin_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get prices from KuCoin API (bonus 4th exchange)"""
        try:
            url = "https://api.kucoin.com/api/v1/market/allTickers"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    result = {}
                    
                    for ticker in data['data']['ticker']:
                        symbol_pair = ticker['symbol']
                        if symbol_pair.endswith('-USDT'):
                            symbol = symbol_pair.replace('-USDT', '')
                            if symbol in [s.upper() for s in symbols]:
                                result[symbol] = {
                                    'price': float(ticker['last']),
                                    'change_24h': float(ticker['changeRate']) * 100,  # KuCoin дает в долях
                                    'volume': float(ticker['volValue']),
                                    'source': 'kucoin'
                                }
                    return result
                else:
                    logger.error(f"KuCoin API error: {response.status}")
                    return {}
        except Exception as e:
            logger.error(f"Error fetching KuCoin prices: {e}")
            return {}
    
    def calculate_average_price(self, prices_data: List[Dict]) -> Dict:
        """Calculate average price from multiple sources"""
        if not prices_data:
            return {}
            
        # Собираем все цены по токенам
        token_prices = {}
        
        for data in prices_data:
            for symbol, price_info in data.items():
                if symbol not in token_prices:
                    token_prices[symbol] = []
                token_prices[symbol].append(price_info)
        
        # Рассчитываем средние значения
        result = {}
        for symbol, price_list in token_prices.items():
            if not price_list:
                continue
                
            prices = [p['price'] for p in price_list if p.get('price')]
            changes_24h = [p['change_24h'] for p in price_list if p.get('change_24h')]
            volumes = [p['volume'] for p in price_list if p.get('volume')]
            
            if prices:
                result[symbol] = {
                    'price': sum(prices) / len(prices),
                    'change_24h': sum(changes_24h) / len(changes_24h) if changes_24h else None,
                    'volume': sum(volumes) / len(volumes) if volumes else None,
                    'sources_count': len(price_list),
                    'sources': [p.get('source') for p in price_list]
                }
        
        return result
    
    async def get_coinmarketcap_market_caps(self, symbols: List[str]) -> Dict[str, float]:
        """Get market caps from CoinMarketCap API"""
        try:
            from config import Config
            
            if not Config.COINMARKETCAP_API_KEY:
                logger.warning("CoinMarketCap API key not found")
                return {}
                
            symbols_string = ','.join([s.upper() for s in symbols])
            url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
            headers = {
                'Accepts': 'application/json',
                'X-CMC_PRO_API_KEY': Config.COINMARKETCAP_API_KEY,
            }
            params = {
                'symbol': symbols_string,
                'convert': 'USD'
            }
            
            async with self.session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    result = {}
                    for symbol, coin_data in data['data'].items():
                        quote = coin_data['quote']['USD']
                        result[symbol] = quote['market_cap']
                    return result
                else:
                    logger.error(f"CoinMarketCap API error: {response.status}")
                    return {}
        except Exception as e:
            logger.error(f"Error fetching CoinMarketCap market caps: {e}")
            return {}

    # Обновите главный метод monitor_and_update_prices
    async def monitor_and_update_prices(self):
        """Main method - fetch prices and update database"""
        logger.info("🔄 Starting price monitoring cycle...")
        
        try:
            # Получаем активные токены из БД
            db: Session = next(get_sync_db())
            active_tokens = db.query(Token).filter(Token.is_active == True).all()
            
            if not active_tokens:
                logger.warning("No active tokens found")
                return
            
            symbols = [token.symbol for token in active_tokens]
            logger.info(f"Monitoring prices for {len(symbols)} tokens: {symbols}")
            
            # Получаем данные с разных бирж + market caps параллельно
            tasks = [
                self.get_binance_prices(symbols),
                self.get_bybit_prices(symbols),
                self.get_coinbase_prices(symbols),
                self.get_kucoin_prices(symbols),
                self.get_coinmarketcap_market_caps(symbols)  # ДОБАВИЛИ market cap
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Разделяем price data и market cap data
            prices_data = [data for data in results[:-1] if isinstance(data, dict)]  # первые 4 - цены
            market_caps = results[-1] if isinstance(results[-1], dict) else {}  # последний - market caps
            
            if not prices_data:
                logger.error("No price data received from any source")
                return
            
            # Рассчитываем средние цены
            average_prices = self.calculate_average_price(prices_data)
            
            # Добавляем market caps к данным о ценах
            for symbol in average_prices:
                if symbol in market_caps:
                    average_prices[symbol]['market_cap'] = market_caps[symbol]
            
            # Обновляем БД
            updated_count = 0
            for token in active_tokens:
                symbol = token.symbol.upper()
                if symbol in average_prices:
                    price_data = average_prices[symbol]
                    
                    # Создаем запись в TokenPrice
                    token_price = TokenPrice(
                        token_id=token.id,
                        price=price_data['price'],
                        market_cap=price_data.get('market_cap'),  # ДОБАВИЛИ market_cap
                        change_24h=price_data.get('change_24h'),
                        sources_count=price_data.get('sources_count', 1),
                        timestamp=datetime.utcnow()
                    )
                    
                    db.add(token_price)
                    updated_count += 1
                    
                    market_cap_str = f"${price_data.get('market_cap', 0)/1e9:.2f}B" if price_data.get('market_cap') else "N/A"
                    logger.info(f"💰 {symbol}: ${price_data['price']:.6f} (±{price_data.get('change_24h', 0):.2f}%) MC: {market_cap_str} from {price_data['sources_count']} sources")
            
            db.commit()
            logger.info(f"✅ Updated prices for {updated_count}/{len(active_tokens)} tokens")
            
        except Exception as e:
            logger.error(f"Error in price monitoring: {e}")
        finally:
            if db:
                db.close()

# Singleton instance
price_monitor = PriceMonitorService()