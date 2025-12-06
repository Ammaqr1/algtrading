#!/usr/bin/env python3
"""
Upstox Token Refresh Service
A daemon service that automatically refreshes Upstox access tokens every 24 hours.
Run this as a background service to keep your tokens fresh.

Usage:
    python token_refresh_service.py
    
    Or as a systemd service:
    sudo systemctl start upstox-token-refresh
"""

import os
import sys
import time
import logging
from datetime import datetime
from upstox_token_manager import UpstoxTokenManager
import schedule

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('upstox_token_refresh.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def refresh_token_job(manager):
    """Job function to refresh token."""
    try:
        logger.info("=" * 60)
        logger.info("🔄 Starting scheduled token refresh...")
        logger.info("=" * 60)
        
        manager.auto_refresh_token()
        
        logger.info("=" * 60)
        logger.info("✅ Token refresh completed successfully")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ Error during token refresh: {e}")
        import traceback
        logger.error(traceback.format_exc())


def run_service(refresh_time="02:00"):
    """
    Run the token refresh service.
    
    Args:
        refresh_time: Time to refresh token daily (format: "HH:MM")
    """
    logger.info("=" * 60)
    logger.info("🚀 Starting Upstox Token Refresh Service")
    logger.info("=" * 60)
    
    # Initialize token manager
    try:
        env_path = os.path.join(os.path.dirname(__file__), '.env')
        manager = UpstoxTokenManager(env_file_path=env_path)
        
        # Check if we have necessary credentials
        if not manager.client_id or not manager.client_secret:
            logger.error("❌ UPSTOX_CLIENT_ID and UPSTOX_CLIENT_SECRET must be set in .env file")
            sys.exit(1)
        
        if not manager.refresh_token:
            logger.warning("⚠️  No refresh token found. Please initialize tokens first:")
            logger.warning(f"   Run: python upstox_token_manager.py")
            logger.warning(f"   Or visit: {manager.get_authorization_url()}")
            logger.warning("   The service will attempt to refresh on schedule but may fail.")
        
        logger.info(f"✅ Token manager initialized")
        logger.info(f"⏰ Token will be refreshed daily at {refresh_time}")
        logger.info("=" * 60)
        
        # Schedule the refresh job
        schedule.every().day.at(refresh_time).do(refresh_token_job, manager=manager)
        
        # Also refresh immediately if token is close to expiry
        try:
            if manager.token_expiry:
                now = datetime.now()
                time_until_expiry = (manager.token_expiry - now).total_seconds() / 3600
                if time_until_expiry < 2:  # Less than 2 hours until expiry
                    logger.info("⏰ Token expiring soon, refreshing immediately...")
                    refresh_token_job(manager)
        except Exception as e:
            logger.warning(f"Could not check token expiry: {e}")
        
        # Run scheduler loop
        logger.info("🔄 Service running... Press Ctrl+C to stop")
        logger.info("-" * 60)
        
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
            
    except KeyboardInterrupt:
        logger.info("\n" + "=" * 60)
        logger.info("⏹️  Service stopped by user")
        logger.info("=" * 60)
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Upstox Token Refresh Service')
    parser.add_argument(
        '--time',
        type=str,
        default='02:00',
        help='Time to refresh token daily (format: HH:MM, default: 02:00)'
    )
    
    args = parser.parse_args()
    
    # Validate time format
    try:
        datetime.strptime(args.time, '%H:%M')
    except ValueError:
        logger.error(f"❌ Invalid time format: {args.time}. Use HH:MM format (e.g., 02:00)")
        sys.exit(1)
    
    run_service(refresh_time=args.time)




