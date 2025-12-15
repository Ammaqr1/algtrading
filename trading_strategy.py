"""
Trading Strategy Implementation
Main strategy execution that:
1. Connects to Upstox websocket at 9:17 AM
2. Captures Sensex price and gets CE/PE option contracts
3. Tracks highest prices for both options between 9:17-9:30
4. Places buy orders at highest price with -1.25% stop loss and +2.5% target
5. Manages re-entry logic (one additional order after stop loss)
6. Tracks order status via PortfolioDataStreamer
"""

import asyncio
from doctest import set_unittest_reportflags
import json
import ssl
import websockets
import requests
from google.protobuf.json_format import MessageToDict
import MarketDataFeed_pb2 as pb
import os
from dotenv import load_dotenv
from mani import AlgoKM, verify_access_token
import pytz
from datetime import datetime, time as time_class
import time as time_module
import threading
import queue
import upstox_client


load_dotenv()
my_access_token = os.getenv('access_token')



def get_market_data_feed_authorize_v3(access_token):
    """Get authorization for market data feed."""
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    url = 'https://api.upstox.com/v3/feed/market-data-feed/authorize'
    api_response = requests.get(url=url, headers=headers)
    return api_response.json()


def decode_protobuf(buffer):
    """Decode protobuf message."""
    feed_response = pb.FeedResponse()
    feed_response.ParseFromString(buffer)
    return feed_response


