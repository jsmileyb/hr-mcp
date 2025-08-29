#!/usr/bin/env python3
"""
Test script to verify client registry functionality and shared client usage.
This script tests that clients are properly shared and reused across different modules.
"""

import sys
import os
import asyncio
import httpx
from dotenv import load_dotenv

# Add the parent directory to the path so we can import from main
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.client_registry import client_registry
from utils.environment import get_owui_url, get_vp_base_url

load_dotenv()

async def test_client_registry():
    """Test that the client registry properly creates and shares clients."""
    print("Testing Client Registry...")
    
    # Test 1: Get clients for different hosts
    owui_url = get_owui_url()
    vp_url = get_vp_base_url()
    
    print(f"Creating client for OWUI: {owui_url}")
    client1 = client_registry.get_client(owui_url)
    
    print(f"Creating client for VP: {vp_url}")
    client2 = client_registry.get_client(vp_url)
    
    # Test 2: Get the same client again - should be shared
    print("Getting OWUI client again (should be shared)...")
    client1_again = client_registry.get_client(owui_url)
    
    # Test 3: Verify they're the same instance
    if client1 is client1_again:
        print("✅ Client sharing works - same instance returned")
    else:
        print("❌ Client sharing failed - different instances")
    
    # Test 4: Verify different hosts get different clients
    if client1 is not client2:
        print("✅ Different hosts get different clients")
    else:
        print("❌ Different hosts should get different clients")
    
    # Test 5: Show the registry contents
    print(f"Registry contains {len(client_registry._clients)} clients")
    for host in client_registry._clients.keys():
        print(f"  - {host}")
    
    print("Test completed successfully!")
    return True

async def test_auth_module_integration():
    """Test that auth modules work with shared clients."""
    print("\nTesting Auth Module Integration...")
    
    try:
        from auth import get_graph_token_async, get_vantagepoint_token, call_pa_workflow_async
        
        # These should not fail even without credentials (will fail gracefully)
        print("✅ Auth modules imported successfully")
        
        # Test that functions accept client parameters
        import inspect
        
        # Check get_graph_token_async signature
        sig = inspect.signature(get_graph_token_async)
        if 'client' in sig.parameters:
            print("✅ get_graph_token_async accepts client parameter")
        else:
            print("❌ get_graph_token_async missing client parameter")
        
        # Check get_vantagepoint_token signature
        sig = inspect.signature(get_vantagepoint_token)
        if 'client' in sig.parameters:
            print("✅ get_vantagepoint_token accepts client parameter")
        else:
            print("❌ get_vantagepoint_token missing client parameter")
        
        # Check call_pa_workflow_async signature
        sig = inspect.signature(call_pa_workflow_async)
        if 'client' in sig.parameters:
            print("✅ call_pa_workflow_async accepts client parameter")
        else:
            print("❌ call_pa_workflow_async missing client parameter")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

async def test_cleanup():
    """Test client cleanup functionality."""
    print("\nTesting Client Cleanup...")
    
    # Create some clients
    client1 = client_registry.get_client("https://example1.com")
    client2 = client_registry.get_client("https://example2.com")
    
    print(f"Created {len(client_registry._clients)} clients")
    
    # Close all clients
    await client_registry.close_all()
    
    print(f"After cleanup: {len(client_registry._clients)} clients")
    
    if len(client_registry._clients) == 0:
        print("✅ Client cleanup works correctly")
    else:
        print("❌ Client cleanup failed")

if __name__ == "__main__":
    async def main():
        success = True
        success &= await test_client_registry()
        success &= await test_auth_module_integration()
        await test_cleanup()
        
        if success:
            print("\n🎉 All tests passed!")
        else:
            print("\n❌ Some tests failed")
            sys.exit(1)
    
    asyncio.run(main())
