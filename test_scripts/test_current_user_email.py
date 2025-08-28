"""
Test script for the get_current_user_email function.
This script tests the live get_current_user_email function to identify and fix issues.
"""
import sys
import os
import asyncio
import httpx
from dotenv import load_dotenv

# Add the parent directory to the path so we can import from main
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load environment variables
load_dotenv()

async def test_get_current_user_email():
    """Test the get_current_user_email function directly"""
    try:
        # Import the function and required variables
        from main import get_current_user_email, get_service_token, OWUI, JWT
        
        print("=" * 60)
        print("TESTING get_current_user_email() FUNCTION")
        print("=" * 60)
        
        # Check environment setup
        print(f"GIA_URL (OWUI): {OWUI}")
        print(f"JWT available: {'Yes' if JWT else 'No'}")
        print()
        
        if not JWT:
            print("❌ ERROR: OWUI_JWT environment variable is not set!")
            return False
        
        # Initialize the HTTP client (mimicking the startup event)
        print("🔄 Initializing HTTP client...")
        import main
        main.client = httpx.AsyncClient(
            base_url=OWUI,
            headers={"Authorization": f"Bearer {JWT}"},
            timeout=60,
        )
        print("✅ HTTP client initialized")
        
        print()
        print("🔄 First, getting service token...")
        
        # Get service token first
        service_token = await get_service_token()
        
        if service_token:
            print("✅ Service token obtained")
            print(f"Service token preview: {service_token[:20] + '...' if len(service_token) > 20 else service_token}")
            
            print()
            print("🔄 Testing get_current_user_email() with service token...")
            
            # Test with service token
            try:
                email = await get_current_user_email(service_token)
                print(f"✅ SUCCESS: Email obtained with service token: {email}")
            except Exception as e:
                print(f"❌ FAILED with service token: {e}")
                print(f"Exception type: {type(e).__name__}")
                import traceback
                traceback.print_exc()
            
            print()
            print("🔄 Testing get_current_user_email() with JWT...")
            
            # Test with JWT
            try:
                email = await get_current_user_email(JWT)
                print(f"✅ SUCCESS: Email obtained with JWT: {email}")
                return True
            except Exception as e:
                print(f"❌ FAILED with JWT: {e}")
                print(f"Exception type: {type(e).__name__}")
                import traceback
                traceback.print_exc()
                return False
        else:
            print("❌ Could not obtain service token")
            return False
            
    except Exception as e:
        print(f"❌ ERROR during testing: {str(e)}")
        print(f"Exception type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Clean up the client if we created it
        import main
        if hasattr(main, 'client') and main.client:
            await main.client.aclose()
            print("🧹 HTTP client closed")


if __name__ == "__main__":
    # Run the async main function
    result = asyncio.run(test_get_current_user_email())
    
    # Exit with appropriate code
    sys.exit(0 if result else 1)
