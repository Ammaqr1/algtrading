#!/usr/bin/env python3
"""
Simple script to initialize Upstox tokens for the first time.
Run this once to get your initial access token and refresh token.
"""

from upstox_token_manager import UpstoxTokenManager

def main():
    print("=" * 60)
    print("🔐 Upstox Token Initialization")
    print("=" * 60)
    print()
    
    try:
        manager = UpstoxTokenManager()
        
        # Check if credentials are set
        if not manager.client_id or not manager.client_secret:
            print("❌ Error: UPSTOX_CLIENT_ID and UPSTOX_CLIENT_SECRET must be set in .env file")
            print()
            print("Please add these to your .env file:")
            print("  UPSTOX_CLIENT_ID=your_client_id")
            print("  UPSTOX_CLIENT_SECRET=your_client_secret")
            print("  UPSTOX_REDIRECT_URI=your_redirect_uri")
            return
        
        if not manager.redirect_uri:
            print("❌ Error: UPSTOX_REDIRECT_URI must be set in .env file")
            return
        
        # Check if we already have tokens
        if manager.access_token and manager.refresh_token:
            print("✅ Tokens already exist!")
            print(f"   Access Token: {manager.access_token[:20]}...")
            print()
            response = input("Do you want to refresh them? (y/n): ")
            if response.lower() != 'y':
                print("Cancelled.")
                return
            
            try:
                new_token = manager.refresh_access_token()
                print(f"\n✅ Token refreshed successfully!")
                print(f"   New Access Token: {new_token[:20]}...")
                return
            except Exception as e:
                print(f"\n❌ Error refreshing token: {e}")
                print("You may need to re-initialize with a new authorization code.")
                return
        
        # Get authorization URL
        print("Step 1: Get Authorization Code")
        print("-" * 60)
        auth_url = manager.get_authorization_url()
        print(f"Visit this URL in your browser:")
        print(f"\n{auth_url}\n")
        print("After logging in and authorizing, you'll be redirected.")
        print("Copy the 'code' parameter from the redirect URL.")
        print()
        print("Example redirect URL:")
        print("  http://localhost:3000/callback?code=ABC123XYZ...")
        print()
        
        # Get code from user
        code = input("Enter the authorization code: ").strip()
        
        if not code:
            print("❌ No code provided. Exiting.")
            return
        
        print()
        print("Step 2: Exchanging code for tokens...")
        print("-" * 60)
        
        # Exchange code for tokens
        try:
            token_data = manager.get_access_token_from_code(code)
            
            print()
            print("=" * 60)
            print("✅ SUCCESS! Tokens initialized and saved to .env file")
            print("=" * 60)
            print(f"Access Token: {manager.access_token[:30]}...")
            if manager.refresh_token:
                print(f"Refresh Token: {manager.refresh_token[:30]}...")
            print()
            print("✅ Your tokens are now set up!")
            print("✅ You can now run the token refresh service:")
            print("   python token_refresh_service.py")
            print()
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()




