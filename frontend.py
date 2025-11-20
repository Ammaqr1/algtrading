import streamlit as st
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
import threading
import queue

# Load environment variables
load_dotenv()
my_access_token = os.getenv('access_token')

# Page configuration
st.set_page_config(
    page_title="Upstock Trading Dashboard",
    page_icon="📈",
    layout="wide"
)

# Initialize session state
if 'trading_active' not in st.session_state:
    st.session_state.trading_active = False
if 'price_queue' not in st.session_state:
    st.session_state.price_queue = queue.Queue()
if 'latest_data' not in st.session_state:
    st.session_state.latest_data = None


def get_market_data_feed_authorize_v3():
    """Get authorization for market data feed."""
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {my_access_token}'
    }
    url = 'https://api.upstox.com/v3/feed/market-data-feed/authorize'
    api_response = requests.get(url=url, headers=headers)
    return api_response.json()


def decode_protobuf(buffer):
    """Decode protobuf message."""
    feed_response = pb.FeedResponse()
    feed_response.ParseFromString(buffer)
    return feed_response


async def fetch_market_data_async(start_hour, start_minute, end_hour, end_minute, instrument_key, price_queue):
    """Fetch market data and put it in queue."""
    # Create default SSL context
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    try:
        # Get market data feed authorization
        response = get_market_data_feed_authorize_v3()
        
        # Connect to the WebSocket with SSL context
        async with websockets.connect(response["data"]["authorized_redirect_uri"], ssl=ssl_context) as websocket:
            price_queue.put({
                'type': 'status',
                'message': '✅ Connection established',
                'status': 'success'
            })

            # Data to be sent over the WebSocket
            data = {
                "guid": "someguid",
                "method": "sub",
                "data": {
                    "mode": "ltpc",
                    "instrumentKeys": [instrument_key]
                }
            }

            # Convert data to binary and send over WebSocket
            binary_data = json.dumps(data).encode('utf-8')
            await websocket.send(binary_data)

            kamal = AlogKM(access_token=my_access_token, instrument_key=instrument_key)

            # Track the high price
            tracked_high = 0
            ist = pytz.timezone("Asia/Kolkata")

            # Continuously receive and decode data from WebSocket
            i = 0
            while st.session_state.trading_active:
                i += 1
                message = await websocket.recv()
                decoded_data = decode_protobuf(message)

                # Get current IST time
                now = datetime.now(ist).time()

                # Define start and end times
                start = time(start_hour, start_minute)
                end = time(end_hour, end_minute)
                exit_time = time(15, 30)  # 3:30 PM

                # Convert the decoded data to a dictionary
                data_dict = MessageToDict(decoded_data)

                # Extract LTP and put in queue
                result = kamal.extract_l1_ohlc(data_dict)
                if result:
                    cp, ltp, ltt = result.values()
                    
                    # Check if we're in the trading window
                    in_window = start <= now <= end
                    if in_window:
                        tracked_high = kamal.highMarketValue(tracked_high, ltp)
                    
                    # Put data in queue for frontend
                    price_queue.put({
                        'type': 'price',
                        'ltp': ltp,
                        'cp': cp,
                        'ltt': ltt,
                        'time': now.strftime('%H:%M:%S'),
                        'iteration': i,
                        'tracked_high': tracked_high,
                        'in_window': in_window
                    })
                else:
                    st.warning("⚠️ Received invalid data")

                # Check exit time
                if now >= exit_time:
                    price_queue.put({
                        'type': 'status',
                        'message': f'⏰ Market closed at {exit_time.strftime("%H:%M")}',
                        'status': 'warning'
                    })
                    break

                await asyncio.sleep(0.1)

    except Exception as e:
        price_queue.put({
            'type': 'status',
            'message': f'❌ Error: {str(e)}',
            'status': 'error'
        })
        st.session_state.trading_active = False


