import streamlit as st
import os
import sys

# Try to import required modules with error handling
try:
    import asyncio
    import json
    import ssl
    import websockets
    import requests
    from google.protobuf.json_format import MessageToDict
    import MarketDataFeed_pb2 as pb
    from dotenv import load_dotenv
    from mani import AlgoKM, verify_access_token
    import pytz
    from datetime import datetime
    import threading
    import queue
    import time
    
    IMPORTS_SUCCESS = True
    MISSING_IMPORTS = []
except ImportError as e:
    IMPORTS_SUCCESS = False
    MISSING_IMPORTS = str(e)
    # Set minimal imports for error display
    from datetime import datetime
    import queue

# Load environment variables if dotenv is available
if IMPORTS_SUCCESS:
    try:
        load_dotenv()
    except:
        pass

# Page configuration
st.set_page_config(
    page_title="GTT Order Execution Dashboard",
    page_icon="📈",
    layout="wide"
)

# Show error if imports failed
if not IMPORTS_SUCCESS:
    st.error("❌ **Import Error Detected**")
    st.error(f"Failed to import required modules: {MISSING_IMPORTS}")
    st.warning("""
    **Please activate your virtual environment first:**
    
    ```bash
    cd /home/ammar/Documents/algo/algtrading
    source venv/bin/activate
    streamlit run gtt_frontend.py
    ```
    
    Or install missing packages:
    ```bash
    pip install streamlit websockets requests python-dotenv pytz protobuf upstox-python-sdk
    ```
    """)
    st.stop()

# Initialize session state (only if imports succeeded)
if IMPORTS_SUCCESS:
    if 'execution_active' not in st.session_state:
        st.session_state.execution_active = False
    if 'status_queue' not in st.session_state:
        st.session_state.status_queue = queue.Queue()
    if 'order_info' not in st.session_state:
        st.session_state.order_info = {}
    if 'latest_status' not in st.session_state:
        st.session_state.latest_status = "Ready"
    if 'error_message' not in st.session_state:
        st.session_state.error_message = None
    # Initialize advanced settings in session state
    if 'tick_size' not in st.session_state:
        st.session_state.tick_size = True
    if 'buy_percentage' not in st.session_state:
        st.session_state.buy_percentage = 1.5
    if 'stop_loss_percentage' not in st.session_state:
        st.session_state.stop_loss_percentage = 1.25
    if 'target_percentage' not in st.session_state:
        st.session_state.target_percentage = 2.5
    if 'product' not in st.session_state:
        st.session_state.product = 'I'
    if 'order_type' not in st.session_state:
        st.session_state.order_type = 'LIMIT'


