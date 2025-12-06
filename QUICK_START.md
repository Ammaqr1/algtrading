# Quick Start: Upstox Token Automation

## 1. Install Dependencies

```bash
pip install -r requirements.txt
```

## 2. Add Credentials to .env

Add these to your `.env` file:

```env
UPSTOX_CLIENT_ID=your_client_id
UPSTOX_CLIENT_SECRET=your_client_secret
UPSTOX_REDIRECT_URI=http://localhost:3000/callback
```

## 3. Initialize Tokens (First Time Only)

```bash
python init_tokens.py
```

Follow the prompts to authorize and get your tokens.

## 4. Start Token Refresh Service

```bash
# Run in background
nohup python token_refresh_service.py > token_service.log 2>&1 &

# Or run in terminal (Ctrl+C to stop)
python token_refresh_service.py
```

That's it! Your tokens will refresh automatically every 24 hours at 2:00 AM.

## Your Existing Code

Your existing code doesn't need any changes! It reads `access_token` from `.env`, which gets automatically updated by the service.

## Manual Refresh

If you need to refresh manually:

```bash
python -c "from upstox_token_manager import UpstoxTokenManager; UpstoxTokenManager().refresh_access_token()"
```

## Custom Refresh Time

To change the refresh time (default: 02:00):

```bash
python token_refresh_service.py --time 03:00
```

See `TOKEN_SETUP_GUIDE.md` for detailed instructions.