class TradingStrategy:
    """Main trading strategy class that orchestrates the entire flow."""
    
    def __init__(self, access_token, quantity=1, start_time=None, end_time=None, exit_time=None,tick_size=False,sensex_price_at_917=None,at_the_money_time=None):
        """
        Initialize trading strategy.
        
        Args:
            access_token: Upstox access token
            quantity: Quantity for option orders (default: 1)
            start_time: Start time as time object (default: 9:17 AM)
            end_time: End time as time object (default: 9:30 AM)
            exit_time: Exit time as time object (default: 3:30 PM)
        """
        self.access_token = access_token
        self.quantity = quantity
        self.ist = pytz.timezone("Asia/Kolkata")
        
        # Sensex instrument key
        self.sensex_instrument_key = 'BSE_INDEX|SENSEX'
        self.tick_size = tick_size
        
        # Initialize AlogKM instance for Sensex
        self.sensex_trader = AlgoKM(
            access_token=access_token,
            instrument_key=self.sensex_instrument_key,
            tick_size=self.tick_size
        )
        
        # Pre-fetch option contracts in background for faster lookup later
        # self._pre_fetch_options()
        
        # State variables
        self.at_the_money_time = at_the_money_time
        self.sensex_price_at_917 = sensex_price_at_917
        self.ce_instrument_key = None
        self.pe_instrument_key = None
        self.ce_high_price = 0
        self.pe_high_price = 0
        self.buy_price = 0
        self.ce_trader = None
        self.pe_trader = None
        
        # Order tracking
        self.ce_gtt_order_id = None
        self.pe_gtt_order_id = None
        self.ce_stoploss_hit_count = 0
        self.pe_stoploss_hit_count = 0
        self.ce_reentry_placed = False
        self.pe_reentry_placed = False
        self.reentry_placed = False
        
        # Time windows - use provided times or defaults
        if at_the_money_time is None:
            at_the_money_time = time_class(9, 17)  # 9:17 AM
        if start_time is None:
            start_time = time_class(10,33)  # 9:17 AM
        if end_time is None:
            end_time = time_class(12, 50)    # 9:30 AM
        if exit_time is None:
            exit_time = time_class(22, 30)   # 3:30 PM

   
        
        self.at_the_money_time = at_the_money_time
        self.start_time = start_time
        self.end_time = end_time
        self.exit_time = exit_time
       

        # Portfolio streamer for order tracking
        self.portfolio_streamer = None
        self.portfolio_thread = None
        self.portfolio_update_queue = queue.Queue()
    
    def _pre_fetch_options(self):
        """Pre-fetch option contracts in background thread for faster lookup."""
        def fetch_in_background():
            try:
                expiry_date = self.sensex_trader.get_thursday_date()
                print(f"🔄 Pre-fetching option contracts for expiry {expiry_date} in background...")
                self.sensex_trader.pre_fetch_option_contracts(
                    expiry_date=expiry_date,
                    instrument_key=self.sensex_instrument_key
                )
            except Exception as e:
                print(f"⚠️ Warning: Could not pre-fetch option contracts: {e}")
                print("   Will fetch when needed (may be slower)")
        
        # Start background thread
        fetch_thread = threading.Thread(target=fetch_in_background, daemon=True)
        fetch_thread.start()
        print("✅ Option contracts pre-fetch started in background")
        
    async def wait_until_time(self, target_time, silent=False,):
        """
        Wait until target time is reached.
        
        Args:
            target_time: time object representing target time
            silent: If True, don't print when time is reached
        """
        while True:
            now = datetime.now(self.ist).time()
            if now >= target_time:
                if not silent:
                    print(f"⏰ Target time {target_time.strftime('%H:%M')} reached!")
                return
           
            await asyncio.sleep(1)
        
    
    def setup_portfolio_streamer(self):
        """Set up PortfolioDataStreamer to track GTT order updates."""
        try:
            configuration = upstox_client.Configuration(sandbox=False)
            configuration.access_token = self.access_token
            
            self.portfolio_streamer = upstox_client.PortfolioDataStreamer(
                upstox_client.ApiClient(configuration),
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
            
            # Check exit time
            if now >= self.exit_time:
                print(f"⏰ Exit time {self.exit_time.strftime('%H:%M')} reached. Stopping portfolio monitoring.")
                break
            
            try:
                # Wait for message with timeout
                try:
                    order_data = self.portfolio_update_queue.get(timeout=1.0)
                    await self.process_portfolio_update(order_data)
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

        stoploss_index = 0
        target_index = 0
        entry_index = 0


        try:
            update_type = order_data.get('update_type', '')
            
            # Process GTT order updates
            if update_type == 'gtt_order':
                gtt_order_id = order_data.get('gtt_order_id', '')
                rules = order_data.get('rules', [])
                
                # Check if this GTT order matches our CE or PE order
                is_ce_order = (self.ce_gtt_order_id and gtt_order_id == self.ce_gtt_order_id)
                is_pe_order = (self.pe_gtt_order_id and gtt_order_id == self.pe_gtt_order_id)
                
                if not (is_ce_order or is_pe_order):
                    # Not our order, skip
                    return


                for i,data in enumerate(rules):
                    if data['strategy'] == 'STOPLOSS':
                        stoploss_index = i
                    elif data['strategy'] == 'TARGET':
                        target_index = i
                    elif data['strategy'] == 'ENTRY':
                        entry_index = i


                stoploss_rule = rules[stoploss_index]
                target_rule = rules[target_index]
                entry_rule = rules[entry_index]



                if entry_rule['strategy'] == 'ENTRY' and entry_rule['status'] == 'FAILED':
                    message = entry_rule.get('message', '')
                    print(f"❌ GTT Order {gtt_order_id} ENTRY rule FAILED: {message}")
                    
                    # Handle re-entry based on which order failed
                    if is_ce_order and not self.reentry_placed:
                        print(f"🔄 Attempting CE re-entry for failed order...")
                        try:
                            self.ce_gtt_order_id = self.ce_trader.buyStock(
                                quantity=self.quantity,
                                buy_price=self.ce_high_price,
                                instrument_key=self.ce_instrument_key
                            ).data.gtt_order_ids[0]
                            print(f"✅ CE re-entry order placed. GTT Order ID: {self.ce_gtt_order_id}")
                            self.reentry_placed = True
                        except Exception as e:
                            print(f"❌ Error placing CE re-entry order: {e}")
                    
                    elif is_pe_order and not self.reentry_placed:
                        print(f"🔄 Attempting PE re-entry for failed order...")
                        try:
                            self.pe_gtt_order_id = self.pe_trader.buyStock(
                                quantity=self.quantity,
                                buy_price=self.pe_high_price,
                                instrument_key=self.pe_instrument_key
                            ).data.gtt_order_ids[0]
                            print(f"✅ PE re-entry order placed. GTT Order ID: {self.pe_gtt_order_id}")
                            self.reentry_placed = True
                        except Exception as e:
                            print(f"❌ Error placing PE re-entry order: {e}")
                
                # Check if STOPLOSS rule triggered
                elif stoploss_rule['status'] in ['ACTIVE', 'TRIGGERED','CANCELLED','COMPLETED'] and target_rule['status'] == 'CANCELLED':

                    if is_ce_order:
                        self.ce_stoploss_hit_count += 1
                        if self.ce_stoploss_hit_count + self.pe_stoploss_hit_count == 2:
                            self.sensex_trader.cancel_gtt_order(self.pe_gtt_order_id)
                            print('The pure 9:17 execution run sucessfully')
                            return

                        if not self.reentry_placed:
                            print(f"🛑 CE Stop Loss Hit! Placing re-entry order...")
                            try:
                                self.ce_gtt_order_id = self.ce_trader.buyStock(
                                    quantity=self.quantity,
                                    buy_price=self.ce_high_price,
                                    instrument_key=self.ce_instrument_key
                                )
                                print(f"✅ CE re-entry order placed. GTT Order ID: {self.ce_gtt_order_id}")
                                self.reentry_placed = True
                                self.ce_reentry_placed = True
                            except Exception as e:
                                print(f"❌ Error placing CE re-entry order: {e}")
                        
                    elif is_pe_order:

                        self.pe_stoploss_hit_count += 1
                        if self.pe_stoploss_hit_count + self.ce_stoploss_hit_count == 2:
                            self.sensex_trader.cancel_gtt_order(self.ce_gtt_order_id)
                            print('The Pure 9:17 execution run succesfully')
                            return

                        if not self.reentry_placed:
                            print(f"🛑 PE Stop Loss Hit! Placing re-entry order...")
                            try:
                                self.pe_gtt_order_id = self.pe_trader.buyStock(
                                    quantity=self.quantity,
                                    buy_price=self.pe_high_price,
                                    instrument_key=self.pe_instrument_key
                                )
                                print(f"✅ PE re-entry order placed. GTT Order ID: {self.pe_gtt_order_id}")
                                self.reentry_placed = True
                                self.pe_reentry_placed = True
                            except Exception as e:
                                print(f"❌ Error placing PE re-entry order: {e}")
                
                # Check if TARGET rule triggered
                elif target_rule['strategy'] == 'TARGET' and target_rule['status'] in ['ACTIVE', 'TRIGGERED','COMPLETED']:
                    if is_ce_order:
                        print(f"🎯 CE Target Hit! Order completed.")
                        self.reentry_placed = True
                        self.ce_gtt_order_id = None  # Stop monitoring
                        print('cancelling the PE order')
                        response = self.ce_trader.cancel_gtt_order(self.pe_gtt_order_id)
                        if response['status'] == 'success':
                            print('the PE order is cancelled Our CE target is hit')
                            return
                        else:
                            print('Error cancelling the PE order Retrying...')
                            response = self.ce_trader.cancel_gtt_order(self.pe_gtt_order_id)
                            if response['status'] == 'success':
                                print('the PE order is cancelled Our CE target is hit')
                                return
                            else:
                                print('Error cancelling in the second attempt the PE order Retrying...')
                                print('Please cancel the PE order manually')
                                return
                    elif is_pe_order:
                        print(f"🎯 PE Target Hit! Order completed.")
                        self.reentry_placed = True
                        self.pe_gtt_order_id = None  # Stop monitoring
                        print('cancelling the CE order')
                        response = self.pe_trader.cancel_gtt_order(self.ce_gtt_order_id)
                        if response['status'] == 'success':
                            print('the CE order is cancelled Our PE target is hit')
                            return
                        else:
                            print('Error cancelling the CE order Retrying...')
                            response = self.pe_trader.cancel_gtt_order(self.ce_gtt_order_id)
                            if response['status'] == 'success':
                                print('the CE order is cancelled Our PE target is hit')
                                return
                            else:
                                print('Error cancelling in the second attempt the CE order Retrying...')
                                print('Please cancel the CE order manually')
                                return
            # Process regular order updates
            # elif update_type == 'order':
            #     order_ref_id = order_data.get('order_ref_id', '')
            #     status = order_data.get('status', '').lower()
                
            #     # Check if this order matches our GTT orders
            #     is_ce_order = (self.ce_gtt_order_id and order_ref_id == self.ce_gtt_order_id)
            #     is_pe_order = (self.pe_gtt_order_id and order_ref_id == self.pe_gtt_order_id)
                
            #     if not (is_ce_order or is_pe_order):
            #         # Not our order, skip
            #         return
                
            #     # Check if order was rejected
            #     if status == 'rejected':
            #         status_message = order_data.get('status_message', '')
            #         print(f"❌ Order {order_ref_id} REJECTED: {status_message}")
                    
            #         # Handle re-entry for rejected orders
            #         if is_ce_order and not self.ce_reentry_placed:
            #             print(f"🔄 Attempting CE re-entry for rejected order...")
            #             try:
            #                 self.ce_gtt_order_id = self.ce_trader.buyStock(
            #                     quantity=self.quantity,
            #                     buy_price=self.buy_price,
            #                     instrument_key=self.ce_instrument_key
            #                 ).data.gtt_order_ids[0]
            #                 print(f"✅ CE re-entry order placed. GTT Order ID: {self.ce_gtt_order_id}")
            #                 self.ce_reentry_placed = True
            #             except Exception as e:
            #                 print(f"❌ Error placing CE re-entry order: {e}")
                    
            #         elif is_pe_order and not self.pe_reentry_placed:
            #             print(f"🔄 Attempting PE re-entry for rejected order...")
            #             try:
            #                 self.pe_gtt_order_id = self.pe_trader.buyStock(
            #                     quantity=self.quantity,
            #                     buy_price=self.buy_price,
            #                     instrument_key=self.pe_instrument_key
            #                 ).data.gtt_order_ids[0]
            #                 print(f"✅ PE re-entry order placed. GTT Order ID: {self.pe_gtt_order_id}")
            #                 self.pe_reentry_placed = True
            #             except Exception as e:
            #                 print(f"❌ Error placing PE re-entry order: {e}")
                
        except Exception as e:
            print(f"Error processing portfolio update: {e}")
            import traceback
            traceback.print_exc()
    
    async def capture_sensex_price_at_917(self, websocket):
        """
        Wait until 9:17 AM and capture Sensex price.
        
        Args:
            websocket: WebSocket connection
            
        Returns:
            float: Sensex price at 9:17
        """
        # Check if current time equals at_the_money_time
        now = datetime.now(self.ist).time()
        current_time_only = time_class(now.hour, now.minute)
        
        if current_time_only > self.at_the_money_time:
            print(f"⏳ The at-the-money time ({self.at_the_money_time.strftime('%H:%M')}) has already passed. Fetching Sensex price from historical data...")
            sensex_price = self.sensex_trader.price_at_917(self.at_the_money_time)
            if not sensex_price:
                print(f"⚠️ Sensex price is not available at {self.at_the_money_time.strftime('%H:%M')}, waiting for 30 seconds")
                time_module.sleep(30)
                sensex_price = self.sensex_trader.price_at_917(self.at_the_money_time)
            print(f"✅ Sensex price at {self.at_the_money_time.strftime('%H:%M')}: ₹{sensex_price}")
            return sensex_price

        await self.wait_until_time(self.at_the_money_time, silent=False)
        
        print(f"📊 Capturing Sensex price at {self.at_the_money_time.strftime('%H:%M')}...")
        
        # Subscribe to Sensex feed if not already subscribed
        data = {
            "guid": "sensex_sub",
            "method": "sub",
            "data": {
                "mode": "ltpc",
                "instrumentKeys": [self.sensex_instrument_key]
            }
        }
        binary_data = json.dumps(data).encode('utf-8')
        await websocket.send(binary_data)
        
        # Receive messages until we get a valid price
        max_attempts = 10
        attempt = 0
        
        while attempt < max_attempts:
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                decoded_data = decode_protobuf(message)
                data_dict = MessageToDict(decoded_data)
                result = self.sensex_trader.extract_l1_ohlc(data_dict)
                if result and result.get('ltp', 0) > 0:
                    sensex_price = result['ltp']
                    self.sensex_price_at_917 = sensex_price
                    print(f"✅ Sensex price at 9:17 AM: ₹{sensex_price}")
                    return sensex_price
                    
            except asyncio.TimeoutError:
                attempt += 1
                print(f"⏳ Waiting for Sensex price data... (attempt {attempt}/{max_attempts})")
            except Exception as e:
                print(f"Error capturing Sensex price: {e}")
                attempt += 1
        
        raise ValueError("Failed to capture Sensex price at 9:17 AM")
    
    def get_option_contracts_for_price(self, sensex_price):
        """
        Get CE and PE option contracts for the given Sensex price.
        
        Args:
            sensex_price: Current Sensex price
            
        Returns:
            tuple: (ce_instrument_key, pe_instrument_key)
        """
        print(f"🔍 Getting option contracts for Sensex price: ₹{sensex_price}")
        
        # Get Thursday expiry date
        expiry_date = self.sensex_trader.get_thursday_date()
        print(f"📅 Expiry date: {expiry_date}")
        
        # Get option contracts
        self.ce_instrument_key, self.pe_instrument_key = self.sensex_trader.get_option_contracts(
            sensex_price=sensex_price,
        )
        
        
        
        print(f"✅ CE Instrument Key: {self.ce_instrument_key}")
        print(f"✅ PE Instrument Key: {self.pe_instrument_key}")
        
        # Initialize traders for CE and PE
        self.ce_trader = AlgoKM(
            access_token=self.access_token,
            instrument_key=self.ce_instrument_key,
            tick_size=True
        )
        self.pe_trader = AlgoKM(
            access_token=self.access_token,
            instrument_key=self.pe_instrument_key,
            tick_size=True
        )
        
        return
    
    async def track_high_prices(self, websocket):
        """
        Track highest prices for CE and PE options between 9:17-9:30.
        
        Args:
            websocket: WebSocket connection
            ce_ik: CE instrument key
            pe_ik: PE instrument key
        """
        print(f"📈 Tracking high prices for CE and PE from {self.start_time.strftime('%H:%M')} to {self.end_time.strftime('%H:%M')}...")
        
        # Subscribe to both CE and PE feeds
        data = {
            "guid": "options_sub",
            "method": "sub",
            "data": {
                "mode": "full",
                "instrumentKeys": [self.ce_instrument_key, self.pe_instrument_key]
            }
        }
        binary_data = json.dumps(data).encode('utf-8')
        await websocket.send(binary_data)
        
        self.ce_high_price = 0
        self.pe_high_price = 0
        
        
        # Track until 9:30
        already_tracked = False
        silent = False
        
        last_ce_30_seconds = time_module.time()
        last_pe_30_seconds = time_module.time()
        while True:
            now = datetime.now(self.ist).time()
            
            # Check if we've passed 9:30
            if now > (time_class(self.start_time.hour,(self.start_time.minute + 1) % 60)):
                print(f"⏰ {self.end_time.strftime('%H:%M')} reached. Final high prices:")
                if not already_tracked:
                    ce_data = self.sensex_trader.intraday_history_per_minute(self.ce_instrument_key)
                    pe_data = self.sensex_trader.intraday_history_per_minute(self.pe_instrument_key)

                    self.ce_high_price = self.sensex_trader.highest_price_per_minute(ce_data,self.start_time,self.end_time,self.ce_high_price)
                    self.pe_high_price = self.sensex_trader.highest_price_per_minute(pe_data,self.start_time,self.end_time,self.pe_high_price)
                    already_tracked = True
                print(f"   CE High: ₹{self.ce_high_price}")
                print(f"   PE High: ₹{self.pe_high_price}")
                break
            
            # check if start time is reached
            if self.start_time <= now <= self.end_time and not already_tracked:

                ce_data = self.sensex_trader.intraday_history_per_minute(self.ce_instrument_key)
                pe_data = self.sensex_trader.intraday_history_per_minute(self.pe_instrument_key)

                silent = True
                already_tracked = True

                if not ce_data:
                    print(f"❌ CE data not available")
                    

                if not pe_data:
                    print(f"❌ PE data not available")
                    


                self.ce_high_price = self.sensex_trader.highest_price_per_minute(ce_data,self.start_time,self.end_time,self.ce_high_price)
                self.pe_high_price = self.sensex_trader.highest_price_per_minute(pe_data,self.start_time,self.end_time,self.pe_high_price)
                

            # Check exit time
            if now >= self.exit_time:
                print(f"⏰ Exit time {self.exit_time.strftime('%H:%M')} reached.")
                already_tracked = True

                break
            

            try:
                await self.wait_until_time(self.start_time, silent=silent)
                already_tracked = True
                silent = True
                    
                # Receive message with timeout
                message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                decoded_data = decode_protobuf(message)
                data_dict = MessageToDict(decoded_data)
                
                # Extract prices for CE
                if 'feeds' in data_dict and self.ce_instrument_key in data_dict['feeds']:
                    
                    data_ce_ik = self.sensex_trader.extract_i1_ohlc(data_dict,self.ce_instrument_key)
                    ce_ltp = data_ce_ik.get('ltpc', {})['ltp']

                    
                    if time_module.time() - last_ce_30_seconds >= 30:
                        last_ce_30_seconds = time_module.time()
                        self.ce_high_price = self.sensex_trader.highMarketValue(
                            self.ce_high_price, data_ce_ik['ohlc_i1']['high'])  

                    if ce_ltp > 0:
                        self.ce_high_price = self.sensex_trader.highMarketValue(
                            self.ce_high_price, ce_ltp
                        )
                
                # Extract prices for PE
                if 'feeds' in data_dict and self.pe_instrument_key in data_dict['feeds']:
                    
                    data_pe_ik = self.sensex_trader.extract_i1_ohlc(data_dict,self.pe_instrument_key)
                    pe_ltp = data_pe_ik.get('ltpc', {})['ltp']
                
                    if time_module.time() - last_pe_30_seconds >= 30:   
                        last_pe_30_seconds = time_module.time()
                        self.pe_high_price = self.sensex_trader.highMarketValue(
                            self.pe_high_price, data_pe_ik['ohlc_i1']['high'])  
                            
                            
                    if pe_ltp > 0:
                        self.pe_high_price = self.sensex_trader.highMarketValue(
                            self.pe_high_price, pe_ltp
                        )
                    
            except asyncio.TimeoutError:
                # Timeout is expected, continue tracking
                continue
            except Exception as e:
                print(f"Error tracking prices: {e}")
                continue
    
    def place_option_orders(self):
        """
        Place buy orders for both CE and PE at their respective highest prices.
        """
        if self.ce_high_price <= 0 or self.pe_high_price <= 0:
            print("❌ Cannot place orders: high prices not available")
            return
        
        self.buy_price = self.sensex_trader.highMarketValue(
            self.pe_high_price, self.ce_high_price
        )
    
        
        print(f"📝 Placing orders at high prices:")
        print(f"   CE: ₹{self.ce_high_price} (quantity: {self.quantity})")
        print(f"   PE: ₹{self.pe_high_price} (quantity: {self.quantity})")
        
        try:
            # Place CE order
            if self.ce_instrument_key and self.ce_high_price > 0 and not self.ce_gtt_order_id:
                self.ce_gtt_order_id = self.ce_trader.buyStock(
                    quantity=self.quantity,
                    buy_price=self.ce_high_price,
                    instrument_key=self.ce_instrument_key
                ).data.gtt_order_ids[0]
                print(f"✅ CE order placed. GTT Order ID: {self.ce_gtt_order_id}")
            
            # Place PE order
            if self.pe_instrument_key and self.pe_high_price > 0 and not self.pe_gtt_order_id:
                self.pe_gtt_order_id = self.pe_trader.buyStock(
                    quantity=self.quantity,
                    buy_price=self.pe_high_price,
                    instrument_key=self.pe_instrument_key
                ).data.gtt_order_ids[0]
                print(f"✅ PE order placed. GTT Order ID: {self.pe_gtt_order_id}")
                
        except Exception as e:
            print(f"❌ Error placing orders: {e}")
    
   
    async def execute_strategy(self):
        """Main strategy execution function."""
        print("=" * 60)
        print("🚀 Starting Trading Strategy")
        print("=" * 60)
        
        # Setup portfolio streamer for order tracking
        self.setup_portfolio_streamer()
        
        # Wait a bit for portfolio streamer to connect
        time_module.sleep(2)
        
        # Create SSL context
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        # Get market data feed authorization
        response = get_market_data_feed_authorize_v3(self.access_token)
        
        try:
            # Connect to WebSocket
            async with websockets.connect(
                response["data"]["authorized_redirect_uri"],
                ssl=ssl_context
            ) as websocket:
                print("✅ WebSocket connected")
                
                # Step 1: Capture Sensex price at 9:17
                if not self.sensex_price_at_917:
                    sensex_price = await self.capture_sensex_price_at_917(websocket)
          
                print('sensex price at 917',sensex_price)
                # Step 2: Get option contracts
                self.get_option_contracts_for_price(sensex_price)
                
                # # Step 3: Track high prices from 9:17 to 9:30
                if not self.ce_high_price and not self.pe_high_price:
                    await self.track_high_prices(websocket)

                # Step 4: Place orders after 9:30
                # self.place_option_orders()
                
                 # Step 5: Monitor orders for stop loss/target hits (run both monitoring functions concurrently)
                # await asyncio.gather(
                #     self.monitor_portfolio_updates()
                # )
                
        except Exception as e:
            print(f"❌ Error in strategy execution: {e}")
            import traceback
            traceback.print_exc()
        
        print("=" * 60)
        print("🏁 Trading Strategy Completed")
        print("=" * 60)


def main():
    """Main entry point."""
    if not my_access_token:
        print("❌ Error: access_token not found in environment variables")
        return
    
    strategy = TradingStrategy(access_token=my_access_token, quantity=20,at_the_money_time=time_class(9,17),tick_size=True)
    asyncio.run(strategy.execute_strategy())
    # strategy.run_portfolio_streamer()
    # strategy = TradingStrategy(access_token=my_access_token, quantity=1)
    # await strategy.execute_strategy()  # This will run run_portfolio_streamer automatically
    # time_module.sleep(60)  # Keep it running for testing


# if __name__ == "__main__":
#     main()

