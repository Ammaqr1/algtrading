
import upstox_client
from upstox_client.rest import ApiException
from datetime import datetime, time, timedelta, date
import pytz
import pandas as pd
import threading
from dotenv import load_dotenv
import os
import time as tm
import requests
import json
import asyncio
import MarketDataFeed_pb2 as pb
from google.protobuf.json_format import MessageToDict
import queue
from retrying import retry



load_dotenv()
access_token = os.getenv('access_token')





def decode_protobuf(buffer):
    """Decode protobuf message."""
    feed_response = pb.FeedResponse()
    feed_response.ParseFromString(buffer)
    return feed_response



class AlgoKM:
    def __init__(self,instrument_key='BSE_INDEX|SENSEX',access_token=None,tick_size=False,buy_percentage=1.5,stop_loss_percentage=1.25,target_percentage=2.5,product='I',validity='DAY',order_type='LIMIT',weekday=1,exchange='BSE'):
        self.configuration = upstox_client.Configuration(sandbox=False)
        self.configuration.access_token = access_token
        self.api_instance = upstox_client.OrderApiV3(upstox_client.ApiClient(self.configuration))
        self.market_holidays_and_timings_api = upstox_client.MarketHolidaysAndTimingsApi(upstox_client.ApiClient(self.configuration))

        self.instrument_key = instrument_key
        self.tick_size = tick_size
        self.option_contracts = None
        self.order_id = None
        self.product = product
        self.validity = validity
        self.order_type = order_type

        self.buy_price = None
        self.quantity = None
        self.ltp_order_price = None

        self.weekday = weekday
        self.exchange = exchange    

        self.ist = pytz.timezone("Asia/Kolkata")


        self.buy_percentage = buy_percentage
        self.stop_loss_percentage = stop_loss_percentage
        self.target_percentage = target_percentage
        
        # args=(...) for positional args, kwargs={...} for keyword args (target already has self)
        # threading.Thread(
        #     target=self.get_option_contracts_response,
        #     kwargs={'weekday': self.weekday, 'exchange': self.exchange},  # e.g. Thursday, BSE
        #     daemon=True
        # ).start()

        # Portfolio streamer for order tracking
        self.portfolio_streamer = None
        self.portfolio_thread = None
        self.portfolio_update_queue = queue.Queue()

        

    def round_to_tick_size(self, price, tick_size=0.05):
        """Round price to the nearest tick size."""
        return round(price / tick_size) * tick_size


    def place_normal_order(self, quantity, buy_price, instrument_key=None):

        if instrument_key is None:
            instrument_key = self.instrument_key

        # 🔧 Dummy hard-coded request body for testing
        body = upstox_client.PlaceOrderV3Request(
            quantity=quantity,                  # hardcoded quantity
            product=self.product,                 # Delivery
            validity=self.validity,              # DAY order
            price=buy_price,                   # price (ignored for MARKET)
            tag="buy-order",      # any string tag
            instrument_token=instrument_key,  # hardcoded instrument
            order_type=self.order_type,         # market order
            transaction_type="BUY",      # buy order
            disclosed_quantity=0,        # nothing disclosed
            trigger_price=0.0,           # 0 for non-SL orders
            is_amo=False,                # not an AMO
            slice=False                  # no auto-slicing
        )

        try:
            api_response = self.api_instance.place_order(body)
            print("Order Placed:", api_response)
            return api_response
        except ApiException as e:
            print("Exception when calling OrderApi->place_order: %s\n" % e) 
         
    def buyStock(self,quantity,buy_price,instrument_key=None):

        if instrument_key is None:
            instrument_key = self.instrument_key

        # Round buy_price to tick size
        if self.tick_size:
            buy_price = self.round_to_tick_size((buy_price) + ((buy_price * 1.5) / 100))
        
        stop_loss_value = buy_price + ((buy_price * - 1.25) / 100)
        if self.tick_size:
            stop_loss_value = self.round_to_tick_size(stop_loss_value)
        
        target_value = buy_price + ((buy_price * 3) / 100)
        if self.tick_size:
            target_value = self.round_to_tick_size(target_value)



        entry_rule = upstox_client.GttRule(
            strategy="ENTRY",           # ENTRY / STOPLOSS / TARGET
            trigger_type="ABOVE",
            trigger_price=buy_price         # Trigger price for the condition
        )


        stop_loss = upstox_client.GttRule(
            strategy="STOPLOSS",           # ENTRY / STOPLOSS / TARGET
            trigger_type="IMMEDIATE",
            trigger_price=stop_loss_value
        )

        target = upstox_client.GttRule(
             strategy="TARGET",           # ENTRY / STOPLOSS / TARGET
            trigger_type="IMMEDIATE",
            trigger_price=target_value
        )

        body = upstox_client.GttPlaceOrderRequest(
            type="MULTIPLE",                         # SINGLE or MULTIPLE
            quantity=quantity,
            product="I",                           # D=Delivery, I=Intraday, etc.
            rules=[entry_rule,stop_loss,target],                          # list of GttRule
            instrument_token=instrument_key,# Example instrument
            transaction_type="BUY"                 # BUY or SELL
        )


        try:
            api_response = self.api_instance.place_gtt_order(body)
            print("Order Placed:", api_response)
            return api_response
        except ApiException as e:
            print("Exception when calling OrderApi->place_order: %s\n" % e)


    def sellStock(self,quantity,sell_price):
        # Round sell_price to tick size
        if self.tick_size:
            sell_price = self.round_to_tick_size(sell_price)
        
        sell_order = upstox_client.PlaceOrderV3Request(
            quantity=quantity,
            product=self.product,
            validity=self.validity,
            price=sell_price,
            tag="sell_order",
            instrument_token=self.instrument_key,
            order_type=self.order_type,
            transaction_type="SELL",
            disclosed_quantity=0,
            trigger_price=0.0,
            is_amo=False,
            slice=False
    )
        try:
            api_response = self.api_instance.place_order(sell_order)
            print("Order Placed:", api_response)
            return api_response
        except ApiException as e:
            print("Exception when calling OrderApi->place_order: %s\n" % e)

    def highMarketValue(self,current,high):
        if current == 0:
            return high
        elif current < high:
            return high
        else:
            return current

    def cancel_normal_order(self,order_id):
        try:
            api_response = self.api_instance.cancel_order(order_id)
            print("Order Cancelled:", api_response)
            return api_response
        except ApiException as e:
            print("Exception when calling OrderApi->cancel_order: %s\n" % e)
        print(f"✅ Normal order cancelled. Order ID: {order_id}")


    def extract_l1_ohlc(self, data_dict):
        """
        Extract LTP, CP, and LTT from the new data_dict structure and return as OHLC-like dict.
        """
        try:
            ist = pytz.timezone("Asia/Kolkata")
            if 'feeds' in data_dict:
                feed = data_dict['feeds'].get(self.instrument_key, {})
                if 'ltpc' in feed:
                    ltpc = feed['ltpc']
                    ltp = float(ltpc.get('ltp', 0))
                    cp = float(ltpc.get('cp', 0))
                    ltt = ltpc.get('ltt')
                    # Use ltt as timestamp if available, else fallback to currentTs
                    ts_ms = int(ltt) if ltt is not None else int(data_dict.get('currentTs', 0))
                    timestamp = datetime.fromtimestamp(ts_ms / 1000, tz=ist)
                    return {
                        'cp': cp,    # Using cp as open (since only ltp/cp available)
                        'ltp': ltp,   # Using ltp as high (since only ltp/cp available)
                        'ltt': timestamp.strftime("%A, %d %B %Y %H:%M:%S %Z")

                    }
            return None
        except Exception as e:
            print(f"Error extracting L1 OHLC: {e}")
            return None

    def extract_i1_ohlc(self, data_dict,instrument_key):
        """
        Extract OHLC interval 1 (I1) data and LTPC from the fullFeed structure.
        Returns a dict with OHLC I1 data and LTPC data.
        """
        try:
            ist = pytz.timezone("Asia/Kolkata")
            if 'feeds' in data_dict:
                feed = data_dict['feeds'].get(instrument_key, {})
                if 'fullFeed' in feed:
                    full_feed = feed['fullFeed']
                    if 'marketFF' in full_feed:
                        market_ff = full_feed['marketFF']
                        
                        # Extract LTPC data
                        ltpc_data = {}
                        if 'ltpc' in market_ff:
                            ltpc = market_ff['ltpc']
                            ltpc_data = {
                                'ltp': float(ltpc.get('ltp', 0)),
                                'ltt': ltpc.get('ltt'),
                                'ltq': ltpc.get('ltq', '0'),
                                'cp': float(ltpc.get('cp', 0))
                            }
                        
                        # Extract OHLC I1 data
                        ohlc_i1_data = {}
                        if 'marketOHLC' in market_ff:
                            market_ohlc = market_ff['marketOHLC']
                            if 'ohlc' in market_ohlc:
                                ohlc_array = market_ohlc['ohlc']
                                # Find the entry with interval "I1"
                                for ohlc_entry in ohlc_array:
                                    if ohlc_entry.get('interval') == 'I1':
                                        ts_ms = int(ohlc_entry.get('ts', 0))
                                        timestamp = datetime.fromtimestamp(ts_ms / 1000, tz=ist)
                                        ohlc_i1_data = {
                                            'interval': ohlc_entry.get('interval'),
                                            'open': float(ohlc_entry.get('open', 0)),
                                            'high': float(ohlc_entry.get('high', 0)),
                                            'low': float(ohlc_entry.get('low', 0)),
                                            'close': float(ohlc_entry.get('close', 0)),
                                            'vol': ohlc_entry.get('vol', '0'),
                                            'ts': ohlc_entry.get('ts'),
                                            'ts_formatted': timestamp.strftime("%A, %d %B %Y %H:%M:%S %Z")
                                        }
                                        break
                        
                        # Return combined data if we found both
                        if ohlc_i1_data and ltpc_data:
                            return {
                                'ohlc_i1': ohlc_i1_data,
                                'ltpc': ltpc_data
                            }
                        elif ohlc_i1_data:
                            return {
                                'ohlc_i1': ohlc_i1_data,
                                'ltpc': None
                            }
                        elif ltpc_data:
                            return {
                                'ohlc_i1': None,
                                'ltpc': ltpc_data
                            }
            return None
        except Exception as e:
            print(f"Error extracting I1 OHLC: {e}")
            return

    def get_token(self):
        pass

    def get_thursday_date(self, weekday=3, exchange='BSE'):
        """
        Returns the date of the given weekday: today if today matches, else the next occurrence.
        If that day (or a day reached by going back) is a holiday, goes back until a non-holiday day.

        Args:
            weekday: int 0-6 (Monday=0, Tuesday=1, ..., Sunday=6) or str e.g. 'thursday', 'Thursday'.
                     Default 3 (Thursday).

        Returns:
            str: The date in 'YYYY-MM-DD' format.
        """
        # Normalize weekday to int 0-6
        if isinstance(weekday, str):
            names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            try:
                weekday = names.index(weekday.lower().strip())
            except ValueError:
                raise ValueError(f"weekday must be 0-6 or one of {names}")
        if not isinstance(weekday, int) or not 0 <= weekday <= 6:
            raise ValueError("weekday must be int 0-6 (Monday=0, Sunday=6) or a day name string")

        today = date.today()
        # Days until target weekday (0 = today, 1-6 = next occurrence)
        days_until_target = (weekday - today.weekday() + 7) % 7
        if days_until_target == 0:
            target_date = today
        else:
            target_date = today + timedelta(days=days_until_target)

        # Keep going back until we find a non-holiday day (max 3 days back)
        days_back = 0
        max_days_back = 3

        while days_back < max_days_back:
            try:
                response_data = self.market_holidays_and_timings_api.get_holiday(target_date.strftime('%Y-%m-%d'))
                if response_data.data:
                    closed_exchanges = response_data.data[0].closed_exchanges
                else:
                    closed_exchanges = []

                if exchange not in closed_exchanges:
                    break
                else:
                    target_date = target_date + timedelta(days=-1)
                    days_back += 1
            except Exception as e:
                print(f"Error checking holiday for {target_date}: {e}")
                break

        return target_date.strftime('%Y-%m-%d')
    

    def get_option_contracts_response(self, expiry_date):
        """Get option contracts response. Handles errors gracefully."""
        
        try:
            options_instance = upstox_client.OptionsApi(
                upstox_client.ApiClient(self.configuration)
            )
                

            param = {
                'expiry_date': expiry_date
            }

            # Get option contracts for the expiry date
            self.option_contracts = options_instance.get_option_contracts(
                instrument_key=self.instrument_key,
                **param
            )
            # print('this is the option_contracts', self.option_contracts)
        except upstox_client.rest.ApiException as e:
            print(f"❌ Error fetching option contracts (API Exception): {e.status} - {e.reason}")
            if e.body:
                try:
                    error_body = json.loads(e.body) if isinstance(e.body, str) else e.body
                    error_msg = error_body.get('errors', [{}])[0].get('message', 'Unknown error')
                    print(f"   Error message: {error_msg}")
                    if 'Invalid token' in error_msg or e.status == 401:
                        print("   💡 Your access token may be expired or invalid. Please refresh it.")
                except:
                    print(f"   Response body: {e.body}")
            self.option_contracts = None
        except Exception as e:
            print(f"❌ Unexpected error fetching option contracts: {e}")
            import traceback
            traceback.print_exc()
            self.option_contracts = None
        

    def get_option_contracts(self, sensex_price, instrument_key=None,expiry_date=None):
        """
        Get option contracts (CE and PE) for given expiry and strike price.
        
        Args:
            expiry_date: Expiry date in format 'YYYY-MM-DD'
            sensex_price: Current Sensex price to round for strike selection
            instrument_key: Underlying instrument key (defaults to Sensex)
            
        Returns:
            tuple: (ce_instrument_key, pe_instrument_key)
        """

        print('hello inside the get_option_contracts')
        if instrument_key is None:
            instrument_key = self.instrument_key

        rounded_strike = {
            'BSE': round(sensex_price / 100) * 100,
            'NSE': round(sensex_price / 50) * 50
        }
        
        try:
            # Round price to nearest 100 for strike selection
            rounded_strike = rounded_strike['NSE']

            print('sensex  price', sensex_price)
            print('rounded_strike', rounded_strike)
            print('instrument_key', instrument_key)
            print('expiry_date', expiry_date)
            
            if not self.option_contracts:
                self.get_option_contracts_response(expiry_date=expiry_date)

            # print('this is the option_contracts', self.option_contracts)


            
            # # Initialize OptionsApi with configuration
           
            # Convert response to dict if needed
            if hasattr(self.option_contracts, 'to_dict'):
                response_dict = self.option_contracts.to_dict()
            else:
                response_dict = self.option_contracts
            
            # Extract data
            data = response_dict.get('data', [])
            if not data:
                raise ValueError(f"No option contracts found for {instrument_key} on {self.get_thursday_date(weekday=weekday, exchange=exchange)}")
            
            # Create DataFrame
            df = pd.DataFrame(data)
            
            # Filter by strike price and instrument type
            ce_df = df[(df['strike_price'] == rounded_strike) & (df['instrument_type'] == 'CE')]
            pe_df = df[(df['strike_price'] == rounded_strike) & (df['instrument_type'] == 'PE')]
            
            if ce_df.empty:
                raise ValueError(f"No CE option found for strike {rounded_strike}")
            if pe_df.empty:
                raise ValueError(f"No PE option found for strike {rounded_strike}")
            
            ce_ik = ce_df['instrument_key'].iloc[0]
            pe_ik = pe_df['instrument_key'].iloc[0]
            
            return ce_ik, pe_ik
            
        except ApiException as e:
            print(f"Exception when calling OptionsApi->get_option_contracts: {e}")
            raise
        except Exception as e:
            print(f"Error getting option contracts: {e}")
            raise

    def time_range(self, ts, ltp):
        # Convert milliseconds to seconds and then to a datetime object
        dt_object = datetime.fromtimestamp(ts / 1000)

        # Define the target time range
        target_start = dt_object.replace(hour=9, minute=16, second=50, microsecond=0).time()
        target_end = dt_object.replace(hour=9, minute=17, second=0, microsecond=0).time()

        # Get the time part of the input timestamp
        input_time = dt_object.time()

        # Check if the input time is within the range
        if target_start <= input_time <= target_end:
            rounded_ltp = round(ltp / 100) * 100
            
            expiry_date = self.get_thursday_date(weekday=1, exchange='BSE')
            return self.get_option_contracts(ltp, instrument_key=self.instrument_key,exchange='BSE',weekday=1)
        # add the logic later

    def get_instrument_token(self):
        pass
    
    def get_today_start_timestamp_ms(self,time,ist=pytz.timezone("Asia/Kolkata")):
        today = datetime.now(ist).date()
        start_datetime = datetime.combine(today, time)
        start_datetime = ist.localize(start_datetime)
        start_timestamp_ms = int(start_datetime.timestamp() * 1000)
        return start_timestamp_ms

    def json_into_dict(self,json_data):
        json_data = json.dumps(json_data)
        return json.loads(json_data)


    def intraday_history_per_minute(self, instrument_key, max_retries=3, retry_delay=1):
        """
        Fetch intraday per minute history for an instrument.
        Retries up to `max_retries` times if network error or no valid JSON data.
        """
        url = f'https://api.upstox.com/v3/historical-candle/intraday/{instrument_key}/minutes/1'
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.configuration.access_token}'
        }
        last_exception = None
        for attempt in range(1, max_retries + 1):
            try:
                response = requests.get(url=url, headers=headers, timeout=10)
                if response.status_code == 200:
                    try:
                        json_data = response.json()
                        if json_data:  # not None or empty
                            return self.json_into_dict(json_data)
                        else:
                            # JSON data returned is empty or null, retry
                            print(f"[intraday_history_per_minute] Warning: Empty JSON response (attempt {attempt})")
                    except Exception as e_json:
                        print(f"[intraday_history_per_minute] Error decoding JSON (attempt {attempt}): {e_json}")
                        last_exception = e_json
                else:
                    print(f"[intraday_history_per_minute] HTTP {response.status_code} (attempt {attempt})")
            except Exception as e:
                print(f"[intraday_history_per_minute] Request error (attempt {attempt}): {e}")
                last_exception = e
            if attempt < max_retries:
                tm.sleep(retry_delay)
        # All attempts failed
        print("[intraday_history_per_minute] Failed to fetch data after retries.")
        if last_exception:
            print(f"Last exception: {last_exception}")
        return None



    def highest_price_per_minute(self, data, start_time, end_time, highest_price, ist=pytz.timezone("Asia/Kolkata")):
        """
        Filter candles by time range and track highest price.
        
        Args:
            data: Dictionary with 'data' -> 'candles' structure
            start_time: time object for start time
            end_time: time object for end time
            highest_price: initial highest price value
            ist: timezone (default: IST)
        
        Returns:
            highest_price: Maximum high price from filtered candles
        """
        candles = data.get('data', {}).get('candles', [])
        for candle in candles:
            # Extract timestamp from candle[0] and get time component
            candle_time = datetime.fromisoformat(candle[0]).time()
            if start_time <= candle_time <= end_time:
                # candle[2] is the high price
                highest_price = self.highMarketValue(highest_price, candle[2])
        return highest_price
    
    def price_at_917(self,time,insturment_key='BSE_INDEX|SENSEX'):
        sensex_data = self.intraday_history_per_minute(instrument_key=insturment_key,max_retries=2)
        candles = sensex_data.get('data', {}).get('candles', [])
        for candle in candles:
            candle_time = datetime.fromisoformat(candle[0]).time()
            if time == candle_time:
                return candle[1]
        return None

    def cancel_gtt_order(self,order_id):
        body = upstox_client.GttCancelOrderRequest(gtt_order_id=order_id)
        response = self.api_instance.cancel_gtt_order(body)
        return response


    async def normal_order_execution(self, websocket, buy_price, quantity):

        self.buy_price = buy_price

        self.quantity = quantity
     
        if self.tick_size:
            self.quantity = self.round_to_tick_size(quantity)


        data = {
            "guid": "normal_order_sub",
            "method": "sub",
            "data": {
                "mode": "ltpc",
                "instrumentKeys": [self.instrument_key]
            }
        }
        binary_data = json.dumps(data).encode('utf-8')
        await websocket.send(binary_data)
        
        # Receive messages until we get a valid price
        max_attempts = 2
        attempt = 0
        entry_taken = self.order_id is not None

        while attempt < max_attempts:
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                decoded_data = decode_protobuf(message)
                data_dict = MessageToDict(decoded_data)
                is_data = self.instrument_key == list(data_dict.get('feeds').keys())[0]


                if is_data:
                    result = self.extract_l1_ohlc(data_dict)
                    if result and result.get('ltp', 0) > 0:
                        ltp = result['ltp']
                        print('this is ltp', ltp)
                        if ltp > self.buy_price and not entry_taken:
                            self.order_id = self.place_normal_order(
                                quantity=self.quantity,
                                buy_price=ltp,
                                instrument_key=self.instrument_key
                            ).data.order_ids[0]
                            self.ltp_order_price = ltp
                            entry_taken = True
                            print(f"✅ Normal order placed. Order ID: {self.order_id}")
                            break        
                  
            except asyncio.TimeoutError:
                attempt += 1
                print(f"⏳ Waiting for Sensex price data... (attempt {attempt}/{max_attempts})")
            except Exception as e:
                print(f"Error capturing Sensex price: {e}")
                attempt += 1

        return entry_taken if entry_taken else False
    





    def setup_portfolio_streamer(self):
        """Set up PortfolioDataStreamer to track GTT order updates."""
        try:
            
            
            self.portfolio_streamer = upstox_client.PortfolioDataStreamer(
                upstox_client.ApiClient(self.configuration),
                order_update=True,
                position_update=False,
                holding_update=False,
                gtt_update=True
            )
            
            def on_portfolio_message(message):
                """Handle portfolio/order update messages."""
                self.handle_order_updates(json.loads(message))
            
            def on_portfolio_open():
                print("✅ Portfolio streamer connected")
            
            def on_portfolio_error(error):
                print(f"❌ Portfolio streamer error: {error}")
            
            self.portfolio_streamer.on("message", on_portfolio_message)
            self.portfolio_streamer.on("open", on_portfolio_open)
            self.portfolio_streamer.on("error", on_portfolio_error)
            
            # Connect in a separate thread
            def run_portfolio_streamer():
                self.portfolio_streamer.connect()
            
            self.portfolio_thread = threading.Thread(target=run_portfolio_streamer, daemon=True)
            self.portfolio_thread.start()
            
            print("📡 Portfolio streamer setup complete")
            
        except Exception as e:
            print(f"Error setting up portfolio streamer: {e}")

    def handle_order_updates(self, message):
        """
        Process order status updates from PortfolioDataStreamer and add to queue.
        
        Args:
            message: Order update message from websocket
        """
        try:
            # Parse the message (format depends on Upstox API)
            if isinstance(message, dict):
                order_data = message
                
            else:
                # Try to convert to dict if it's a model instance
                order_data = message.to_dict() if hasattr(message, 'to_dict') else str(message)
            
            print(f"📨 Order update received: {json.dumps(order_data, indent=2) if isinstance(order_data, dict) else order_data}")
            
            # Add to queue for async processing
            self.portfolio_update_queue.put(order_data)
                
        except Exception as e:
            print(f"Error handling order update: {e}")
        
    async def monitor_portfolio_updates(self):
        """
        Monitor portfolio streamer updates and handle re-entry logic based on GTT order status.
        This function processes real-time updates from the portfolio streamer websocket.
        Similar to monitor_orders but uses portfolio streamer data instead of polling.
        """
        print("📡 Monitoring portfolio streamer for order updates...")
        
        while True:
            now = datetime.now(self.ist).time()
            
            
            try:
                # Wait for message with timeout
                try:
                    order_data = self.portfolio_update_queue.get(timeout=1.0)
                    result = await self.process_portfolio_update(order_data)
                    print('this is result',result)
                    # Only return when we have a terminal status (complete/rejected); keep waiting for "open" etc.
                    if result is not None:
                        return result
                except queue.Empty:
                    # Timeout is expected, continue monitoring
                    continue
                    
            except Exception as e:
                print(f"Error in portfolio monitoring loop: {e}")
                continue
            
            # Small sleep to prevent tight loop
            await asyncio.sleep(0.1)

    async def process_portfolio_update(self, order_data):
        """
        Process a single portfolio update message and handle re-entry if needed.
        
        Args:
            order_data: Order update data from portfolio streamer
        """

        try:
            update_type = order_data.get('update_type', '')
            
            if update_type == 'order':
                order_ref_id = order_data.get('order_id', '')
                status = order_data.get('status', '').lower()
                
                # Check if this order matches our GTT orders
                is_normal_order = (self.order_id and order_ref_id == self.order_id)
                
                
                # Check if order was rejected
                if status == 'rejected' and is_normal_order:
                    status_message = order_data.get('status_message', '')
                    print(f"❌ Order {order_ref_id} REJECTED: {status_message}")
                    return 'REJECTED'
                elif status == 'complete' and is_normal_order:
                    print(f"✅ Order {order_ref_id} COMPLETED")
                    return 'COMPLETED'
        except Exception as e:
            print(f"Error processing portfolio update: {e}")
            import traceback
            traceback.print_exc()
            return 'ERROR'


    @retry(stop_max_attempt_number=3, wait_fixed=1000)
    async def track_stop_loss_and_target(self, websocket):
        """
        Track highest prices for CE and PE options between 9:17-9:30.
        
        Args:
            websocket: WebSocket connection
        """
        print(f"📈 Tracking stop loss and target...")


        
        # Subscribe to sensex feed
        data = {
            "guid": "sensex_sub",
            "method": "sub",
            "data": {
                "mode": "ltpc",
                "instrumentKeys": [self.instrument_key]
            }
        }
        binary_data = json.dumps(data).encode('utf-8')
        await websocket.send(binary_data)
        
    
        stop_loss_price = self.ltp_order_price - (self.ltp_order_price * self.stop_loss_percentage / 100)
        target_price = self.ltp_order_price + (self.ltp_order_price * self.target_percentage / 100)

        while True:
            try:
                # Receive message with timeout
                message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                decoded_data = decode_protobuf(message)
                data_dict = MessageToDict(decoded_data)

                # Extract prices for CE
                if 'feeds' in data_dict and self.instrument_key in data_dict['feeds']:
                    data_ik = self.extract_l1_ohlc(data_dict)
                    ltp = data_ik.get('ltp', 0)

                    print('this is ltp', ltp)

                    if ltp <= stop_loss_price:
                        print('this is stop_loss_price', stop_loss_price)
                        response = self.sellStock(
                            quantity=self.quantity,
                            sell_price=stop_loss_price
                        ).data.order_ids[0]
                        print('this is the response', response)
                        print(f"✅ Stop loss price {stop_loss_price} reached")
                        return 'STOP_LOSS'

                    if ltp >= target_price:
                        print('this is target_price', target_price)
                        response = self.sellStock(
                            quantity=self.quantity,
                            sell_price=target_price
                        ).data.order_ids[0]
                        print('this is the response', response)
                        print(f"✅ Target price {target_price} reached")
                        return 'TARGET'

            except asyncio.TimeoutError:
                # No message in 1s – keep monitoring, loop again
                continue
            except Exception as e:
                print(f"Error tracking prices: {e}")
                continue
    
    


    async def normal_gtt_execution(self,websocket,buy_price,quantity):
        """Main strategy execution function."""
        print("=" * 60)
        print("🚀 Starting Trading Strategy")
        print("=" * 60)
        
        # Setup portfolio streamer for order tracking
        await asyncio.sleep(1)
        self.setup_portfolio_streamer()
        
        try:

            entry_taken = await self.normal_order_execution(websocket,buy_price=buy_price,quantity=quantity)

            if entry_taken:
                status = await self.monitor_portfolio_updates()
                if status == 'COMPLETED':
                    status = await self.track_stop_loss_and_target(websocket)
                    if status == 'TARGET':
                        print(f"✅ {status} order placed")
                        return 
                    else:
                        print(f"❌ {status} order not placed")
                        return
                         
        except Exception as e:
            print(f"❌ Error in strategy execution: {e}")
            import traceback
            traceback.print_exc()
        
        print("=" * 60)
        print("🏁 Trading Strategy Completed")
        print("=" * 60)




        