def run_trading_loop(start_hour, start_minute, end_hour, end_minute, instrument_key, price_queue):
    """Run the trading loop in a separate thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(fetch_market_data_async(
        start_hour, start_minute, end_hour, end_minute, instrument_key, price_queue
    ))


# Main UI
st.title("📈 Upstock Trading Dashboard")
st.markdown("---")

# Sidebar for controls
with st.sidebar:
    st.header("⚙️ Trading Configuration")
    
    # Time inputs
    col1, col2 = st.columns(2)
    with col1:
        start_hour = st.number_input("Start Hour", min_value=0, max_value=23, value=9)
        start_minute = st.number_input("Start Minute", min_value=0, max_value=59, value=17)
    
    with col2:
        end_hour = st.number_input("End Hour", min_value=0, max_value=23, value=9)
        end_minute = st.number_input("End Minute", min_value=0, max_value=59, value=30)
    
    st.markdown("---")
    
    # Instrument key input
    instrument_key = st.text_input("Instrument Key", value="BSE_FO|874098")
    
    st.markdown("---")
    
    # Start/Stop buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 Start Trading", disabled=st.session_state.trading_active, use_container_width=True):
            st.session_state.trading_active = True
            st.session_state.price_queue = queue.Queue()
            
            # Start trading thread
            trading_thread = threading.Thread(
                target=run_trading_loop,
                args=(start_hour, start_minute, end_hour, end_minute, instrument_key, st.session_state.price_queue),
                daemon=True
            )
            trading_thread.start()
            st.success(f"Trading started! Window: {start_hour:02d}:{start_minute:02d} - {end_hour:02d}:{end_minute:02d}")
    
    with col2:
        if st.button("⏹️ Stop Trading", disabled=not st.session_state.trading_active, use_container_width=True):
            st.session_state.trading_active = False
            st.warning("Trading stopped by user")

# Main content area
if st.session_state.trading_active:
    # Create placeholders for real-time updates
    status_placeholder = st.empty()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        ltp_placeholder = st.empty()
    with col2:
        cp_placeholder = st.empty()
    with col3:
        high_placeholder = st.empty()
    with col4:
        time_placeholder = st.empty()
    
    st.markdown("---")
    
    # Data table placeholder
    data_placeholder = st.empty()
    
    # Continuously check queue for updates
    while st.session_state.trading_active:
        try:
            # Get data from queue (non-blocking)
            if not st.session_state.price_queue.empty():
                data = st.session_state.price_queue.get_nowait()
                
                if data['type'] == 'status':
                    status_placeholder.info(data['message'])
                    if data.get('status') in ['warning', 'error']:
                        st.session_state.trading_active = False
                        break
                
                elif data['type'] == 'price':
                    st.session_state.latest_data = data
                    
                    # Update metrics
                    ltp_placeholder.metric(
                        label="💰 Last Traded Price (LTP)",
                        value=f"₹{data['ltp']:.2f}",
                        delta=f"{data['ltp'] - data['cp']:.2f}"
                    )
                    
                    cp_placeholder.metric(
                        label="📊 Current Price (CP)",
                        value=f"₹{data['cp']:.2f}"
                    )
                    
                    high_placeholder.metric(
                        label="📈 Tracked High",
                        value=f"₹{data['tracked_high']:.2f}" if data['tracked_high'] > 0 else "N/A"
                    )
                    
                    time_placeholder.metric(
                        label="🕐 Time",
                        value=data['time']
                    )
                    
                    # Show trading window status
                    if data['in_window']:
                        status_placeholder.success(f"🟢 In trading window | Iteration: {data['iteration']}")
                    else:
                        status_placeholder.info(f"⏳ Outside trading window | Iteration: {data['iteration']}")
                    
                    # Show detailed data
                    with data_placeholder.container():
                        st.subheader("📋 Latest Market Data")
                        st.json({
                            "Last Traded Price": f"₹{data['ltp']}",
                            "Current Price": f"₹{data['cp']}",
                            "Last Traded Time": data['ltt'],
                            "Tracked High": f"₹{data['tracked_high']}",
                            "Current Time": data['time'],
                            "Iteration": data['iteration'],
                            "In Trading Window": "Yes" if data['in_window'] else "No"
                        })
            
            # Small delay to prevent blocking UI
            import time
            time.sleep(0.1)
            
        except queue.Empty:
            pass
        except Exception as e:
            st.error(f"Error updating UI: {str(e)}")
            break
    
else:
    # Show welcome message when not trading
    st.info("👈 Configure your trading parameters in the sidebar and click **Start Trading** to begin!")
    
    st.markdown("""
    ### 🎯 Features:
    - 📊 Real-time price updates
    - ⏰ Custom trading window (start & end time)
    - 📈 Track highest price during trading window
    - 💰 Live LTP (Last Traded Price) display
    - 🔔 Market status notifications
    
    ### 📝 Instructions:
    1. Set your **Start Time** and **End Time** in the sidebar
    2. Enter the **Instrument Key** (default: BSE_FO|874098)
    3. Click **🚀 Start Trading** to begin monitoring
    4. Click **⏹️ Stop Trading** to stop
    """)

# Footer
st.markdown("---")
st.caption("Built with Streamlit 🎈 | Market data from Upstox")
