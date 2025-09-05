#!/usr/bin/env python3
"""
Performance profiler for the HR-MCP service to identify bottlenecks
"""

import asyncio
import httpx
import json
import time
from datetime import datetime

async def profile_request():
    """Profile a typical request to identify bottlenecks"""
    
    base_url = "http://127.0.0.1:5001"
    
    payload = {
        "question": "What is our badge policy?",
        "model": "gia-chat",
        "stream": False  # Start with non-streaming to get full timing
    }
    
    print(f"=== Performance Profile - {datetime.now()} ===")
    print(f"Target URL: {base_url}/ask-file")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print()
    
    # Timing checkpoints
    checkpoints = {}
    
    try:
        # 1. Connection setup
        start_time = time.time()
        checkpoints['start'] = start_time
        
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            checkpoints['client_created'] = time.time()
            print(f"✓ Client created: {(checkpoints['client_created'] - checkpoints['start'])*1000:.1f}ms")
            
            # 2. Request initiation
            response = await client.post(
                f"{base_url}/ask-file",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
            )
            checkpoints['response_received'] = time.time()
            print(f"✓ Response received: {(checkpoints['response_received'] - checkpoints['client_created'])*1000:.1f}ms")
            
            # 3. Parse response
            if response.status_code == 200:
                data = response.json()
                checkpoints['response_parsed'] = time.time()
                print(f"✓ Response parsed: {(checkpoints['response_parsed'] - checkpoints['response_received'])*1000:.1f}ms")
                
                # 4. Response analysis
                if 'response' in data:
                    response_len = len(data['response'])
                    sources_count = len(data.get('sources', []))
                    print(f"✓ Response length: {response_len} chars")
                    print(f"✓ Sources count: {sources_count}")
                else:
                    print(f"⚠ Unexpected response format: {list(data.keys())}")
                    
            else:
                print(f"❌ Request failed: {response.status_code} - {response.text}")
                
        checkpoints['complete'] = time.time()
        
        # Summary
        total_time = checkpoints['complete'] - checkpoints['start']
        print()
        print("=== Timing Breakdown ===")
        print(f"Client setup:      {(checkpoints['client_created'] - checkpoints['start'])*1000:.1f}ms")
        print(f"Network request:   {(checkpoints['response_received'] - checkpoints['client_created'])*1000:.1f}ms")
        print(f"Response parsing:  {(checkpoints['response_parsed'] - checkpoints['response_received'])*1000:.1f}ms")
        print(f"Total time:        {total_time*1000:.1f}ms ({total_time:.2f}s)")
        
        return total_time
        
    except Exception as e:
        print(f"❌ Error during profiling: {e}")
        import traceback
        traceback.print_exc()
        return None

async def profile_streaming_request():
    """Profile a streaming request to compare performance"""
    
    base_url = "http://127.0.0.1:5001"
    
    payload = {
        "question": "What is our badge policy?",
        "model": "gia-chat", 
        "stream": True
    }
    
    print(f"\n=== Streaming Performance Profile ===")
    
    try:
        start_time = time.time()
        first_chunk_time = None
        last_chunk_time = None
        chunk_count = 0
        
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            async with client.stream(
                "POST",
                f"{base_url}/ask-file",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream"
                }
            ) as response:
                
                if response.status_code != 200:
                    print(f"❌ Streaming request failed: {response.status_code}")
                    return None
                
                async for line in response.aiter_lines():
                    current_time = time.time()
                    
                    if first_chunk_time is None:
                        first_chunk_time = current_time
                        print(f"✓ First chunk received: {(first_chunk_time - start_time)*1000:.1f}ms")
                    
                    if line.strip():
                        chunk_count += 1
                        last_chunk_time = current_time
                        
                        # Show first few chunks for debugging
                        if chunk_count <= 3:
                            print(f"  Chunk {chunk_count}: {line[:80]}...")
                            
                        if line.strip() == "data: [DONE]":
                            break
                
                total_time = last_chunk_time - start_time
                time_to_first = (first_chunk_time - start_time) * 1000
                
                print(f"✓ Streaming complete: {total_time:.2f}s")
                print(f"✓ Time to first chunk: {time_to_first:.1f}ms")
                print(f"✓ Total chunks: {chunk_count}")
                
                return time_to_first, total_time
                
    except Exception as e:
        print(f"❌ Error during streaming profile: {e}")
        return None

async def compare_performance():
    """Compare non-streaming vs streaming performance"""
    
    print("Starting performance comparison...")
    
    # Test regular request
    regular_time = await profile_request()
    
    # Test streaming request  
    streaming_result = await profile_streaming_request()
    
    if regular_time and streaming_result:
        time_to_first, streaming_total = streaming_result
        
        print(f"\n=== Performance Comparison ===")
        print(f"Regular response:     {regular_time:.2f}s")
        print(f"Streaming total:      {streaming_total:.2f}s") 
        print(f"Time to first chunk:  {time_to_first:.0f}ms")
        print(f"Streaming advantage:  {((regular_time - time_to_first/1000) / regular_time * 100):.1f}% faster to first content")

if __name__ == "__main__":
    print("HR-MCP Performance Profiler")
    print("Make sure the server is running on localhost:5001")
    print()
    
    asyncio.run(compare_performance())
