#!/usr/bin/env python3
"""
Test script to verify the refactored endpoints still work with token caching.
"""

import sys
import os
import asyncio
import httpx
from dotenv import load_dotenv

# Add the parent directory to the path so we can import from main
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.environment import get_owui_url, get_owui_jwt, get_hardcoded_file_id
from utils.http_client import ensure_model, post_chat_completions

load_dotenv()

async def test_ensure_model():
    """Test the ensure_model function with cached tokens"""
    print("🧪 Testing ensure_model with token caching...")
    
    owui_url = get_owui_url()
    jwt = get_owui_jwt()
    
    if not owui_url or not jwt:
        print("❌ Missing required environment variables")
        return False
    
    async with httpx.AsyncClient(base_url=owui_url) as client:
        try:
            model_alias = {"gpt-5": "gpt-5"}
            model_id = await ensure_model(client, "gpt-5", jwt, model_alias)
            print(f"✅ Model resolved: {model_id}")
            return True
        except Exception as e:
            print(f"❌ ensure_model failed: {e}")
            return False

async def test_chat_completions():
    """Test the chat completions endpoint with cached tokens"""
    print("\n🧪 Testing chat completions with token caching...")
    
    owui_url = get_owui_url()
    jwt = get_owui_jwt()
    file_id = get_hardcoded_file_id()
    
    if not all([owui_url, jwt, file_id]):
        print("❌ Missing required environment variables")
        return False
    
    async with httpx.AsyncClient(base_url=owui_url) as client:
        try:
            # First ensure we have a valid model
            model_alias = {"gpt-5": "gpt-5"}
            model_id = await ensure_model(client, "gpt-5", jwt, model_alias)
            
            # Test chat completions
            payload = {
                "model": model_id,
                "messages": [{"role": "user", "content": "What is the PTO policy?"}],
                "files": [{"id": file_id, "type": "file", "status": "processed"}],
            }
            
            response = await post_chat_completions(client, payload, jwt)
            print(f"✅ Chat completion successful, response keys: {list(response.keys()) if isinstance(response, dict) else type(response)}")
            return True
        except Exception as e:
            print(f"❌ chat completions failed: {e}")
            return False

if __name__ == "__main__":
    async def main():
        print("🚀 Starting API Endpoint Tests with Token Caching\n")
        
        try:
            success1 = await test_ensure_model()
            success2 = await test_chat_completions()
            
            if success1 and success2:
                print("\n✅ All API tests passed with token caching!")
            else:
                print("\n❌ Some API tests failed")
                sys.exit(1)
                
        except Exception as e:
            print(f"\n❌ Test failed with error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    asyncio.run(main())
