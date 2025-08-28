#!/usr/bin/env python3
"""
Live test script for Vantagepoint Authentication
Tests the actual authentication endpoint with real credentials
"""

import sys
import os
from datetime import datetime
import json

# Add the parent directory to the path so we can import from auth module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth.vp_auth import get_vantagepoint_token
import httpx

def test_vp_authentication():
    """
    Test the Vantagepoint authentication with live data
    """
    print("=" * 60)
    print("VANTAGEPOINT AUTHENTICATION LIVE TEST")
    print("=" * 60)
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Check if required environment variables are set
    required_env_vars = [
        "VP_BASE_URL",
        "VP_USERNAME", 
        "VP_PASSWORD",
        "VP_DATABASE",
        "VP_CLIENT_ID",
        "VP_CLIENT_SECRET"
    ]
    
    print("Checking environment variables...")
    missing_vars = []
    for var in required_env_vars:
        value = os.environ.get(var)
        if value:
            if var in ["VP_PASSWORD", "VP_CLIENT_SECRET"]:
                print(f"✓ {var}: {'*' * len(value)}")  # Mask sensitive data
            else:
                print(f"✓ {var}: {value}")
        else:
            missing_vars.append(var)
            print(f"✗ {var}: NOT SET")
    
    if missing_vars:
        print(f"\nERROR: Missing required environment variables: {', '.join(missing_vars)}")
        print("Please set these variables in your .env file or environment.")
        return False
    
    print("\n" + "-" * 60)
    print("ATTEMPTING AUTHENTICATION...")
    print("-" * 60)
    
    try:
        # Call the authentication function
        token_response = get_vantagepoint_token()
        
        print("✓ Authentication successful!")
        print("\nResponse details:")
        print("-" * 30)
        
        # Pretty print the response
        for key, value in token_response.items():
            if key.lower() in ['access_token', 'refresh_token', 'token']:
                # Mask tokens for security but show first/last few characters
                if isinstance(value, str) and len(value) > 10:
                    masked_value = f"{value[:6]}...{value[-6:]}"
                    print(f"{key}: {masked_value}")
                else:
                    print(f"{key}: {'*' * 8}")
            else:
                print(f"{key}: {value}")
        
        # Additional token analysis
        print("\n" + "-" * 30)
        print("TOKEN ANALYSIS:")
        print("-" * 30)
        
        if 'access_token' in token_response:
            token = token_response['access_token']
            print(f"Access token length: {len(token)} characters")
            print(f"Token type: {type(token).__name__}")
        
        if 'expires_in' in token_response:
            expires_in = token_response['expires_in']
            print(f"Token expires in: {expires_in} seconds ({expires_in/3600:.1f} hours)")
        
        if 'token_type' in token_response:
            print(f"Token type: {token_response['token_type']}")
        
        return True
        
    except httpx.HTTPStatusError as e:
        print(f"✗ HTTP Error occurred:")
        print(f"  Status Code: {e.response.status_code}")
        print(f"  Reason: {e.response.reason_phrase}")
        print(f"  URL: {e.request.url}")
        
        try:
            error_detail = e.response.json()
            print(f"  Error Detail: {json.dumps(error_detail, indent=2)}")
        except:
            print(f"  Response Text: {e.response.text}")
        
        return False
        
    except httpx.RequestError as e:
        print(f"✗ Request Error occurred:")
        print(f"  Error: {str(e)}")
        print("  This could be a network connectivity issue or invalid URL.")
        return False
        
    except Exception as e:
        print(f"✗ Unexpected error occurred:")
        print(f"  Error Type: {type(e).__name__}")
        print(f"  Error Message: {str(e)}")
        return False

def test_endpoint_connectivity():
    """
    Test basic connectivity to the Vantagepoint endpoint
    """
    print("\n" + "=" * 60)
    print("ENDPOINT CONNECTIVITY TEST")
    print("=" * 60)
    
    base_url = os.environ.get("VP_BASE_URL")
    if not base_url:
        print("✗ VP_BASE_URL not set")
        return False
    
    print(f"Testing connectivity to: {base_url}")
    
    try:
        # Test basic connectivity
        response = httpx.get(base_url, timeout=10.0)
        print(f"✓ Endpoint is reachable")
        print(f"  Status Code: {response.status_code}")
        print(f"  Response Headers: {dict(response.headers)}")
        return True
        
    except httpx.TimeoutException:
        print(f"✗ Timeout connecting to {base_url}")
        return False
        
    except httpx.RequestError as e:
        print(f"✗ Connection error: {str(e)}")
        return False
        
    except Exception as e:
        print(f"✗ Unexpected error: {str(e)}")
        return False

if __name__ == "__main__":
    print("Starting Vantagepoint Authentication Live Tests...")
    print()
    
    # Test endpoint connectivity first
    connectivity_ok = test_endpoint_connectivity()
    
    # Test authentication
    auth_ok = test_vp_authentication()
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Endpoint Connectivity: {'✓ PASS' if connectivity_ok else '✗ FAIL'}")
    print(f"Authentication Test: {'✓ PASS' if auth_ok else '✗ FAIL'}")
    print(f"Overall Result: {'✓ ALL TESTS PASSED' if (connectivity_ok and auth_ok) else '✗ SOME TESTS FAILED'}")
    print(f"Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Exit with appropriate code
    sys.exit(0 if (connectivity_ok and auth_ok) else 1)
