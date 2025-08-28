"""
Simple test script for the get_service_token function.
This is a basic test to verify the service token functionality.
"""
import sys
import os
import asyncio
import httpx
from dotenv import load_dotenv

# Add the parent directory to the path so we can import from main
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

load_dotenv()

async def test_service_token():
    """Simple test for get_service_token function"""
    from main import OWUI, JWT
    
    print("Testing get_service_token()...")
    print(f"GIA URL: {OWUI}")
    print(f"JWT available: {'Yes' if JWT else 'No'}")
    
    if not JWT:
        print("ERROR: OWUI_JWT environment variable is required!")
        return
    
    # Initialize HTTP client
    client = httpx.AsyncClient(
        base_url=OWUI,
        headers={"Authorization": f"Bearer {JWT}"},
        timeout=60,
    )
    
    try:
        # Import and test the function
        from main import get_service_token
        
        # Set the global client (since the function expects it)
        import main
        main.client = client
        
        # Call the function
        service_token = await get_service_token()
        
        if service_token:
            print(f"✅ Success! Service token obtained")
            print(f"Token length: {len(service_token)}")
            print(f"Token preview: {service_token[:30]}...")
            
            # Test the token with a simple API call
            headers = {"Accept": "application/json", "Authorization": f"Bearer {service_token}"}
            response = await client.get("/api/models", headers=headers)
            
            print(f"API test status: {response.status_code}")
            if response.status_code == 200:
                print("✅ Service token works with API!")
                print(f"Response data: {response.json()}")
            else:
                print(f"⚠️  API call returned: {response.status_code}")
                
        else:
            print("❌ Failed to obtain service token")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(test_service_token())
