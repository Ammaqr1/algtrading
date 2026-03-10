import asyncio
import ssl
import os
from dotenv import load_dotenv
from mani import AlgoKM
from trading_strategy import TradingStrategy, get_market_data_feed_authorize_v3
import websockets

load_dotenv()
access_token = os.getenv('access_token')


# async def run_strategy_test():
#     """Run the full strategy (websocket, sensex, options, orders) using TradingStrategy."""
#     from datetime import time as time_class
#     strategy = TradingStrategy(
#         access_token=access_token,
#         quantity=20,
#         tick_size=True,
#         at_the_money_time=time_class(9, 17),
#     )
#     await strategy.execute_strategy()


async def run_single_order_test():
    """Minimal test: connect websocket and run AlgoKM.normal_gtt_execution once."""
    if not access_token:
        print("❌ Set access_token in .env")
        return
    response = get_market_data_feed_authorize_v3(access_token)
    if response.get("status") == "error" or "data" not in response:
        print("❌ Market data feed auth failed (check token)")
        return
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    async with websockets.connect(
        response["data"]["authorized_redirect_uri"],
        ssl=ssl_context,
    ) as websocket:
        print("✅ WebSocket connected")
        algo = AlgoKM(
            instrument_key='NSE_EQ|INE528G01035',
            access_token=access_token,
            tick_size=True,
            buy_percentage=0,
            stop_loss_percentage=0.08,
            target_percentage=0.08,
            product='I',
            validity='DAY',
            order_type='LIMIT', 
        )
        print(algo,'this is algo')
        await algo.normal_gtt_execution(websocket=websocket, buy_price=19.82, quantity=1)


# if __name__ == "__main__":
#     asyncio.run(run_single_order_test())
    # Or: asyncio.run(run_single_order_test())
