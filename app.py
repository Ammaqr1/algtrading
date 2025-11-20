"""
Streamlit Frontend for Trading Strategy
Allows users to configure and run the trading strategy with custom time settings.
"""

import streamlit as st
import asyncio
import threading
import sys
from datetime import time as time_class
from trading_strategy import TradingStrategy
import queue

# Page configuration
st.set_page_config(
    page_title="Trading Strategy Dashboard",
    page_icon="📈",
    layout="wide"
)

# Initialize session state
if 'strategy_running' not in st.session_state:
    st.session_state.strategy_running = False
if 'strategy_thread' not in st.session_state:
    st.session_state.strategy_thread = None
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'log_queue' not in st.session_state:
    st.session_state.log_queue = queue.Queue()

# Custom print function to capture logs
class LogCapture:
    def __init__(self, log_queue):
        self.log_queue = log_queue
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
    
    def write(self, text):
        if text.strip():  # Only capture non-empty lines
            self.log_queue.put(text.strip())
        self.original_stdout.write(text)
    
    def flush(self):
        self.original_stdout.flush()

def run_strategy_async(access_token, start_time, end_time, exit_time, quantity, tick_size, log_queue):
    """Run the trading strategy in a separate thread."""
    # Capture stdout to get logs
    log_capture = LogCapture(log_queue)
    sys.stdout = log_capture
    sys.stderr = log_capture
    
    try:
        # Create strategy instance
        strategy = TradingStrategy(
            access_token=access_token,
            quantity=quantity,
            start_time=start_time,
            end_time=end_time,
            exit_time=exit_time,
            tick_size=tick_size
        )
        
        # Run the strategy
        asyncio.run(strategy.execute_strategy())
        
    except Exception as e:
        log_queue.put(f"❌ Error: {str(e)}")
        import traceback
        log_queue.put(traceback.format_exc())
    finally:
        # Restore stdout
        sys.stdout = log_capture.original_stdout
        sys.stderr = log_capture.original_stderr
        st.session_state.strategy_running = False

# Main UI
st.title("📈 Trading Strategy Dashboard")
st.markdown("---")

# Sidebar for configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Access Token input
    st.subheader("🔑 Access Token")
    access_token = st.text_input(
        "Upstox Access Token",
        type="password",
        help="Enter your Upstox API access token",
        placeholder="Enter your access token here"
    )
    
    st.markdown("---")
    
    # Time settings
    st.subheader("⏰ Time Settings")
    
    # Start Time
    start_time_col1, start_time_col2 = st.columns(2)
    with start_time_col1:
        start_hour = st.number_input("Start Hour", min_value=0, max_value=23, value=9, key="start_hour")
    with start_time_col2:
        start_minute = st.number_input("Start Minute", min_value=0, max_value=59, value=17, key="start_minute")
    start_time = time_class(start_hour, start_minute)
    st.caption(f"Start Time: {start_time.strftime('%H:%M')}")
    
    st.markdown("---")
    
    # End Time
    end_time_col1, end_time_col2 = st.columns(2)
    with end_time_col1:
        end_hour = st.number_input("End Hour", min_value=0, max_value=23, value=9, key="end_hour")
    with end_time_col2:
        end_minute = st.number_input("End Minute", min_value=0, max_value=59, value=30, key="end_minute")
    end_time = time_class(end_hour, end_minute)
    st.caption(f"End Time: {end_time.strftime('%H:%M')}")
    
    st.markdown("---")
    
    # Exit Time
    exit_time_col1, exit_time_col2 = st.columns(2)
    with exit_time_col1:
        exit_hour = st.number_input("Exit Hour", min_value=0, max_value=23, value=15, key="exit_hour")
    with exit_time_col2:
        exit_minute = st.number_input("Exit Minute", min_value=0, max_value=59, value=30, key="exit_minute")
    exit_time = time_class(exit_hour, exit_minute)
    st.caption(f"Exit Time: {exit_time.strftime('%H:%M')}")
    
    st.markdown("---")
    
    # Trading Parameters
    st.subheader("📊 Trading Parameters")
    quantity = st.number_input("Quantity", min_value=1, value=1, help="Quantity for option orders")
    tick_size = st.checkbox("Tick Size", value=False, help="Enable tick size for option contracts")
    
    st.markdown("---")
    
    # Control buttons
    col1, col2 = st.columns(2)
    with col1:
        start_button = st.button("🚀 Start Strategy", use_container_width=True, disabled=st.session_state.strategy_running)
    with col2:
        stop_button = st.button("⏹️ Stop Strategy", use_container_width=True, disabled=not st.session_state.strategy_running)

