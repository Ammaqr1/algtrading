# Upstox Token Automation Setup Guide

This guide will help you set up automatic token refresh for your Upstox API access tokens.

## Overview

The token management system automatically refreshes your Upstox access token every 24 hours. Upstox tokens expire at 3:30 AM the following day, so the service refreshes them at 2:00 AM daily (configurable).

## Prerequisites

1. **Upstox Developer Account**: You need API credentials from Upstox
   - Go to: https://upstox.com/developer/dashboard
   - Create an app and get your `Client ID` and `Client Secret`
   - Set a redirect URI (e.g., `http://localhost:3000/callback`)

2. **Python Environment**: Make sure you have Python 3.7+ installed

## Installation

1. Install required packages:
```bash
pip install -r requirements.txt
```

## Initial Setup

### Step 1: Configure Environment Variables

Add the following to your `.env` file in the `algtrading` directory:

```env
# Upstox API Credentials
UPSTOX_CLIENT_ID=your_client_id_here
UPSTOX_CLIENT_SECRET=your_client_secret_here
UPSTOX_REDIRECT_URI=http://localhost:3000/callback

# These will be automatically populated after first authorization
access_token=
UPSTOX_REFRESH_TOKEN=
```

### Step 2: Get Authorization Code (First Time Only)

1. **Option A: Use the helper function**

Run this Python code to get the authorization URL:

```python
from upstox_token_manager import UpstoxTokenManager

manager = UpstoxTokenManager()
auth_url = manager.get_authorization_url()
print(f"Visit this URL: {auth_url}")
```

2. **Option B: Manual URL construction**

Visit this URL in your browser (replace placeholders):
```
https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id=YOUR_CLIENT_ID&redirect_uri=YOUR_REDIRECT_URI
```

3. **Authorize and Get Code**
   - Log in to Upstox
   - Authorize the application
   - You'll be redirected to your redirect URI with a `code` parameter
   - Copy the `code` value from the URL (e.g., `http://localhost:3000/callback?code=ABC123...`)

### Step 3: Exchange Code for Tokens

Run the token manager to exchange the authorization code:

```python
from upstox_token_manager import UpstoxTokenManager

manager = UpstoxTokenManager()
authorization_code = input("Enter authorization code: ")
manager.get_access_token_from_code(authorization_code)
```

Or create a simple script `init_tokens.py`:

```python
from upstox_token_manager import UpstoxTokenManager

manager = UpstoxTokenManager()

# Get authorization URL
print("Step 1: Visit this URL to authorize:")
print(manager.get_authorization_url())
print("\nStep 2: After authorization, you'll be redirected.")
print("Copy the 'code' parameter from the redirect URL.")
print()

# Get code from user
code = input("Enter the authorization code: ")

# Exchange for tokens
try:
    manager.get_access_token_from_code(code)
    print("\n✅ Tokens saved successfully!")
    print(f"✅ Access Token: {manager.access_token[:20]}...")
    if manager.refresh_token:
        print(f"✅ Refresh Token saved")
except Exception as e:
    print(f"❌ Error: {e}")
```

## Running the Token Refresh Service

### Option 1: Run as Python Script (Background)

```bash
# Run in background
nohup python token_refresh_service.py > token_service.log 2>&1 &

# Or with custom refresh time (default: 02:00 AM)
python token_refresh_service.py --time 02:00
```

### Option 2: Run as Systemd Service (Linux)

1. Create a systemd service file `/etc/systemd/system/upstox-token-refresh.service`:

```ini
[Unit]
Description=Upstox Token Refresh Service
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/home/ammar/Documents/algo/algtrading
ExecStart=/usr/bin/python3 /home/ammar/Documents/algo/algtrading/token_refresh_service.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

2. Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable upstox-token-refresh
sudo systemctl start upstox-token-refresh
sudo systemctl status upstox-token-refresh
```

3. View logs:
```bash
sudo journalctl -u upstox-token-refresh -f
```

### Option 3: Use Cron (Linux/Mac)

Add to crontab (`crontab -e`):

```cron
# Refresh token daily at 2:00 AM
0 2 * * * cd /home/ammar/Documents/algo/algtrading && /usr/bin/python3 token_refresh_service.py --time 02:00
```

### Option 4: Task Scheduler (Windows)

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger to "Daily" at 2:00 AM
4. Action: Start a program
5. Program: `python.exe`
6. Arguments: `C:\path\to\algtrading\token_refresh_service.py`

## Integration with Existing Code

Your existing code already reads `access_token` from the `.env` file. The token manager automatically updates this file, so your code will automatically use the refreshed token.

Example usage in your code:

```python
from dotenv import load_dotenv
import os
from upstox_token_manager import UpstoxTokenManager

# Load environment
load_dotenv()

# Get current token (automatically refreshed if needed)
manager = UpstoxTokenManager()
access_token = manager.get_current_token()

# Use the token in your trading strategy
# Your existing code will work as-is since it reads from .env
```

## Manual Token Refresh

You can manually refresh the token anytime:

```python
from upstox_token_manager import UpstoxTokenManager

manager = UpstoxTokenManager()
new_token = manager.refresh_access_token()
print(f"New token: {new_token}")
```

Or run:
```bash
python -c "from upstox_token_manager import UpstoxTokenManager; UpstoxTokenManager().refresh_access_token()"
```

## Troubleshooting

### Error: "Refresh token not found"
- Make sure you completed the initial setup and have a `UPSTOX_REFRESH_TOKEN` in your `.env` file
- Re-run the initialization process

### Error: "Client ID/Secret not found"
- Check that `UPSTOX_CLIENT_ID` and `UPSTOX_CLIENT_SECRET` are set in `.env`

### Token refresh fails
- Check your internet connection
- Verify your Upstox credentials are still valid
- Check logs: `upstox_token_refresh.log`

### Service not running
- Check if the service/process is running
- Check logs for errors
- Verify Python path and file paths are correct

## Security Notes

1. **Never commit `.env` file** - Add it to `.gitignore`
2. **Protect your credentials** - Store them securely
3. **Use environment variables** in production instead of `.env` file
4. **Rotate credentials** if they're compromised

## Token Expiry Details

- Upstox access tokens expire at **3:30 AM the following day** (regardless of when generated)
- The service refreshes tokens at **2:00 AM** daily (before expiry)
- You can customize the refresh time using `--time` parameter

## Support

For issues:
1. Check the logs: `upstox_token_refresh.log`
2. Verify your Upstox API credentials
3. Check Upstox API status and documentation




