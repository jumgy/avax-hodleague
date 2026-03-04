# services/price_monitor_service.py
import asyncio
import aiohttp
import logging
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.database import AsyncSessionLocal
from models.token_models import Token, TokenPrice
from config import Config

logger = logging.getLogger(__name__)


class PriceMonitorService:
    # Hardcoded tokens for DexScreener
    DEXSCREENER_TOKENS = {
        'ABX': {
            'chain_id': 'abstract',
            'address': '0x4C68E4102c0F120cce9F08625bd12079806b7C4D'
        },
        'ABSTER': {
            'chain_id': 'abstract',
            'address': '0xc325b7e2736A5202bd860F5974D0AA375E57EdE5'
        }
    }
    
    def __init__(self):
        self.session: aiohttp.ClientSession = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_dexscreener_price(self, symbol: str) -> Optional[Dict]:
        """Get price from DexScreener API for specific tokens (ABX, ABSTER)"""
        try:
            if symbol.upper() not in self.DEXSCREENER_TOKENS:
                return None
            
            token_info = self.DEXSCREENER_TOKENS[symbol.upper()]
            chain_id = token_info['chain_id']
            token_address = token_info['address']
            
            url = f"https://api.dexscreener.com/token-pairs/v1/{chain_id}/{token_address}"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if not data or len(data) == 0:
                        logger.warning(f"No DexScreener data for {symbol}")
                        return None
                    
                    # First pair (usually most liquid)
                    pair = data[0]
                    
                    # Extract data
                    price_usd = float(pair.get('priceUsd', 0))
                    market_cap = pair.get('marketCap')
                    fdv = pair.get('fdv')
                    
                    price_change = pair.get('priceChange', {})
                    change_24h = price_change.get('h24', 0)

                    # 24h volume
                    volume = pair.get('volume', {})
                    volume_24h = volume.get('h24', 0)
                    
                    result = {
                        'price': price_usd,
                        'change_24h': change_24h,
                        'volume': volume_24h,
                        'market_cap': market_cap if market_cap else fdv,
                        'source': 'dexscreener'
                    }
                    
                    logger.info(f"DexScreener {symbol}: ${price_usd:.6f} (+/-{change_24h:.2f}%)")
                    return {symbol.upper(): result}
                    
                else:
                    logger.error(f"DexScreener API error for {symbol}: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error fetching DexScreener price for {symbol}: {e}")
            return None
    
    async def get_binance_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get prices from Binance API"""
        try:
            # Binance pairs like BTCUSDT
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
                                    'change_24h': float(ticker['price24hPcnt']) * 100,
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
            result = {}
            
            for symbol in symbols:
                try:
                    pair = f"{symbol.upper()}-USD"
                    ticker_url = f"https://api.exchange.coinbase.com/products/{pair}/ticker"
                    
                    async with self.session.get(ticker_url) as response:
                        if response.status == 200:
                            ticker_data = await response.json()
                            
                            stats_url = f"https://api.exchange.coinbase.com/products/{pair}/stats"
                            async with self.session.get(stats_url) as stats_response:
                                if stats_response.status == 200:
                                    stats_data = await stats_response.json()
                                    
                                    current_price = float(ticker_data['price'])
                                    open_24h = float(stats_data['open'])
                                    change_24h = ((current_price - open_24h) / open_24h) * 100 if open_24h > 0 else 0
                                    
                                    result[symbol.upper()] = {
                                        'price': current_price,
                                        'change_24h': change_24h,
                                        'volume': float(stats_data['volume']),
                                        'source': 'coinbase'
                                    }
                    
                    await asyncio.sleep(0.1)
                except Exception as e:
                    logger.warning(f"Error fetching {symbol} from Coinbase: {e}")
                    continue
            
            return result
        except Exception as e:
            logger.error(f"Error fetching Coinbase prices: {e}")
            return {}
    
    async def get_kucoin_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get prices from KuCoin API"""
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
                                    'change_24h': float(ticker['changeRate']) * 100,
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
        
        token_prices = {}
        for data in prices_data:
            for symbol, price_info in data.items():
                if symbol not in token_prices:
                    token_prices[symbol] = []
                token_prices[symbol].append(price_info)
        
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
    
    async def monitor_and_update_prices(self):
        """Main method - fetch prices and update database"""
        logger.info("🔄 Starting price monitoring cycle...")
        
        async with AsyncSessionLocal() as db:
            try:
                # Get active tokens from DB
                query = select(Token).where(Token.is_active == True)
                result = await db.execute(query)
                active_tokens = result.scalars().all()
                
                if not active_tokens:
                    logger.warning("No active tokens found")
                    return
                
                symbols = [token.symbol for token in active_tokens]
                logger.info(f"Monitoring prices for {len(symbols)} tokens: {symbols}")
                
                # Split by regular vs DexScreener
                dexscreener_symbols = [s for s in symbols if s.upper() in self.DEXSCREENER_TOKENS]
                regular_symbols = [s for s in symbols if s.upper() not in self.DEXSCREENER_TOKENS]
                
                # Tasks for regular tokens
                tasks = []
                
                if regular_symbols:
                    tasks.extend([
                        self.get_binance_prices(regular_symbols),
                        self.get_bybit_prices(regular_symbols),
                        self.get_coinbase_prices(regular_symbols),
                        self.get_kucoin_prices(regular_symbols),
                        self.get_coinmarketcap_market_caps(regular_symbols)
                    ])
                
                # Add DexScreener token tasks
                for symbol in dexscreener_symbols:
                    tasks.append(self.get_dexscreener_price(symbol))
                
                # Run all requests in parallel
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process results
                prices_data = []
                market_caps = {}
                
                if regular_symbols:
                    regular_results = results[:5]  # 4 exchanges + CMC

                    # First 4 are exchange prices
                    for data in regular_results[:4]:
                        if isinstance(data, dict) and data:
                            prices_data.append(data)
                    
                    # Last is market caps from CoinMarketCap
                    if isinstance(regular_results[4], dict):
                        market_caps.update(regular_results[4])
                    
                    # Remaining are DexScreener
                    dex_results = results[5:]
                else:
                    # All results from DexScreener.
                    dex_results = results
                
                # Process DexScreener results
                for dex_data in dex_results:
                    if isinstance(dex_data, dict) and dex_data:
                        # DexScreener already includes market_cap in data.
                        for symbol, data in dex_data.items():
                            if 'market_cap' in data:
                                market_caps[symbol] = data['market_cap']
                        
                        prices_data.append(dex_data)
                
                if not prices_data:
                    logger.error("No price data received from any source")
                    return
                
                # Average prices (or single value for DexScreener)
                average_prices = self.calculate_average_price(prices_data)
                
                # Add market caps to price data
                for symbol in average_prices:
                    if symbol in market_caps:
                        average_prices[symbol]['market_cap'] = market_caps[symbol]
                
                # Update DB
                updated_count = 0
                for token in active_tokens:
                    symbol = token.symbol.upper()
                    if symbol in average_prices:
                        price_data = average_prices[symbol]
                        
                        # Create TokenPrice record
                        token_price = TokenPrice(
                            token_id=token.id,
                            price=price_data['price'],
                            market_cap=price_data.get('market_cap'),
                            change_24h=price_data.get('change_24h'),
                            sources_count=price_data.get('sources_count', 1),
                            timestamp=datetime.utcnow()
                        )
                        db.add(token_price)
                        updated_count += 1
                        
                        # Format market cap for log
                        market_cap_value = price_data.get('market_cap')
                        if market_cap_value:
                            if market_cap_value >= 1e9:
                                market_cap_str = f"${market_cap_value/1e9:.2f}B"
                            elif market_cap_value >= 1e6:
                                market_cap_str = f"${market_cap_value/1e6:.2f}M"
                            else:
                                market_cap_str = f"${market_cap_value:,.0f}"
                        else:
                            market_cap_str = "N/A"
                        
                        # Label for DexScreener tokens
                        source_info = f"from {price_data['sources_count']} sources"
                        if symbol in self.DEXSCREENER_TOKENS:
                            source_info = "from DexScreener"
                        
                        logger.info(
                            f"{symbol}: ${price_data['price']:.6f} "
                            f"(±{price_data.get('change_24h', 0):.2f}%) "
                            f"MC: {market_cap_str} {source_info}"
                        )
                
                await db.commit()
                logger.info(f"Updated prices for {updated_count}/{len(active_tokens)} tokens")
                
            except Exception as e:
                logger.error(f"Error in price monitoring: {e}")
                await db.rollback()


# Singleton instance
price_monitor = PriceMonitorService()