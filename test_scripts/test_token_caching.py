#!/usr/bin/env python3
"""
Test script to verify token caching functionality.
This script tests that tokens are properly cached and reused.
"""

import sys
import os
import asyncio
import httpx
import time
from dotenv import load_dotenv

# Add the parent directory to the path so we can import from main
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from auth import get_cached_service_token, clear_token_cache
from utils.environment import get_owui_url, get_owui_jwt

load_dotenv()

async def test_token_caching():
    """Test token caching functionality"""
    print("🧪 Testing Token Caching...")
    
    owui_url = get_owui_url()
    jwt = get_owui_jwt()
    
    if not owui_url or not jwt:
        print("❌ Missing required environment variables")
        return False
    
    async with httpx.AsyncClient(base_url=owui_url) as client:
        # Clear any existing cache
        await clear_token_cache()
        print("✅ Cleared token cache")
        
        # First call - should exchange JWT for service token
        print("\n📞 First token request (should exchange JWT)...")
        start_time = time.time()
        token1 = await get_cached_service_token(client, jwt)
        first_duration = time.time() - start_time
        print(f"✅ Got token: {token1[:20]}...{token1[-10:] if len(token1) > 30 else ''}")
        print(f"⏱️  Duration: {first_duration:.3f}s")
        
        # Second call - should use cached token
        print("\n📞 Second token request (should use cache)...")
        start_time = time.time()
        token2 = await get_cached_service_token(client, jwt)
        second_duration = time.time() - start_time
        print(f"✅ Got token: {token2[:20]}...{token2[-10:] if len(token2) > 30 else ''}")
        print(f"⏱️  Duration: {second_duration:.3f}s")
        
        # Verify tokens are the same
        if token1 == token2:
            print("✅ Tokens match - caching working!")
        else:
            print("❌ Tokens don't match - caching not working")
            return False
        
        # Verify second call was faster (cache hit)
        if second_duration < first_duration * 0.5:  # Should be significantly faster
            print(f"✅ Cache hit was {first_duration/second_duration:.1f}x faster")
        else:
            print("⚠️  Cache hit wasn't significantly faster (might still be working)")
        
        # Test cache clearing
        print("\n🧹 Testing cache clearing...")
        await clear_token_cache()
        print("✅ Cache cleared")
        
        # Third call - should exchange again
        print("\n📞 Third token request (after cache clear)...")
        start_time = time.time()
        token3 = await get_cached_service_token(client, jwt)
        third_duration = time.time() - start_time
        print(f"✅ Got token: {token3[:20]}...{token3[-10:] if len(token3) > 30 else ''}")
        print(f"⏱️  Duration: {third_duration:.3f}s")
        
        # This should be a new exchange (similar duration to first call)
        if third_duration > second_duration * 2:  # Should be much slower than cache hit
            print("✅ Cache clearing forces new token exchange")
        else:
            print("⚠️  Duration suggests cache might not have been cleared")
        
        print("\n🎉 Token caching test completed successfully!")
        return True

async def test_concurrent_requests():
    """Test multiple concurrent requests to verify thread safety"""
    print("\n🧪 Testing Concurrent Token Requests...")
    
    owui_url = get_owui_url()
    jwt = get_owui_jwt()
    
    async with httpx.AsyncClient(base_url=owui_url) as client:
        # Clear cache
        await clear_token_cache()
        
        # Make 5 concurrent requests
        print("📞 Making 5 concurrent token requests...")
        start_time = time.time()
        
        tasks = [get_cached_service_token(client, jwt) for _ in range(5)]
        tokens = await asyncio.gather(*tasks)
        
        duration = time.time() - start_time
        print(f"⏱️  Total duration: {duration:.3f}s")
        
        # All tokens should be the same
        unique_tokens = set(tokens)
        if len(unique_tokens) == 1:
            print("✅ All concurrent requests got the same token")
            print(f"✅ Token: {tokens[0][:20]}...{tokens[0][-10:] if len(tokens[0]) > 30 else ''}")
        else:
            print(f"❌ Got {len(unique_tokens)} different tokens from concurrent requests")
            return False
        
        print("🎉 Concurrent request test completed successfully!")
        return True

if __name__ == "__main__":
    async def main():
        print("🚀 Starting Token Caching Tests\n")
        
        try:
            success1 = await test_token_caching()
            success2 = await test_concurrent_requests()
            
            if success1 and success2:
                print("\n✅ All token caching tests passed!")
            else:
                print("\n❌ Some tests failed")
                sys.exit(1)
                
        except Exception as e:
            print(f"\n❌ Test failed with error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    asyncio.run(main())
