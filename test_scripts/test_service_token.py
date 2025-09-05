"""
Test script for the get_service_token function.
This script tests the live get_service_token function to ensure it's returning actual data from the app instance.
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

async def test_get_service_token():
    """Test the get_cached_service_token function directly"""
    try:
        # Import the function and required variables from the correct modules
        from main import OWUI, JWT
        from auth import get_cached_service_token
        
        print("=" * 60)
        print("TESTING get_cached_service_token() FUNCTION")
        print("=" * 60)
        
        # Check environment setup
        print(f"GIA_URL (OWUI): {OWUI}")
        print(f"JWT available: {'Yes' if JWT else 'No'}")
        print(f"JWT preview: {JWT[:20] + '...' if JWT and len(JWT) > 20 else 'Not available'}")
        print()
        
        if not JWT:
            print("❌ ERROR: OWUI_JWT environment variable is not set!")
            return False
        
        # Initialize the HTTP client (mimicking the startup event)
        print("🔄 Initializing HTTP client...")
        client = httpx.AsyncClient(
            base_url=OWUI,
            headers={"Accept": "application/json"},
            timeout=httpx.Timeout(connect=5, read=30, write=30, pool=30),
            limits=httpx.Limits(max_keepalive_connections=32, max_connections=128),
            http2=True,
        )
        print("✅ HTTP client initialized")
        
        print()
        print("🔄 Testing get_cached_service_token()...")
        
        # Call the function with proper parameters
        service_token = await get_cached_service_token(client, JWT)
        
        if service_token:
            print("✅ SUCCESS: Service token obtained!")
            print(f"Token type: {type(service_token)}")
            print(f"Token length: {len(service_token) if isinstance(service_token, str) else 'N/A'}")
            print(f"Token preview: {service_token[:20] + '...' if isinstance(service_token, str) and len(service_token) > 20 else service_token}")
            
            # Check if service token is the same as JWT (direct usage)
            if service_token == JWT:
                print("ℹ️  Service token is identical to JWT (direct usage mode)")
            else:
                print("ℹ️  Service token is different from JWT (token exchange mode)")
            
            # Validate token format (should be a non-empty string)
            if isinstance(service_token, str) and len(service_token) > 0:
                print("✅ Token format validation: PASSED")
                return True
            else:
                print("❌ Token format validation: FAILED - Token should be a non-empty string")
                return False
        else:
            print("❌ FAILED: No service token obtained")
            return False
            
    except Exception as e:
        print(f"❌ ERROR during testing: {str(e)}")
        print(f"Exception type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Clean up the client if we created it
        if 'client' in locals() and client:
            await client.aclose()
            print("🧹 HTTP client closed")


async def test_service_token_with_api_call():
    """Test using the service token to make an actual API call"""
    try:
        from main import OWUI, JWT
        from auth import get_cached_service_token
        
        print("\n" + "=" * 60)
        print("TESTING SERVICE TOKEN WITH API CALL")
        print("=" * 60)
        
        # Initialize client
        client = httpx.AsyncClient(
            base_url=OWUI,
            headers={"Accept": "application/json"},
            timeout=httpx.Timeout(connect=5, read=30, write=30, pool=30),
            limits=httpx.Limits(max_keepalive_connections=32, max_connections=128),
            http2=True,
        )
        
        # Get service token
        print("🔄 Getting service token...")
        service_token = await get_cached_service_token(client, JWT)
        
        if not service_token:
            print("❌ Could not obtain service token for API test")
            return False
        
        print("✅ Service token obtained for API test")
        
        # Test the token by making an API call to /api/models
        print("🔄 Testing service token with /api/models endpoint...")
        
        try:
            headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {service_token}"
            }
            
            response = await client.get("/api/models", headers=headers)
            
            print(f"API Response Status: {response.status_code}")
            
            if response.status_code == 200:
                print("✅ SUCCESS: Service token works with API!")
                
                # Try to parse the response
                try:
                    data = response.json()
                    print(f"Response type: {type(data)}")
                    if isinstance(data, list):
                        print(f"Number of models: {len(data)}")
                        if data:
                            print(f"First model preview: {data[0] if len(str(data[0])) < 100 else str(data[0])[:100] + '...'}")
                    elif isinstance(data, dict):
                        print(f"Response keys: {list(data.keys())}")
                    else:
                        print(f"Response preview: {str(data)[:200]}...")
                except Exception as parse_error:
                    print(f"⚠️  Could not parse JSON response: {parse_error}")
                    print(f"Raw response (first 200 chars): {response.text[:200]}...")
                
                return True
            else:
                print(f"❌ API call failed with status {response.status_code}")
                print(f"Response: {response.text[:200]}...")
                return False
                
        except httpx.HTTPError as api_error:
            print(f"❌ HTTP error during API call: {api_error}")
            return False
            
    except Exception as e:
        print(f"❌ ERROR during API testing: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        if 'client' in locals() and client:
            await client.aclose()


async def test_auth_endpoints_directly():
    """Test authentication endpoints directly to diagnose the 401 issue"""
    try:
        from main import OWUI, JWT
        
        print("\n" + "=" * 60)
        print("TESTING AUTH ENDPOINTS DIRECTLY")
        print("=" * 60)
        
        # Initialize client
        client = httpx.AsyncClient(
            base_url=OWUI,
            headers={"Accept": "application/json"},
            timeout=httpx.Timeout(connect=5, read=30, write=30, pool=30),
            limits=httpx.Limits(max_keepalive_connections=32, max_connections=128),
            http2=True,
        )
        
        # Test 1: Try /api/v1/auths/api_key endpoint directly
        print("🔄 Testing /api/v1/auths/api_key endpoint directly...")
        try:
            response = await client.get(
                "/api/v1/auths/api_key",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {JWT}"
                }
            )
            print(f"✅ /api/v1/auths/api_key Status: {response.status_code}")
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
                except:
                    print(f"Response (first 100 chars): {response.text[:100]}...")
            else:
                print(f"❌ Response: {response.text[:200]}...")
        except Exception as e:
            print(f"❌ Error with /api/v1/auths/api_key: {e}")
        
        print()
        
        # Test 2: Try /api/v1/auths/ endpoint directly  
        print("🔄 Testing /api/v1/auths/ endpoint directly...")
        try:
            response = await client.get(
                "/api/v1/auths/",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {JWT}"
                }
            )
            print(f"✅ /api/v1/auths/ Status: {response.status_code}")
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
                    if isinstance(data, dict) and 'email' in data:
                        print(f"Email found: {data.get('email')}")
                except:
                    print(f"Response (first 100 chars): {response.text[:100]}...")
            else:
                print(f"❌ Response: {response.text[:200]}...")
        except Exception as e:
            print(f"❌ Error with /api/v1/auths/: {e}")
            
        print()
        
        # Test 3: Try /api/models endpoint with JWT directly
        print("🔄 Testing /api/models endpoint with JWT directly...")
        try:
            response = await client.get(
                "/api/models",
                headers={
                    "Accept": "application/json", 
                    "Authorization": f"Bearer {JWT}"
                }
            )
            print(f"/api/models with JWT Status: {response.status_code}")
            if response.status_code == 200:
                try:
                    data = response.json()
                    if isinstance(data, list):
                        print(f"✅ Models found: {len(data)} models")
                        return True
                    else:
                        print(f"Models response type: {type(data)}")
                except:
                    print(f"Response (first 100 chars): {response.text[:100]}...")
            else:
                print(f"❌ Response: {response.text[:200]}...")
        except Exception as e:
            print(f"❌ Error with /api/models: {e}")
            
        return False
        
    except Exception as e:
        print(f"❌ ERROR during endpoint testing: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        if 'client' in locals() and client:
            await client.aclose()


async def main():
    """Main test function"""
    print("🚀 Starting Service Token Test Suite")
    print(f"Timestamp: {asyncio.get_event_loop().time()}")
    print()
    
    # Test 0: Direct endpoint testing to diagnose auth issues
    test0_result = await test_auth_endpoints_directly()
    
    # Test 1: Basic service token functionality
    test1_result = await test_get_service_token()
    
    # Test 2: Service token with actual API call
    test2_result = await test_service_token_with_api_call()
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Test 0 (direct endpoints): {'✅ PASSED' if test0_result else '❌ FAILED'}")
    print(f"Test 1 (get_cached_service_token): {'✅ PASSED' if test1_result else '❌ FAILED'}")
    print(f"Test 2 (API call with token): {'✅ PASSED' if test2_result else '❌ FAILED'}")
    
    overall_result = test1_result and test2_result
    print(f"\nOverall Result: {'✅ ALL TESTS PASSED' if overall_result else '❌ SOME TESTS FAILED'}")
    
    if test0_result and not (test1_result and test2_result):
        print("\n💡 NOTE: Direct JWT authentication works, but token exchange may have issues.")
        print("   Consider updating the system to use JWT directly if appropriate.")
    
    return overall_result


if __name__ == "__main__":
    # Run the async main function
    result = asyncio.run(main())
    
    # Exit with appropriate code
    sys.exit(0 if result else 1)
