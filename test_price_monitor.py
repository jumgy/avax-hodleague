# test_price_monitor.py
import asyncio
import sys
import os

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.price_monitor_service import PriceMonitorService

async def test_price_monitor():
    """Test price monitoring service"""
    print("🧪 Testing Price Monitor Service...")
    
    async with PriceMonitorService() as monitor:
        await monitor.monitor_and_update_prices()
    
    print("✅ Test completed!")

if __name__ == "__main__":
    asyncio.run(test_price_monitor())