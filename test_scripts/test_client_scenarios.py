#!/usr/bin/env python3
"""
Test script to simulate different client scenarios that might cause the 50s delay
"""

import sys
import os
import asyncio
import httpx
import json
import time
from dotenv import load_dotenv

# Add the parent directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

load_dotenv()

async def test_various_client_scenarios():
    """Test different client configurations that might cause delays"""
    print("🔍 Testing Various Client Scenarios")
    print("=" * 50)
    
    test_payload = {
        "question": "What is the vacation policy?",
        "model": "gpt-5",
        "stream": False
    }
    
    scenarios = [
        {
            "name": "Default httpx client (like Postman)",
            "client_config": {}
        },
        {
            "name": "With HTTP/2 disabled",
            "client_config": {"http2": False}
        },
        {
            "name": "With very short timeout",
            "client_config": {"timeout": 5.0}
        },
        {
            "name": "With connection limits",
            "client_config": {
                "limits": httpx.Limits(max_keepalive_connections=1, max_connections=2)
            }
        },
        {
            "name": "With proxy simulation (bad DNS)",
            "client_config": {
                "timeout": httpx.Timeout(connect=30, read=60, write=30, pool=30)
            }
        },
        {
            "name": "With explicit host resolution",
            "client_config": {},
            "url_override": "http://127.0.0.1:5001/ask-file"
        }
    ]
    
    for scenario in scenarios:
        print(f"\n--- {scenario['name']} ---")
        
        start_time = time.time()
        try:
            url = scenario.get("url_override", "http://localhost:5001/ask-file")
            
            async with httpx.AsyncClient(**scenario["client_config"]) as client:
                response = await client.post(url, json=test_payload)
                elapsed = time.time() - start_time
                
                if response.status_code == 200:
                    print(f"✅ Success: {elapsed:.2f}s")
                else:
                    print(f"❌ Failed: {elapsed:.2f}s - Status: {response.status_code}")
                    
        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            print(f"⏰ Timeout: {elapsed:.2f}s")
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"❌ Error: {elapsed:.2f}s - {type(e).__name__}: {e}")

async def test_streaming_vs_non_streaming():
    """Compare streaming vs non-streaming performance"""
    print("\n" + "=" * 50)
    print("🔍 Testing Streaming vs Non-Streaming")
    print("=" * 50)
    
    base_payload = {
        "question": "What is the vacation policy?",
        "model": "gpt-5"
    }
    
    # Test non-streaming
    print("\n--- Non-Streaming Request ---")
    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {**base_payload, "stream": False}
            response = await client.post("http://localhost:5001/ask-file", json=payload)
            elapsed = time.time() - start_time
            print(f"✅ Non-streaming: {elapsed:.2f}s - Status: {response.status_code}")
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ Non-streaming error: {elapsed:.2f}s - {e}")
    
    # Test streaming
    print("\n--- Streaming Request ---")
    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {**base_payload, "stream": True}
            
            first_chunk_time = None
            total_chunks = 0
            
            async with client.stream("POST", "http://localhost:5001/ask-file", json=payload) as response:
                async for line in response.aiter_lines():
                    if first_chunk_time is None:
                        first_chunk_time = time.time() - start_time
                        print(f"⚡ First chunk: {first_chunk_time:.2f}s")
                    
                    if line.startswith("data: [DONE]"):
                        break
                    total_chunks += 1
                    
            elapsed = time.time() - start_time
            print(f"✅ Streaming complete: {elapsed:.2f}s - Chunks: {total_chunks}")
            
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ Streaming error: {elapsed:.2f}s - {e}")

async def check_server_logs():
    """Instructions for checking server logs"""
    print("\n" + "=" * 50)
    print("📋 Server Log Analysis")
    print("=" * 50)
    print("""
To identify the exact bottleneck:

1. **Check your FastAPI server logs** when making the slow request
   - Look for long delays between log entries
   - Check for any error messages or warnings
   
2. **Enable detailed timing logs** in your app by adding:
   ```python
   import time
   
   @app.middleware("http")
   async def log_request_timing(request, call_next):
       start_time = time.time()
       response = await call_next(request)
       process_time = time.time() - start_time
       logger.info(f"Request {request.url.path} took {process_time:.2f}s")
       return response
   ```
   
3. **Compare the client making the slow request** with Postman:
   - Different machine/container?
   - Different network?
   - Different authentication?
   - Different request headers?
   
4. **Check if your slow client has**:
   - Connection pooling issues
   - Retry logic
   - Proxy configuration
   - DNS resolution problems
    """)

if __name__ == "__main__":
    asyncio.run(test_various_client_scenarios())
    asyncio.run(test_streaming_vs_non_streaming())
    asyncio.run(check_server_logs())