# Handle button clicks
if start_button:
    if not access_token:
        st.error("❌ Please enter your access token!")
    else:
        st.session_state.strategy_running = True
        st.session_state.logs = []
        st.session_state.log_queue = queue.Queue()
        
        # Start strategy in a separate thread
        strategy_thread = threading.Thread(
            target=run_strategy_async,
            args=(access_token, start_time, end_time, exit_time, quantity, tick_size, st.session_state.log_queue),
            daemon=True
        )
        strategy_thread.start()
        st.session_state.strategy_thread = strategy_thread
        
        st.success(f"✅ Strategy started!")
        st.info(f"⏰ Time Settings: Start={start_time.strftime('%H:%M')}, End={end_time.strftime('%H:%M')}, Exit={exit_time.strftime('%H:%M')}")

if stop_button:
    st.session_state.strategy_running = False
    st.warning("⏹️ Strategy stop requested. Please wait for current operations to complete.")

# Main content area
st.markdown("## 📊 Strategy Status")

# Status indicator
status_col1, status_col2 = st.columns([2, 1])
with status_col1:
    if st.session_state.strategy_running:
        st.success("🟢 Strategy is running...")
    else:
        st.info("⚪ Strategy is not running")

with status_col2:
    if access_token:
        st.success("✅ Access Token: Set")
    else:
        st.warning("⚠️ Access Token: Not Set")

# Configuration summary
with st.expander("📋 Current Configuration", expanded=False):
    config_col1, config_col2, config_col3 = st.columns(3)
    with config_col1:
        st.metric("Start Time", f"{start_time.strftime('%H:%M')}")
    with config_col2:
        st.metric("End Time", f"{end_time.strftime('%H:%M')}")
    with config_col3:
        st.metric("Exit Time", f"{exit_time.strftime('%H:%M')}")
    config_params_col1, config_params_col2 = st.columns(2)
    with config_params_col1:
        st.metric("Quantity", quantity)
    with config_params_col2:
        st.metric("Tick Size", "Enabled" if tick_size else "Disabled")

st.markdown("---")

# Logs display
log_col1, log_col2 = st.columns([4, 1])
with log_col1:
    st.markdown("## 📝 Strategy Logs")
with log_col2:
    refresh_logs = st.button("🔄 Refresh Logs", use_container_width=True)

# Check for new logs
new_logs = []
if st.session_state.strategy_running or refresh_logs:
    while not st.session_state.log_queue.empty():
        try:
            log_entry = st.session_state.log_queue.get_nowait()
            new_logs.append(log_entry)
        except queue.Empty:
            break

# Add new logs to session state
if new_logs:
    st.session_state.logs.extend(new_logs)
    # Keep only last 500 logs to prevent memory issues
    if len(st.session_state.logs) > 500:
        st.session_state.logs = st.session_state.logs[-500:]

# Display logs in a scrollable container
if st.session_state.logs:
    # Create a text area for logs (read-only, scrollable)
    log_text = "\n".join(st.session_state.logs[-200:])  # Show last 200 logs
    st.text_area(
        "Live Logs",
        value=log_text,
        height=400,
        disabled=True,
        label_visibility="collapsed"
    )
    st.caption(f"Showing {min(len(st.session_state.logs), 200)} of {len(st.session_state.logs)} logs")
    
    # Clear logs button
    if st.button("🗑️ Clear Logs"):
        st.session_state.logs = []
        st.rerun()
else:
    st.info("📝 Logs will appear here when the strategy starts...")

# Auto-refresh when strategy is running (using Streamlit's built-in mechanism)
if st.session_state.strategy_running and new_logs:
    st.rerun()

# Instructions
with st.expander("📖 Instructions"):
    st.markdown("""
    ### How to use:
    1. **Enter Access Token**: Input your Upstox API access token in the sidebar
    2. **Configure Time Settings**:
       - **Start Time**: When to start capturing Sensex price (default: 9:17)
       - **End Time**: When to stop tracking high prices (default: 9:30)
       - **Exit Time**: When to exit all positions (default: 15:30 / 3:30 PM)
    3. **Set Quantity**: Number of contracts to trade (default: 1)
    4. **Start Strategy**: Click the "Start Strategy" button to begin
    5. **Monitor Logs**: Watch the logs section for real-time updates
    
    ### Strategy Flow:
    - Connects to Upstox websocket at start time
    - Captures Sensex price and gets CE/PE option contracts
    - Tracks highest prices for both options between start and end time
    - Places buy orders at highest price with stop loss and target
    - Monitors orders and handles re-entry logic
    - Exits all positions at exit time
    
    ### Notes:
    - The strategy runs in a separate thread to keep the UI responsive
    - Logs are captured in real-time
    - Click "Stop Strategy" to request a stop (may take a moment)
    """)

# Footer
st.markdown("---")
st.caption("Built with Streamlit 🎈 | Trading Strategy Dashboard")

