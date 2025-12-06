"""
Upstox Token Manager
Automates getting and refreshing Upstox access tokens.
Handles token refresh every 24 hours and updates .env file.
"""

import os
import requests
import json
from datetime import datetime, timedelta
import time
from dotenv import load_dotenv, set_key
import logging
from threading import Thread
import schedule

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class UpstoxTokenManager:
    """
    Manages Upstox access token retrieval and automatic refresh.
    """
    
    def __init__(self, env_file_path='.env'):
        """
        Initialize the token manager.
        
        Args:
            env_file_path: Path to .env file to store tokens
        """
        self.env_file_path = env_file_path
        load_dotenv(env_file_path)
        
        # Upstox OAuth endpoints
        self.token_url = 'https://api.upstox.com/v2/login/authorization/token'
        self.refresh_token_url = 'https://api.upstox.com/v2/login/authorization/token'
        
        # Load credentials from environment
        self.client_id = os.getenv('UPSTOX_CLIENT_ID') or os.getenv('UPSTOX_API_KEY')
        self.client_secret = os.getenv('UPSTOX_CLIENT_SECRET') or os.getenv('UPSTOX_SECRET_KEY')
        self.redirect_uri = os.getenv('UPSTOX_REDIRECT_URI')
        self.refresh_token = os.getenv('UPSTOX_REFRESH_TOKEN')
        self.access_token = os.getenv('access_token')
        
        # Token expiry tracking (defaults to 3:30 AM next day for Upstox)
        self.token_expiry = None
        
    def get_access_token_from_code(self, authorization_code):
        """
        Exchange authorization code for access token and refresh token.
        
        Args:
            authorization_code: Authorization code from Upstox OAuth callback
            
        Returns:
            dict: Contains access_token, refresh_token, and other token info
        """
        if not all([self.client_id, self.client_secret, self.redirect_uri]):
            raise ValueError("Client ID, Client Secret, and Redirect URI must be set in .env file")
        
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        
        data = {
            'code': authorization_code,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': self.redirect_uri,
            'grant_type': 'authorization_code',
        }
        
        try:
            response = requests.post(self.token_url, headers=headers, data=data)
            response.raise_for_status()
            token_data = response.json()
            
            logger.info("✅ Successfully obtained access token from authorization code")
            
            # Save tokens to .env file
            self._save_tokens_to_env(token_data)
            
            return token_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Error getting access token: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            raise
    
    def refresh_access_token(self):
        """
        Refresh access token using refresh token.
        
        Returns:
            str: New access token
        """
        if not self.refresh_token:
            raise ValueError("Refresh token not found. Please obtain one using authorization code first.")
        
        if not all([self.client_id, self.client_secret]):
            raise ValueError("Client ID and Client Secret must be set in .env file")
        
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        
        data = {
            'refresh_token': self.refresh_token,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'refresh_token',
        }
        
        try:
            response = requests.post(self.refresh_token_url, headers=headers, data=data)
            response.raise_for_status()
            token_data = response.json()
            
            logger.info("✅ Successfully refreshed access token")
            
            # Save tokens to .env file
            self._save_tokens_to_env(token_data)
            
            return token_data.get('access_token')
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Error refreshing access token: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            raise
    
    def _save_tokens_to_env(self, token_data):
        """
        Save tokens to .env file.
        
        Args:
            token_data: Dictionary containing token information
        """
        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')
        
        if not access_token:
            logger.error("No access token in response")
            return
        
        # Update access_token in .env
        set_key(self.env_file_path, 'access_token', access_token)
        logger.info(f"✅ Updated access_token in {self.env_file_path}")
        
        # Update refresh_token if provided
        if refresh_token:
            set_key(self.env_file_path, 'UPSTOX_REFRESH_TOKEN', refresh_token)
            self.refresh_token = refresh_token
            logger.info(f"✅ Updated UPSTOX_REFRESH_TOKEN in {self.env_file_path}")
        
        # Reload environment
        load_dotenv(self.env_file_path, override=True)
        self.access_token = access_token
        
        # Calculate expiry (Upstox tokens expire at 3:30 AM next day)
        now = datetime.now()
        tomorrow = now + timedelta(days=1)
        self.token_expiry = tomorrow.replace(hour=3, minute=30, second=0, microsecond=0)
        
        # If it's already past 3:30 AM today, expiry is today at 3:30 AM
        today_330am = now.replace(hour=3, minute=30, second=0, microsecond=0)
        if now > today_330am:
            self.token_expiry = today_330am
        
        logger.info(f"⏰ Token expires at: {self.token_expiry}")
    
    def get_current_token(self):
        """
        Get current access token, refresh if needed.
        
        Returns:
            str: Access token
        """
        # Check if token needs refresh
        if self.token_expiry:
            now = datetime.now()
            # Refresh if less than 1 hour until expiry
            if now >= (self.token_expiry - timedelta(hours=1)):
                logger.info("⏰ Token expiring soon, refreshing...")
                try:
                    return self.refresh_access_token()
                except Exception as e:
                    logger.warning(f"Failed to refresh token: {e}")
        
        return self.access_token
    
    def auto_refresh_token(self):
        """
        Automatically refresh the token (to be called by scheduler).
        """
        try:
            logger.info("🔄 Auto-refreshing token...")
            self.refresh_access_token()
            logger.info("✅ Token auto-refresh completed")
        except Exception as e:
            logger.error(f"❌ Auto-refresh failed: {e}")
            # If refresh fails, you might want to send an alert or notification here
    
    def start_auto_refresh_scheduler(self, refresh_time="02:00"):
        """
        Start a background scheduler to refresh token daily.
        
        Args:
            refresh_time: Time to refresh token daily (format: "HH:MM", default: "02:00")
        """
        logger.info(f"⏰ Setting up daily token refresh at {refresh_time}")
        
        # Schedule token refresh daily
        schedule.every().day.at(refresh_time).do(self.auto_refresh_token)
        
        # Run scheduler in background thread
        def run_scheduler():
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        
        scheduler_thread = Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        logger.info("✅ Auto-refresh scheduler started")
    
    def get_authorization_url(self):
        """
        Get the URL for user to authorize the application.
        
        Returns:
            str: Authorization URL
        """
        if not all([self.client_id, self.redirect_uri]):
            raise ValueError("Client ID and Redirect URI must be set in .env file")
        
        auth_url = (
            f"https://api.upstox.com/v2/login/authorization/dialog"
            f"?response_type=code"
            f"&client_id={self.client_id}"
            f"&redirect_uri={self.redirect_uri}"
        )
        
        return auth_url


def main():
    """
    Example usage of UpstoxTokenManager.
    """
    manager = UpstoxTokenManager()
    
    # Option 1: If you have an authorization code (first time setup)
    # Uncomment and use this:
    # authorization_code = input("Enter authorization code from Upstox: ")
    # manager.get_access_token_from_code(authorization_code)
    
    # Option 2: Refresh existing token
    try:
        if manager.refresh_token:
            print("🔄 Refreshing access token...")
            new_token = manager.refresh_access_token()
            print(f"✅ New access token: {new_token[:20]}...")
        else:
            print("⚠️ No refresh token found. Please get one first using authorization code.")
            print(f"📋 Authorization URL: {manager.get_authorization_url()}")
            print("Visit the URL above, authorize, and copy the 'code' parameter from redirect URL")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Option 3: Start auto-refresh scheduler
    # manager.start_auto_refresh_scheduler(refresh_time="02:00")


if __name__ == "__main__":
    main()