# Only define functions if imports succeeded
if IMPORTS_SUCCESS:
    def get_market_data_feed_authorize_v3(access_token):
        """Get authorization for market data feed."""
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {access_token}'
        }
        url = 'https://api.upstox.com/v3/feed/market-data-feed/authorize'
        api_response = requests.get(url=url, headers=headers, timeout=10)
        return api_response.json()


    def decode_protobuf(buffer):
        """Decode protobuf message."""
        feed_response = pb.FeedResponse()
        feed_response.ParseFromString(buffer)
        return feed_response


    def round_to_tick_size(price, tick_size=0.05):
        """Round price to the nearest tick size."""
        return round(price / tick_size) * tick_size


    def calculate_order_prices(base_buy_price, buy_percentage, stop_loss_percentage, target_percentage, tick_size_enabled):
        """Calculate the actual buy price, stop loss, and target prices."""
        # Calculate buy price with percentage
        calculated_buy_price = base_buy_price + (base_buy_price * buy_percentage / 100)
        if tick_size_enabled:
            calculated_buy_price = round_to_tick_size(calculated_buy_price)
        
        # Calculate stop loss (negative percentage)
        stop_loss_price = calculated_buy_price + (calculated_buy_price * -stop_loss_percentage / 100)
        if tick_size_enabled:
            stop_loss_price = round_to_tick_size(stop_loss_price)
        
        # Calculate target (positive percentage)
        target_price = calculated_buy_price + (calculated_buy_price * target_percentage / 100)
        if tick_size_enabled:
            target_price = round_to_tick_size(target_price)
        
        return calculated_buy_price, stop_loss_price, target_price


    async def execute_gtt_order_async(access_token, instrument_key, buy_price, quantity, status_queue, 
                                      tick_size=True, buy_percentage=1.5, stop_loss_percentage=1.25, 
                                      target_percentage=2.5, product='I', order_type='LIMIT'):
        """Execute GTT order asynchronously."""
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        try:
            # Verify access token first
            status_queue.put({
                'type': 'status',
                'message': '🔐 Verifying access token...',
                'status': 'info'
            })
            
            is_valid, token_msg = verify_access_token(access_token)
            if not is_valid:
                status_queue.put({
                    'type': 'status',
                    'message': f'❌ {token_msg}',
                    'status': 'error'
                })
                return

            status_queue.put({
                'type': 'status',
                'message': '✅ Access token verified',
                'status': 'success'
            })

            # Get market data feed authorization
            status_queue.put({
                'type': 'status',
                'message': '🔌 Connecting to market data feed...',
                'status': 'info'
            })
            
            response = get_market_data_feed_authorize_v3(access_token)
            
            if 'data' not in response or 'authorized_redirect_uri' not in response['data']:
                status_queue.put({
                    'type': 'status',
                    'message': f'❌ Failed to get market data authorization: {response}',
                    'status': 'error'
                })
                return

            # Connect to WebSocket
            async with websockets.connect(
                response["data"]["authorized_redirect_uri"],
                ssl=ssl_context
            ) as websocket:
                status_queue.put({
                    'type': 'status',
                    'message': '✅ WebSocket connected successfully',
                    'status': 'success'
                })

                # Initialize AlgoKM instance with all parameters
                algo = AlgoKM(
                    instrument_key=instrument_key,
                    access_token=access_token,
                    tick_size=tick_size,
                    buy_percentage=buy_percentage,
                    stop_loss_percentage=stop_loss_percentage,
                    target_percentage=target_percentage,
                    product=product,
                    order_type=order_type
                )

                status_queue.put({
                    'type': 'status',
                    'message': f'📊 Initialized trading for {instrument_key}',
                    'status': 'info'
                })

                # Calculate prices
                calc_buy, calc_sl, calc_target = calculate_order_prices(
                    buy_price,
                    buy_percentage,
                    stop_loss_percentage,
                    target_percentage,
                    tick_size
                )
                
                status_queue.put({
                    'type': 'order_info',
                    'data': {
                        'instrument_key': instrument_key,
                        'buy_price': buy_price,
                        'quantity': quantity,
                        'calculated_buy_price': calc_buy,
                        'stop_loss_price': calc_sl,
                        'target_price': calc_target,
                        'buy_percentage': buy_percentage,
                        'stop_loss_percentage': stop_loss_percentage,
                        'target_percentage': target_percentage,
                        'status': 'Initializing...'
                    }
                })

                # Execute normal GTT order
                status_queue.put({
                    'type': 'status',
                    'message': '🚀 Starting GTT order execution...',
                    'status': 'info'
                })

                try:
                    await algo.normal_gtt_execution(
                        websocket=websocket,
                        buy_price=buy_price,
                        quantity=quantity
                    )

                    status_queue.put({
                        'type': 'status',
                        'message': '✅ GTT order execution completed',
                        'status': 'success'
                    })

                    # Get order ID if available
                    if algo.order_id:
                        status_queue.put({
                            'type': 'order_info',
                            'data': {
                                'instrument_key': instrument_key,
                                'buy_price': buy_price,
                                'quantity': quantity,
                                'order_id': algo.order_id,
                                'status': 'Order Placed'
                            }
                        })

                except Exception as e:
                    status_queue.put({
                        'type': 'status',
                        'message': f'❌ Error during execution: {str(e)}',
                        'status': 'error'
                    })
                    import traceback
                    traceback.print_exc()

        except websockets.exceptions.InvalidStatusCode as e:
            status_queue.put({
                'type': 'status',
                'message': f'❌ WebSocket connection failed: {str(e)}',
                'status': 'error'
            })
        except Exception as e:
            status_queue.put({
                'type': 'status',
                'message': f'❌ Unexpected error: {str(e)}',
                'status': 'error'
            })
            import traceback
            traceback.print_exc()


    def run_gtt_execution(access_token, instrument_key, buy_price, quantity, status_queue,
                          tick_size=True, buy_percentage=1.5, stop_loss_percentage=1.25,
                          target_percentage=2.5, product='I', order_type='LIMIT'):
        """Run GTT execution in a separate thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(execute_gtt_order_async(
            access_token, instrument_key, buy_price, quantity, status_queue,
            tick_size, buy_percentage, stop_loss_percentage, target_percentage, product, order_type
        ))


# Main UI
st.title("📈 GTT Order Execution Dashboard")
st.markdown("---")

# Sidebar for configuration
with st.sidebar:
    st.header("⚙️ Order Configuration")
    
    # Access token input
    access_token_input = st.text_input(
        "Access Token",
        value=os.getenv('access_token', ''),
        type="password",
        help="Enter your Upstox access token"
    )
    
    # Use environment variable if input is empty
    access_token = access_token_input if access_token_input else os.getenv('access_token', '')
    
    if access_token:
        # Verify token button
        if st.button("🔐 Verify Token", use_container_width=True):
            is_valid, message = verify_access_token(access_token)
            if is_valid:
                st.success(message)
            else:
                st.error(message)
    
    st.markdown("---")
    
    # Instrument key input
    instrument_key = st.text_input(
        "Instrument Key",
        value="BSE_FO|1150227",
        help="Format: EXCHANGE|INSTRUMENT_TOKEN (e.g., BSE_FO|1150227)"
    )
    
    st.markdown("---")
    
    # Order parameters
    col1, col2 = st.columns(2)
    with col1:
        # Initialize preview_buy_price in session state if not exists
        if 'preview_buy_price' not in st.session_state:
            st.session_state.preview_buy_price = 255.0
        
        buy_price = st.number_input(
            "Buy Price (₹)",
            min_value=0.0,
            value=st.session_state.preview_buy_price,
            step=0.05,
            format="%.2f",
            key='buy_price_input'
        )
        # Update session state with current buy_price value for preview
        if 'buy_price_input' in st.session_state:
            st.session_state.preview_buy_price = st.session_state.buy_price_input
        else:
            st.session_state.preview_buy_price = buy_price
    
    with col2:
        quantity = st.number_input(
            "Quantity",
            min_value=1,
            value=75,
            step=1
        )
    
    st.markdown("---")
    
    # Advanced settings (collapsible)
    with st.expander("⚙️ Advanced Settings"):
        st.session_state.tick_size = st.checkbox(
            "Use Tick Size", 
            value=st.session_state.tick_size,
            help="Enable tick size rounding for prices (default tick size: 0.05)"
        )
        
        st.session_state.buy_percentage = st.number_input(
            "Buy Percentage (%)",
            min_value=0.0,
            max_value=10.0,
            value=st.session_state.buy_percentage,
            step=0.1,
            help="Percentage to add to buy price"
        )
        st.session_state.stop_loss_percentage = st.number_input(
            "Stop Loss Percentage (%)",
            min_value=0.0,
            max_value=10.0,
            value=st.session_state.stop_loss_percentage,
            step=0.1,
            help="Stop loss percentage"
        )
        st.session_state.target_percentage = st.number_input(
            "Target Percentage (%)",
            min_value=0.0,
            max_value=10.0,
            value=st.session_state.target_percentage,
            step=0.1,
            help="Target profit percentage"
        )
        product_options = ['I', 'D', 'M']
        product_index = product_options.index(st.session_state.product) if st.session_state.product in product_options else 0
        st.session_state.product = st.selectbox(
            "Product Type",
            options=product_options,
            index=product_index,
            help="I=Intraday, D=Delivery, M=Margin"
        )
        order_type_options = ['LIMIT', 'MARKET']
        order_type_index = order_type_options.index(st.session_state.order_type) if st.session_state.order_type in order_type_options else 0
        st.session_state.order_type = st.selectbox(
            "Order Type",
            options=order_type_options,
            index=order_type_index
        )
    
    st.markdown("---")
    
    # Execution buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button(
            "🚀 Execute GTT Order",
            disabled=st.session_state.execution_active or not access_token or not instrument_key,
            use_container_width=True,
            type="primary"
        ):
            if not access_token:
                st.error("❌ Please enter access token")
            elif not instrument_key:
                st.error("❌ Please enter instrument key")
            else:
                st.session_state.execution_active = True
                st.session_state.status_queue = queue.Queue()
                st.session_state.order_info = {}
                st.session_state.latest_status = "Executing..."
                st.session_state.error_message = None
                
                # Start execution thread with all parameters from session state
                execution_thread = threading.Thread(
                    target=run_gtt_execution,
                    args=(access_token, instrument_key, buy_price, quantity, st.session_state.status_queue,
                          st.session_state.tick_size, st.session_state.buy_percentage, 
                          st.session_state.stop_loss_percentage, st.session_state.target_percentage, 
                          st.session_state.product, st.session_state.order_type),
                    daemon=True
                )
                execution_thread.start()
                st.success("🚀 GTT order execution started!")
    
    with col2:
        if st.button(
            "⏹️ Stop Execution",
            disabled=not st.session_state.execution_active,
            use_container_width=True
        ):
            st.session_state.execution_active = False
            st.warning("⏹️ Execution stopped by user")

# Initialize status messages list in session state
if 'status_messages' not in st.session_state:
    st.session_state.status_messages = []

# Main content area
# Show price preview before execution
if not st.session_state.execution_active and IMPORTS_SUCCESS:
    # Calculate and show price preview based on sidebar values
    # We need to access sidebar values - they're in the sidebar scope, so we'll use session state
    # Store buy_price in session state when sidebar is rendered
    if 'preview_buy_price' not in st.session_state:
        st.session_state.preview_buy_price = 255.0
    
    # Show price preview
    st.markdown("### 💰 Price Preview")
    
    # Try to get buy_price from session state (updated from sidebar widget)
    # Check if buy_price_input exists in session state (from the widget key)
    if 'buy_price_input' in st.session_state:
        preview_buy_price = st.session_state.buy_price_input
    else:
        preview_buy_price = st.session_state.get('preview_buy_price', 255.0)
    
    if preview_buy_price > 0:
        try:
            calc_buy, calc_sl, calc_target = calculate_order_prices(
                preview_buy_price,
                st.session_state.buy_percentage,
                st.session_state.stop_loss_percentage,
                st.session_state.target_percentage,
                st.session_state.tick_size
            )
            
            # Display calculated prices
            preview_col1, preview_col2, preview_col3 = st.columns(3)
            
            with preview_col1:
                st.metric(
                    "Buy Price (with %)", 
                    f"₹{calc_buy:.2f}",
                    delta=f"+{st.session_state.buy_percentage}%"
                )
                st.caption(f"Base: ₹{preview_buy_price:.2f} + {st.session_state.buy_percentage}%")
            
            with preview_col2:
                st.metric(
                    "Stop Loss", 
                    f"₹{calc_sl:.2f}",
                    delta=f"-{st.session_state.stop_loss_percentage}%",
                    delta_color="inverse"
                )
                st.caption(f"From buy price: -{st.session_state.stop_loss_percentage}%")
            
            with preview_col3:
                st.metric(
                    "Target", 
                    f"₹{calc_target:.2f}",
                    delta=f"+{st.session_state.target_percentage}%"
                )
                st.caption(f"From buy price: +{st.session_state.target_percentage}%")
        except Exception as e:
            st.info("Configure your order parameters in the sidebar to see calculated prices.")
    else:
        st.info("Configure your order parameters in the sidebar to see calculated prices.")
if st.session_state.execution_active:
    # Order information section
    st.markdown("### 📋 Order Information")
    
    # First row: Basic info
    order_col1, order_col2, order_col3, order_col4 = st.columns(4)
    
    with order_col1:
        instrument_display = st.session_state.order_info.get('instrument_key', instrument_key if 'instrument_key' in locals() else 'N/A')
        st.metric("Instrument", instrument_display)
    
    with order_col2:
        qty_display = st.session_state.order_info.get('quantity', quantity if 'quantity' in locals() else 0)
        st.metric("Quantity", qty_display)
    
    with order_col3:
        base_price_display = st.session_state.order_info.get('buy_price', 0) if st.session_state.order_info else 0
        st.metric("Base Price", f"₹{base_price_display:.2f}" if base_price_display > 0 else "₹0.00")
    
    with order_col4:
        status_display = st.session_state.latest_status if st.session_state.latest_status else "Executing..."
        st.metric("Status", status_display)
    
    st.markdown("---")
    
    # Second row: Calculated prices
    st.markdown("#### 💰 Calculated Prices")
    price_col1, price_col2, price_col3 = st.columns(3)
    
    # Get calculated prices from order_info or calculate them
    base_buy_price = st.session_state.order_info.get('buy_price', 0) if st.session_state.order_info else 0
    
    if st.session_state.order_info and 'calculated_buy_price' in st.session_state.order_info:
        calc_buy = st.session_state.order_info['calculated_buy_price']
        calc_sl = st.session_state.order_info['stop_loss_price']
        calc_target = st.session_state.order_info['target_price']
        base_buy_price = st.session_state.order_info.get('buy_price', base_buy_price)
    else:
        # Calculate on the fly using values from session state
        if base_buy_price > 0 and IMPORTS_SUCCESS:
            try:
                calc_buy, calc_sl, calc_target = calculate_order_prices(
                    base_buy_price,
                    st.session_state.buy_percentage,
                    st.session_state.stop_loss_percentage,
                    st.session_state.target_percentage,
                    st.session_state.tick_size
                )
            except NameError:
                # Fallback if calculate_order_prices is not defined
                calc_buy, calc_sl, calc_target = 0.0, 0.0, 0.0
        else:
            calc_buy, calc_sl, calc_target = 0.0, 0.0, 0.0
    
    with price_col1:
        st.metric(
            "Buy Price (with %)", 
            f"₹{calc_buy:.2f}",
            delta=f"+{st.session_state.buy_percentage}%"
        )
        if base_buy_price > 0:
            st.caption(f"Base: ₹{base_buy_price:.2f} + {st.session_state.buy_percentage}%")
    
    with price_col2:
        st.metric(
            "Stop Loss", 
            f"₹{calc_sl:.2f}",
            delta=f"-{st.session_state.stop_loss_percentage}%",
            delta_color="inverse"
        )
        if calc_buy > 0:
            st.caption(f"From buy price: -{st.session_state.stop_loss_percentage}%")
    
    with price_col3:
        st.metric(
            "Target", 
            f"₹{calc_target:.2f}",
            delta=f"+{st.session_state.target_percentage}%"
        )
        if calc_buy > 0:
            st.caption(f"From buy price: +{st.session_state.target_percentage}%")
    
    st.markdown("---")
    
    # Status messages section
    st.markdown("### 📊 Execution Status")
    
    # Process queue messages (non-blocking)
    try:
        while not st.session_state.status_queue.empty():
            data = st.session_state.status_queue.get_nowait()
            
            if data['type'] == 'status':
                st.session_state.status_messages.append({
                    'message': data['message'],
                    'status': data['status'],
                    'timestamp': datetime.now().strftime('%H:%M:%S')
                })
                # Keep only last N messages
                if len(st.session_state.status_messages) > 20:
                    st.session_state.status_messages.pop(0)
                
                st.session_state.latest_status = data['message']
                
                if data['status'] == 'error':
                    st.session_state.error_message = data['message']
            
            elif data['type'] == 'order_info':
                st.session_state.order_info = data['data']
                if 'order_id' in data['data']:
                    st.session_state.latest_status = f"Order ID: {data['data']['order_id']}"
    except queue.Empty:
        pass
    except Exception as e:
        st.error(f"Error processing queue: {str(e)}")
    
    # Display status messages
    if st.session_state.status_messages:
        for msg in reversed(st.session_state.status_messages[-10:]):  # Show last 10 messages
            if msg['status'] == 'success':
                st.success(f"[{msg['timestamp']}] {msg['message']}")
            elif msg['status'] == 'error':
                st.error(f"[{msg['timestamp']}] {msg['message']}")
            elif msg['status'] == 'info':
                st.info(f"[{msg['timestamp']}] {msg['message']}")
            else:
                st.write(f"[{msg['timestamp']}] {msg['message']}")
    else:
        st.info("⏳ Waiting for status updates...")
    
    # Auto-refresh button
    if st.button("🔄 Refresh Status", use_container_width=True):
        st.rerun()

else:
    # Show final status if execution completed
    if st.session_state.order_info:
        st.markdown("### ✅ Execution Summary")
        st.json(st.session_state.order_info)
        
        if st.session_state.error_message:
            st.error(f"❌ Error: {st.session_state.error_message}")
    
    # Welcome message when not executing
    st.info("👈 Configure your order parameters in the sidebar and click **Execute GTT Order** to begin!")
    
    st.markdown("""
    ### 🎯 Features:
    - 📊 Normal GTT order execution
    - 🔐 Access token verification
    - 📈 Real-time execution status updates
    - 💰 Order information display
    - 🔔 Status notifications
    
    ### 📝 Instructions:
    1. Enter your **Access Token** in the sidebar (or use environment variable)
    2. Enter the **Instrument Key** (format: EXCHANGE|INSTRUMENT_TOKEN)
    3. Set **Buy Price** and **Quantity**
    4. (Optional) Configure advanced settings
    5. Click **🚀 Execute GTT Order** to start
    6. Monitor real-time status updates
    7. Click **⏹️ Stop Execution** to stop if needed
    
    ### ⚠️ Important Notes:
    - Make sure your access token is valid and not expired
    - The execution will place a normal order first, then monitor for stop loss/target
    - Portfolio streamer will track order updates in real-time
    - Execution runs asynchronously and won't block the UI
    """)
    
    # Show current configuration if available
    if st.session_state.order_info:
        st.markdown("### 📋 Last Order Information")
        st.json(st.session_state.order_info)

# Footer
st.markdown("---")
st.caption("Built with Streamlit 🎈 | GTT Order Execution | Market data from Upstox")