def verify_access_token(access_token):
    """
    Verify if the access token is valid by making a test API call.
    
    Args:
        access_token: Upstox access token to verify
        
    Returns:
        tuple: (is_valid: bool, message: str)
    """
    if not access_token or not access_token.strip():
        return False, "❌ Access token is empty"
    
    try:
        # Use market data feed authorization endpoint to verify token
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {access_token.strip()}'
        }
        url = 'https://api.upstox.com/v3/feed/market-data-feed/authorize'
        
        response = requests.get(url=url, headers=headers, timeout=10)
        response_data = response.json()
        
        # Check if request was successful
        if response.status_code == 200:
            if response_data.get('status') == 'success' or 'data' in response_data:
                return True, "✅ Access token is valid"
            else:
                error_msg = response_data.get('errors', [{}])[0].get('message', 'Unknown error')
                return False, f"❌ Token validation failed: {error_msg}"
        elif response.status_code == 401:
            error_msg = response_data.get('errors', [{}])[0].get('message', 'Unauthorized')
            return False, f"❌ Invalid or expired token: {error_msg}"
        else:
            error_msg = response_data.get('errors', [{}])[0].get('message', f'HTTP {response.status_code}')
            return False, f"❌ API Error: {error_msg}"
            
    except requests.exceptions.Timeout:
        return False, "❌ Request timeout. Please check your internet connection."
    except requests.exceptions.ConnectionError:
        return False, "❌ Connection error. Please check your internet connection."
    except requests.exceptions.RequestException as e:
        return False, f"❌ Network error: {str(e)}"
    except Exception as e:
        return False, f"❌ Unexpected error: {str(e)}"


    
        
    
