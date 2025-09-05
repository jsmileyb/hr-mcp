#!/usr/bin/env python3
"""
Quick test to confirm DNS vs IP performance difference
"""

import asyncio
import httpx
import time

async def test_dns_vs_ip():
    """Test localhost vs 127.0.0.1 performance"""
    
    test_payload = {
        "question": "What is the vacation policy?",
        "model": "gpt-5", 
        "stream": False
    }
    
    tests = [
        ("localhost", "http://localhost:5001/ask-file"),
        ("127.0.0.1", "http://127.0.0.1:5001/ask-file")
    ]
    
    for name, url in tests:
        print(f"\n--- Testing {name} ---")
        start_time = time.time()
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, json=test_payload)
                elapsed = time.time() - start_time
                
                if response.status_code == 200:
                    print(f"✅ {name}: {elapsed:.2f}s - SUCCESS")
                else:
                    print(f"❌ {name}: {elapsed:.2f}s - Status: {response.status_code}")
                    
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"❌ {name}: {elapsed:.2f}s - Error: {e}")

if __name__ == "__main__":
    print("🔍 Testing DNS vs IP Performance")
    print("=" * 40)
    asyncio.run(test_dns_vs_ip())
