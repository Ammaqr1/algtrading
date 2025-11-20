# Import necessary modules4

import asyncio
import json
import ssl
import websockets
import requests
from google.protobuf.json_format import MessageToDict
import MarketDataFeed_pb2 as pb
import os
from dotenv import load_dotenv
from mani import AlogKM
import pytz
from datetime import datetime, time
import time as tm


load_dotenv()
my_access_token = os.getenv('access_token')
print(my_access_token)

def get_market_data_feed_authorize_v3():
    """Get authorization for market data feed."""
   
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {my_access_token}'
    }
    url = 'https://api.upstox.com/v3/feed/market-data-feed/authorize'
    api_response = requests.get(url=url, headers=headers)
    print(api_response.json())
    return api_response.json()


def decode_protobuf(buffer):
    """Decode protobuf message."""
    feed_response = pb.FeedResponse()
    feed_response.ParseFromString(buffer)
    return feed_response


async def fetch_market_data():
    """Fetch market data using WebSocket and print it."""

    # Create default SSL context
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    # instrument key
    instrument_key = "BSE_INDEX|SENSEX"

    # Get market data feed authorization
    response = get_market_data_feed_authorize_v3()
    # Connect to the WebSocket with SSL context
    async with websockets.connect(response["data"]["authorized_redirect_uri"], ssl=ssl_context) as websocket:
        i = 0
        print(f'Connection established {i}')

        # await asyncio.sleep(1)  # Wait for 1 second

        # Data to be sent over the WebSocket
        data = {
            "guid": "someguid",
            "method": "sub",
            "data": {
                "mode": "full",
                "instrumentKeys": [instrument_key]
            }
        }

        # Convert data to binary and send over WebSocket
        binary_data = json.dumps(data).encode('utf-8')
        await websocket.send(binary_data)


        kamal = AlogKM(access_token=my_access_token,instrument_key=instrument_key)

        # Track the high price
        tracked_high = 0
        start_hour = 9
        start_minute = 17
        end_hour = 16
        end_minute = 30

        # Continuously receive and decode data from WebSocket
        while True:
            i += 1
            message = await websocket.recv()
            decoded_data = decode_protobuf(message)

                    # Define IST timezone
            ist = pytz.timezone("Asia/Kolkata")

            # Get current IST time
            now = datetime.now(ist).time()

            # Define start and end times
            start = time(start_hour, start_minute)
            end = time(end_hour, end_minute)
            exit_time = time(17, 30)  # 3:30 PM


            # Convert the decoded data to a dictionary
            data_dict = MessageToDict(decoded_data)

            print(f'i ith call {i}')
            print(json.dumps(data_dict, indent=2))


            if now >= exit_time:
                print(f"⏰ Time reached {exit_time.strftime('%H:%M')}. Exiting loop.")
                break



            while start <= now <= end:
                result = kamal.extract_l1_ohlc(data_dict)
                if result:
                    cp,ltp,ltt = result.values()
                    print(f"📊 L1 HIGH: ₹{ltp} | L1 CURRENT: ₹{cp}")

                    # Pass to when_to_buy - using L1 data
                    tracked_high = kamal.highMarketValue(
                        tracked_high,
                        ltp
                    )
                    print(tracked_high,'this is tracked high')
                    price=tracked_high if tracked_high else ltp
                    print(f'price {price}')

                    # ✅ Update time on each iteration to check if we're still in window
                    now = datetime.now(ist).time()
                    print(f'⏰ Current time: {now} | Window: {start} - {end}')



            # tracked_high = 193
            if tracked_high > 0:
                gtt_order_id = kamal.buyStock(quantity=20, buy_price=tracked_high,instrument_key=instrument_key)
                print('bought the stock')

                while gtt_order_id:
                    i += 1
                    j = 1

                    if now >= exit_time:
                        print(f"⏰ Time reached {exit_time.strftime('%H:%M')}. Exiting loop.")
                        break

                    message = await websocket.recv()
                    decoded_data = decode_protobuf(message)
                    data_dict = MessageToDict(decoded_data)

                    result = kamal.extract_l1_ohlc(data_dict)

                    if result:
                        cp,ltp,ltt = result.values()
                        print(f'cp {cp} ltp {ltp} ltt {ltt} from inside')

                        # Check if price is near trigger/stop loss/target
                        is_near, strategy, trigger_price = kamal.is_price_near_trigger(
                            current_price= ltp,
                            buy_price=tracked_high,
                            threshold_percent=0.5
                        )

                        if is_near:
                            if strategy == 'TARGET':
                                print(f"\n🔔 ALERT: Price near {strategy}!")
                                print(f"🎯 {strategy} trigger price: ₹{trigger_price} last traded price: ₹{ltp} last traded time: {ltt}")
                                response = kamal.get_gtt_order_details(gtt_order_id)
                                print('response',response)
                                status = kamal.check_gtt_status(response)
                                if status == 'Target Hit':
                                    break
                            elif strategy == 'STOPLOSS':
                                print(f"\n🔔 ALERT: Price near {strategy}!")
                                print(f"🎯 {strategy} trigger price: ₹{trigger_price} last traded price: ₹{ltp} last traded time: {ltt}")
                                kamal.get_gtt_order_details(gtt_order_id)
                                status = kamal.check_gtt_status(response)
                                if status == 'Stop Loss Hit':
                                    j += 1
                                    if j == 2:
                                        break
                                    gtt_order_id = kamal.buyStock(quantity=1, buy_price=tracked_high)
                            else:
                                print(f"🎯 {strategy} trigger price: ₹{trigger_price} last traded price: ₹{ltp} last traded time: {ltt}")







# Execute the function to fetch market data
asyncio.run(fetch_market_data())