# Test code - only run when script is executed directly, not when imported
# NSE_INDEX|Nifty 50

# data = {'feeds': {'BSE_FO|1127928': {'fullFeed': {'marketFF': {'ltpc': {'ltp': 255.0, 'ltt': '1763529366611', 'ltq': '40', 'cp': 386.2}, 'marketLevel': {'bidAskQuote': [{'bidQ': '80', 'bidP': 254.6, 'askQ': '60', 'askP': 254.9}, {'bidQ': '20', 'bidP': 254.55, 'askQ': '40', 'askP': 255.0}, {'bidQ': '20', 'bidP': 254.5, 'askQ': '1080', 'askP': 255.05}, {'bidQ': '160', 'bidP': 254.4, 'askQ': '340', 'askP': 255.1}, {'bidQ': '340', 'bidP': 254.35, 'askQ': '340', 'askP': 255.15}]}, 'optionGreeks': {'delta': -0.4796, 'theta': -112.3274, 'gamma': 0.0006, 'vega': 19.3795, 'rho': -1.3444}, 'marketOHLC': {'ohlc': [{'interval': '1d', 'open': 385.95, 'high': 488.35, 'low': 235.6, 'close': 255.0, 'vol': '9027620', 'ts': '1763490600000'}, {'interval': 'I1', 'open': 260.5, 'high': 261.35, 'low': 255.4, 'close': 255.8, 'vol': '142360', 'ts': '1763529300000'}]}, 'atp': 296.86, 'vtt': '9027620', 'oi': 1416020.0, 'iv': 0.1387786865234375, 'tbq': 188240.0, 'tsq': 263140.0}}, 'requestMode': 'full_d5'}, 'BSE_FO|1128472': {'fullFeed': {'marketFF': {'ltpc': {'ltp': 228.1, 'ltt': '1763529365954', 'ltq': '40', 'cp': 239.35}, 'marketLevel': {'bidAskQuote': [{'bidQ': '160', 'bidP': 227.8, 'askQ': '20', 'askP': 228.3}, {'bidQ': '80', 'bidP': 227.75, 'askQ': '600', 'askP': 228.35}, {'bidQ': '220', 'bidP': 227.7, 'askQ': '160', 'askP': 228.4}, {'bidQ': '260', 'bidP': 227.65, 'askQ': '220', 'askP': 228.45}, {'bidQ': '680', 'bidP': 227.6, 'askQ': '180', 'askP': 228.5}]}, 'optionGreeks': {'delta': 0.5234, 'theta': -88.2644, 'gamma': 0.0008, 'vega': 19.3711, 'rho': 1.4507}, 'marketOHLC': {'ohlc': [{'interval': '1d', 'open': 239.2, 'high': 249.05, 'low': 125.75, 'close': 228.1, 'vol': '18783540', 'ts': '1763490600000'}, {'interval': 'I1', 'open': 219.35, 'high': 226.75, 'low': 219.35, 'close': 226.75, 'vol': '126180', 'ts': '1763529300000'}]}, 'atp': 191.32, 'vtt': '18783540', 'oi': 1438320.0, 'iv': 0.109100341796875, 'tbq': 238620.0, 'tsq': 226160.0}}, 'requestMode': 'full_d5'}}, 'currentTs': '1763529366451'}
# dat = am.extract_i1_ohlc(data,'BSE_FO|1127928')
# # dat.get('ltpc', {}).get('ltp', 0) if data.get('ltpc') else 0
# print(dat.get('ltpc', {})['ltp'])


# data = am.get_all_gtt_orders()
# print('this is the data of all gtt orders',data)

# adata = am.buyStock(quantity=100,buy_price=255.0,instrument_key=instrument_key)
# print(adata,'this is the adata')


# response = am.cancel_gtt_order('GTT-C25101200006152')
# print('this is the response of the cancel gtt order',response)
# id = am.get_gtt_order_details('GTT-C25091200197924')
# print(id)

# am = AlgoKM(instrument_key='NSE_INDEX|Nifty 50',access_token=access_token,tick_size=True,buy_percentage=0,stop_loss_percentage=0.08,target_percentage=0.08,product='I',validity='DAY',order_type='LIMIT',weekday=1,exchange='NSE')  

# data = am.get_option_contracts_response(expiry_date='2026-03-10')
# print('this is the data of the option contracts', data)
