#!/usr/bin/env python3
"""
Test streaming vs non-streaming performance directly to OWUI
"""

import asyncio
import httpx
import json
import time
import os
from datetime import datetime

# Load environment
from dotenv import load_dotenv
load_dotenv()

OWUI_URL = os.getenv("GIA_URL", "http://127.0.0.1:8080")
OWUI_JWT = os.getenv("OWUI_JWT")
FILE_ID = os.getenv("HARDCODED_FILE_ID")

async def test_owui_direct():
    """Test OWUI response times directly"""
    
    print(f"=== OWUI Direct Performance Test ===")
    print(f"OWUI URL: {OWUI_URL}")
    print(f"File ID: {FILE_ID}")
    print()
    
    # Get service token first
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        
        # 1. Get service token
        print("🔑 Getting service token...")
        start_time = time.time()
        
        auth_response = await client.post(
            f"{OWUI_URL}/api/v1/auths/api_key",
            headers={"Authorization": f"Bearer {OWUI_JWT}"}
        )
        
        if auth_response.status_code != 200:
            print(f"❌ Auth failed: {auth_response.status_code} - {auth_response.text}")
            return
            
        service_token = auth_response.json()["api_key"]
        token_time = time.time() - start_time
        print(f"✓ Service token obtained: {token_time*1000:.1f}ms")
        
        # 2. Test streaming request to OWUI
        print("\n📡 Testing streaming request to OWUI...")
        
        payload = {
            "model": "gia-chat",
            "stream": True,
            "messages": [{"role": "user", "content": "What is our badge policy?"}],
            "files": [{"id": FILE_ID, "type": "file", "status": "processed"}],
        }
        
        start_time = time.time()
        first_chunk_time = None
        chunk_count = 0
        
        async with client.stream(
            "POST",
            f"{OWUI_URL}/api/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {service_token}",
                "Accept": "text/event-stream",
                "Cache-Control": "no-cache"
            }
        ) as response:
            
            if response.status_code != 200:
                print(f"❌ OWUI streaming failed: {response.status_code}")
                print(f"Response: {await response.aread()}")
                return
                
            print(f"✓ OWUI streaming response: {response.status_code}")
            print(f"Content-Type: {response.headers.get('content-type')}")
            
            async for line in response.aiter_lines():
                current_time = time.time()
                
                if first_chunk_time is None:
                    first_chunk_time = current_time
                    time_to_first = (first_chunk_time - start_time) * 1000
                    print(f"✓ First chunk from OWUI: {time_to_first:.1f}ms")
                
                if line.strip():
                    chunk_count += 1
                    
                    # Show first few chunks
                    if chunk_count <= 5:
                        print(f"  Chunk {chunk_count}: {line[:100]}...")
                    
                    if line.strip() == "data: [DONE]" or "finish_reason" in line:
                        total_time = current_time - start_time
                        print(f"✓ OWUI streaming complete: {total_time:.2f}s")
                        print(f"✓ Total chunks from OWUI: {chunk_count}")
                        break
        
        # 3. Test non-streaming request to OWUI
        print("\n📄 Testing non-streaming request to OWUI...")
        
        payload_non_stream = {**payload, "stream": False}
        
        start_time = time.time()
        response = await client.post(
            f"{OWUI_URL}/api/chat/completions",
            json=payload_non_stream,
            headers={
                "Authorization": f"Bearer {service_token}",
                "Accept": "application/json"
            }
        )
        
        non_stream_time = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            content_length = len(str(data))
            print(f"✓ Non-streaming response: {non_stream_time:.2f}s")
            print(f"✓ Response size: {content_length} chars")
        else:
            print(f"❌ Non-streaming failed: {response.status_code}")
            
        print(f"\n=== OWUI Performance Summary ===")
        print(f"Service token:     {token_time*1000:.1f}ms")
        print(f"Streaming TTFC:    {time_to_first:.1f}ms")
        print(f"Streaming total:   {total_time:.2f}s")
        print(f"Non-streaming:     {non_stream_time:.2f}s")
        
        # The bottleneck analysis
        print(f"\n🔍 Bottleneck Analysis:")
        print(f"HR-MCP adds:       ~{(5280 - non_stream_time*1000):.0f}ms overhead")
        print(f"OWUI processing:   ~{non_stream_time:.2f}s base time")

if __name__ == "__main__":
    if not OWUI_JWT:
        print("❌ OWUI_JWT environment variable not set")
        exit(1)
        
    asyncio.run(test_owui_direct())
