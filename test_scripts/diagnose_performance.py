#!/usr/bin/env python3
"""
Performance diagnostic script to identify bottlenecks in the /ask-file endpoint
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

async def test_owui_connectivity():
    """Test direct connectivity to OWUI service"""
    print("=== Testing OWUI Connectivity ===")
    
    from utils.environment import get_owui_url, get_owui_jwt
    
    owui_url = get_owui_url()
    jwt = get_owui_jwt()
    
    print(f"OWUI URL: {owui_url}")
    print(f"JWT (masked): {jwt[:20]}...{jwt[-10:] if len(jwt) > 30 else jwt}")
    
    # Test basic connectivity
    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{owui_url}/api/v1/auths/api_key", 
                                      headers={"Authorization": f"Bearer {jwt}"})
            connectivity_time = time.time() - start_time
            print(f"✅ OWUI connectivity: {connectivity_time:.2f}s - Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ JWT-to-token exchange successful")
                return data.get("api_key")
            else:
                print(f"❌ JWT-to-token exchange failed: {response.text}")
                return None
                
    except Exception as e:
        connectivity_time = time.time() - start_time
        print(f"❌ OWUI connectivity failed after {connectivity_time:.2f}s: {e}")
        return None

async def test_model_resolution(service_token: str):
    """Test model resolution performance"""
    if not service_token:
        print("⏭️  Skipping model resolution (no service token)")
        return None
        
    print("\n=== Testing Model Resolution ===")
    
    from utils.environment import get_owui_url
    owui_url = get_owui_url()
    
    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{owui_url}/api/models",
                                      headers={"Authorization": f"Bearer {service_token}"})
            model_time = time.time() - start_time
            print(f"✅ Model resolution: {model_time:.2f}s - Status: {response.status_code}")
            
            if response.status_code == 200:
                models = response.json()
                print(f"✅ Available models: {len(models) if isinstance(models, list) else 'unknown count'}")
                return True
            else:
                print(f"❌ Model resolution failed: {response.text}")
                return False
                
    except Exception as e:
        model_time = time.time() - start_time
        print(f"❌ Model resolution failed after {model_time:.2f}s: {e}")
        return False

async def test_chat_completions(service_token: str):
    """Test the actual chat completions endpoint"""
    if not service_token:
        print("⏭️  Skipping chat completions (no service token)")
        return
        
    print("\n=== Testing Chat Completions ===")
    
    from utils.environment import get_owui_url, get_hardcoded_file_id, get_openai_model
    
    owui_url = get_owui_url()
    file_id = get_hardcoded_file_id()
    model_id = get_openai_model()
    
    payload = {
        "model": model_id,
        "stream": False,
        "messages": [{"role": "user", "content": "What is the vacation policy?"}],
        "files": [{"id": file_id, "type": "file", "status": "processed"}],
    }
    
    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{owui_url}/api/chat/completions",
                                       json=payload,
                                       headers={"Authorization": f"Bearer {service_token}"})
            completion_time = time.time() - start_time
            print(f"✅ Chat completion: {completion_time:.2f}s - Status: {response.status_code}")
            
            if response.status_code == 200:
                print(f"✅ Chat completion successful")
                # Don't print the full response, just confirm it worked
                return True
            else:
                print(f"❌ Chat completion failed: {response.text}")
                return False
                
    except Exception as e:
        completion_time = time.time() - start_time
        print(f"❌ Chat completion failed after {completion_time:.2f}s: {e}")
        return False

async def test_fastapi_endpoint():
    """Test the FastAPI endpoint directly"""
    print("\n=== Testing FastAPI Endpoint ===")
    
    payload = {
        "question": "What is the vacation policy?",
        "model": "gpt-5",
        "stream": False
    }
    
    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post("http://localhost:5001/ask-file",
                                       json=payload,
                                       headers={"Accept": "application/json"})
            endpoint_time = time.time() - start_time
            print(f"✅ FastAPI endpoint: {endpoint_time:.2f}s - Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                normalized_text = data.get("normalized_text", "")
                sources = data.get("sources", [])
                print(f"✅ Response length: {len(normalized_text)} characters")
                print(f"✅ Sources found: {len(sources)}")
                return True
            else:
                print(f"❌ FastAPI endpoint failed: {response.text}")
                return False
                
    except Exception as e:
        endpoint_time = time.time() - start_time
        print(f"❌ FastAPI endpoint failed after {endpoint_time:.2f}s: {e}")
        return False

async def main():
    """Run all diagnostic tests"""
    print("🔍 HR-MCP Performance Diagnostic Tool")
    print("=" * 50)
    
    # Test 1: OWUI connectivity and token exchange
    service_token = await test_owui_connectivity()
    
    # Test 2: Model resolution
    await test_model_resolution(service_token)
    
    # Test 3: Direct chat completions
    await test_chat_completions(service_token)
    
    # Test 4: FastAPI endpoint (requires server to be running)
    await test_fastapi_endpoint()
    
    print("\n" + "=" * 50)
    print("🎯 Diagnostic Summary:")
    print("- If OWUI connectivity is slow (>5s), check network/DNS")
    print("- If model resolution is slow, check OWUI /api/models endpoint")  
    print("- If chat completion is slow, check OWUI processing time")
    print("- If FastAPI endpoint is slow but others are fast, check app logic")
    print("\n💡 Compare these times with your Postman response times!")

if __name__ == "__main__":
    asyncio.run(main())
