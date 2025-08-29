#!/usr/bin/env python3
"""
Test script to verify streaming responses work correctly.
This script tests both streaming and non-streaming endpoints.
"""

import sys
import os
import asyncio
import httpx
import json
from dotenv import load_dotenv

# Add the parent directory to the path so we can import from main
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

load_dotenv()

async def test_streaming_response():
    """Test the streaming /ask-file endpoint"""
    print("Testing streaming response...")
    
    # Start the FastAPI app in the background or assume it's running
    base_url = "http://localhost:5001"
    
    async with httpx.AsyncClient() as client:
        payload = {
            "question": "What is the vacation policy?",
            "model": "gpt-5", 
            "stream": True
        }
        
        try:
            async with client.stream(
                "POST",
                f"{base_url}/ask-file",
                json=payload,
                headers={"Accept": "text/event-stream"}
            ) as response:
                print(f"Response status: {response.status_code}")
                print(f"Response headers: {dict(response.headers)}")
                
                if response.status_code == 200:
                    print("\n--- Streaming Response ---")
                    
                    async for line in response.aiter_lines():
                        if line.strip():
                            print(f"Received: {line}")
                            
                            if line.startswith("data: "):
                                data_part = line[6:].strip()
                                if data_part == "[DONE]":
                                    print("Stream completed!")
                                    break
                                try:
                                    chunk_data = json.loads(data_part)
                                    print(f"Parsed chunk: {chunk_data}")
                                except json.JSONDecodeError:
                                    print(f"Non-JSON data: {data_part}")
                else:
                    print(f"Error response: {await response.aread()}")
                    
        except Exception as e:
            print(f"Error testing streaming: {e}")

async def test_non_streaming_response():
    """Test the non-streaming /ask-file endpoint for comparison"""
    print("\nTesting non-streaming response...")
    
    base_url = "http://localhost:5001"
    
    async with httpx.AsyncClient() as client:
        payload = {
            "question": "What is the vacation policy?",
            "model": "gpt-5",
            "stream": False
        }
        
        try:
            response = await client.post(
                f"{base_url}/ask-file",
                json=payload,
                headers={"Accept": "application/json"}
            )
            
            print(f"Response status: {response.status_code}")
            print(f"Response headers: {dict(response.headers)}")
            
            if response.status_code == 200:
                data = response.json()
                print("\n--- Non-Streaming Response ---")
                print(f"Normalized text length: {len(data.get('normalized_text', ''))}")
                print(f"Sources count: {len(data.get('sources', []))}")
                print(f"Instructions: {data.get('instructions', '')[:100]}...")
            else:
                print(f"Error response: {response.text}")
                
        except Exception as e:
            print(f"Error testing non-streaming: {e}")

async def test_streaming_with_direct_http_client():
    """Test streaming using the http_client module directly"""
    print("\nTesting streaming with direct HTTP client...")
    
    try:
        from utils.environment import get_owui_url, get_owui_jwt, get_hardcoded_file_id
        from utils.http_client import ensure_model, post_chat_completions_stream
        
        owui = get_owui_url()
        jwt = get_owui_jwt()
        file_id = get_hardcoded_file_id()
        
        async with httpx.AsyncClient(
            base_url=owui,
            timeout=httpx.Timeout(connect=5, read=30, write=30, pool=30),
            http2=True
        ) as client:
            
            model_alias = {"gpt-5": "gpt-5"}
            model_id = await ensure_model(client, "gpt-5", jwt, model_alias)
            
            payload = {
                "model": model_id,
                "stream": True,
                "messages": [{"role": "user", "content": "What is the vacation policy?"}],
                "files": [{"id": file_id, "type": "file", "status": "processed"}],
            }
            
            print("Streaming chunks from OWUI...")
            async for chunk in post_chat_completions_stream(client, payload, jwt):
                print(f"Chunk: {chunk.strip()}")
                
    except Exception as e:
        print(f"Error testing direct streaming: {e}")

if __name__ == "__main__":
    print("=== Streaming Response Test ===")
    print("Make sure the FastAPI server is running on localhost:5001")
    print("Start with: uvicorn main:app --host 0.0.0.0 --port 5001 --reload")
    print()
    
    asyncio.run(test_streaming_response())
    asyncio.run(test_non_streaming_response())
    asyncio.run(test_streaming_with_direct_http_client())
