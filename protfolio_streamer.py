"""
Portfolio Stream Feed
Connects to Upstox Portfolio Stream Feed WebSocket to receive real-time updates
on orders, GTT orders, positions, and holdings.

Usage:
    # Basic usage - subscribe to all update types
    streamer = PortfolioStreamer(update_types=['order', 'gtt_order', 'position', 'holding'])
    await streamer.run()
    
    # Subscribe only to orders
    streamer = PortfolioStreamer(update_types=['order'])
    await streamer.run()
    
    # Use custom access token
    streamer = PortfolioStreamer(access_token='your_token', update_types=['gtt_order'])
    await streamer.run()

Note:
    - The WebSocket automatically redirects (302) to the authorized endpoint
    - Heartbeat/ping frames are handled automatically by the websockets library
    - Access token can be provided as parameter or via .env file as 'access_token'
"""

import asyncio
import json
import ssl
import websockets
import os
from dotenv import load_dotenv
from datetime import datetime
import pytz

# Load environment variables
load_dotenv()
my_access_token = os.getenv('access_token')


class PortfolioStreamer:
    """Class to handle portfolio stream feed WebSocket connection."""
    
    def __init__(self, access_token=None, update_types=None):
        """
        Initialize Portfolio Streamer.
        
        Args:
            access_token: Upstox access token (defaults to env variable)
            update_types: List of update types to subscribe to.
                         Options: 'order', 'gtt_order', 'position', 'holding'
                         If None, defaults to 'order' only
        """
        self.access_token = access_token or my_access_token
        if not self.access_token:
            raise ValueError("Access token is required. Set it as parameter or in .env file as 'access_token'")
        
        self.update_types = update_types or ['order']
        self.websocket = None
        self.ist = pytz.timezone("Asia/Kolkata")
        self.running = False
        
    def _build_url(self):
        """Build WebSocket URL with query parameters."""
        base_url = "wss://api.upstox.com/v2/feed/portfolio-stream-feed"
        
        if self.update_types:
            # URL encode the update types (comma-separated)
            update_types_str = ",".join(self.update_types)
            url = f"{base_url}?update_types={update_types_str}"
        else:
            url = base_url
        
        return url
    
    def _build_headers(self):
        """Build WebSocket headers for authentication."""
        # Return as list of tuples for websockets library
        return [
            ('Authorization', f'Bearer {self.access_token}'),
            ('Accept', '*/*')
        ]
    
    def _format_timestamp(self, timestamp_ns):
        """Convert nanosecond timestamp to readable format."""
        if timestamp_ns:
            # Convert nanoseconds to seconds
            timestamp_s = timestamp_ns / 1_000_000_000
            dt = datetime.fromtimestamp(timestamp_s, tz=self.ist)
            return dt.strftime("%Y-%m-%d %H:%M:%S %Z")
        return None
    
    def _process_order_update(self, message):
        """Process order update message."""
        print("\n" + "="*80)
        print("[ORDER] ORDER UPDATE")
        print("="*80)
        print(f"Update Type: {message.get('update_type', 'N/A')}")
        print(f"Order ID: {message.get('order_id', 'N/A')}")
        print(f"Status: {message.get('status', 'N/A')}")
        print(f"Transaction Type: {message.get('transaction_type', 'N/A')}")
        print(f"Quantity: {message.get('quantity', 'N/A')}")
        print(f"Price: {message.get('price', 'N/A')}")
        print(f"Product: {message.get('product', 'N/A')}")
        print(f"Instrument Token: {message.get('instrument_token', 'N/A')}")
        print(f"Trading Symbol: {message.get('trading_symbol', message.get('tradingsymbol', 'N/A'))}")
        print(f"Exchange: {message.get('exchange', 'N/A')}")
        print(f"Order Type: {message.get('order_type', 'N/A')}")
        print(f"Validity: {message.get('validity', 'N/A')}")
        print(f"Tag: {message.get('tag', 'N/A')}")
        
        if 'filled_quantity' in message:
            print(f"Filled Quantity: {message.get('filled_quantity', 0)}")
        if 'pending_quantity' in message:
            print(f"Pending Quantity: {message.get('pending_quantity', 0)}")
        if 'disclosed_quantity' in message:
            print(f"Disclosed Quantity: {message.get('disclosed_quantity', 0)}")
        if 'trigger_price' in message:
            print(f"Trigger Price: {message.get('trigger_price', 0)}")
        if 'average_price' in message:
            print(f"Average Price: {message.get('average_price', 0)}")
        if 'message' in message and message['message']:
            print(f"Message: {message['message']}")
        
        print("="*80)
    
    def _process_gtt_order_update(self, message):
        """Process GTT order update message."""
        print("\n" + "="*80)
        print("[GTT] GTT ORDER UPDATE")
        print("="*80)
        print(f"Update Type: {message.get('update_type', 'N/A')}")
        print(f"GTT Order ID: {message.get('gtt_order_id', 'N/A')}")
        print(f"Type: {message.get('type', 'N/A')}")
        print(f"Exchange: {message.get('exchange', 'N/A')}")
        print(f"Instrument Token: {message.get('instrument_token', 'N/A')}")
        print(f"Trading Symbol: {message.get('trading_symbol', message.get('tradingsymbol', 'N/A'))}")
        print(f"Quantity: {message.get('quantity', 'N/A')}")
        print(f"Product: {message.get('product', 'N/A')}")
        
        created_at = self._format_timestamp(message.get('created_at'))
        expires_at = self._format_timestamp(message.get('expires_at'))
        print(f"Created At: {created_at}")
        print(f"Expires At: {expires_at}")
        
        # Process rules
        rules = message.get('rules', [])
        if rules:
            print(f"\n[RULES] Rules ({len(rules)}):")
            for i, rule in enumerate(rules, 1):
                print(f"\n  Rule {i}:")
                print(f"    Strategy: {rule.get('strategy', 'N/A')}")
                print(f"    Status: {rule.get('status', 'N/A')}")
                print(f"    Trigger Type: {rule.get('trigger_type', 'N/A')}")
                print(f"    Trigger Price: {rule.get('trigger_price', 'N/A')}")
                print(f"    Transaction Type: {rule.get('transaction_type', 'N/A')}")
                if rule.get('order_id'):
                    print(f"    Order ID: {rule.get('order_id')}")
                if rule.get('trailing_gap') is not None:
                    print(f"    Trailing Gap: {rule.get('trailing_gap')}")
                if rule.get('message'):
                    print(f"    Message: {rule.get('message')}")
        
        print("="*80)
    
    def _process_position_update(self, message):
        """Process position update message."""
        print("\n" + "="*80)
        print("[POSITION] POSITION UPDATE")
        print("="*80)
        print(f"Update Type: {message.get('update_type', 'N/A')}")
        print(f"Exchange: {message.get('exchange', 'N/A')}")
        print(f"Instrument Token: {message.get('instrument_token', 'N/A')}")
        print(f"Trading Symbol: {message.get('trading_symbol', message.get('tradingsymbol', 'N/A'))}")
        print(f"Product: {message.get('product', 'N/A')}")
        print(f"Quantity: {message.get('quantity', 0)}")
        print(f"Average Price: {message.get('average_price', 0)}")
        print(f"Last Price: {message.get('last_price', 0)}")
        print(f"P&L: {message.get('pnl', 0)}")
        print(f"Unrealized P&L: {message.get('unrealized_pnl', 0)}")
        print(f"Realized P&L: {message.get('realized_pnl', 0)}")
        print("="*80)
    
    def _process_holding_update(self, message):
        """Process holding update message."""
        print("\n" + "="*80)
        print("[HOLDING] HOLDING UPDATE")
        print("="*80)
        print(f"Update Type: {message.get('update_type', 'N/A')}")
        print(f"Exchange: {message.get('exchange', 'N/A')}")
        print(f"Instrument Token: {message.get('instrument_token', 'N/A')}")
        print(f"Trading Symbol: {message.get('trading_symbol', message.get('tradingsymbol', 'N/A'))}")
        print(f"Quantity: {message.get('quantity', 0)}")
        print(f"Average Price: {message.get('average_price', 0)}")
        print(f"Last Price: {message.get('last_price', 0)}")
        print(f"P&L: {message.get('pnl', 0)}")
        print("="*80)
    
    def _process_message(self, message_str):
        """Process incoming WebSocket message."""
        try:
            message = json.loads(message_str)
            update_type = message.get('update_type', 'unknown')
            
            current_time = datetime.now(self.ist).strftime("%Y-%m-%d %H:%M:%S %Z")
            print(f"\n[TIME] Received at: {current_time}")
            
            if update_type == 'order':
                self._process_order_update(message)
            elif update_type == 'gtt_order':
                self._process_gtt_order_update(message)
            elif update_type == 'position':
                self._process_position_update(message)
            elif update_type == 'holding':
                self._process_holding_update(message)
            else:
                print(f"\n[WARN] Unknown update type: {update_type}")
                print(json.dumps(message, indent=2))
            
        except json.JSONDecodeError as e:
            print(f"\n[ERROR] Error decoding JSON message: {e}")
            print(f"Raw message: {message_str}")
        except Exception as e:
            print(f"\n[ERROR] Error processing message: {e}")
            print(f"Message: {message_str}")
    
    async def connect(self):
        """Connect to the portfolio stream feed WebSocket."""
        url = self._build_url()
        headers = self._build_headers()
        
        # Create SSL context
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        print(f"[CONNECT] Connecting to Portfolio Stream Feed...")
        print(f"URL: {url}")
        print(f"Update Types: {', '.join(self.update_types)}")
        
        try:
            # Connect to WebSocket with headers
            # Note: websockets library handles redirects automatically during handshake
            self.websocket = await websockets.connect(
                url,
                additional_headers=headers,
                ssl=ssl_context
            )
            
            print("[OK] Connected successfully!")
            print("[LISTEN] Listening for updates...\n")
            self.running = True
            
        except Exception as e:
            print(f"[ERROR] Connection error: {e}")
            raise
    
    async def listen(self):
        """Listen for messages from the WebSocket."""
        if not self.websocket:
            raise RuntimeError("Not connected. Call connect() first.")
        
        try:
            async for message in self.websocket:
                # Handle text messages (JSON)
                if isinstance(message, str):
                    self._process_message(message)
                # Handle binary messages (shouldn't happen for this feed, but handle gracefully)
                elif isinstance(message, bytes):
                    try:
                        message_str = message.decode('utf-8')
                        self._process_message(message_str)
                    except UnicodeDecodeError:
                        print(f"\n[WARN] Received binary message that couldn't be decoded")
                # Handle ping/pong frames (automatically handled by websockets library)
                
        except websockets.exceptions.ConnectionClosed:
            print("\n[CONNECT] WebSocket connection closed")
            self.running = False
        except Exception as e:
            print(f"\n[ERROR] Error in listen loop: {e}")
            self.running = False
            raise
    
    async def disconnect(self):
        """Disconnect from the WebSocket."""
        if self.websocket:
            await self.websocket.close()
            print("\n[DISCONNECT] Disconnected from Portfolio Stream Feed")
            self.running = False
    
    async def run(self):
        """Run the streamer (connect and listen)."""
        try:
            await self.connect()
            await self.listen()
        except KeyboardInterrupt:
            print("\n\n[WARN] Interrupted by user")
        except Exception as e:
            print(f"\n[ERROR] Error: {e}")
        finally:
            await self.disconnect()


async def main():
    """Main function to run the portfolio streamer."""
    # Example: Subscribe to all update types
    # You can customize this list: ['order'], ['gtt_order'], ['order', 'position'], etc.
    update_types = ['order', 'gtt_order', 'position', 'holding']
    
    streamer = PortfolioStreamer(update_types=update_types)
    await streamer.run()


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())

