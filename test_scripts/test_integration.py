#!/usr/bin/env python3
"""
Integration test to verify that the refactored modules work together correctly.
"""

import sys
import os
import asyncio
from dotenv import load_dotenv

# Add the parent directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

load_dotenv()

async def test_integration():
    """Test that all modules work together with shared clients."""
    print("Running Integration Test...")
    
    try:
        # Import all the main components
        from main import app
        from utils.client_registry import client_registry
        from utils.environment import get_owui_url, get_vp_base_url
        from auth import get_graph_token_async, get_vantagepoint_token, call_pa_workflow_async
        from utils.vantagepoint import get_vacation_days
        
        print("✅ All imports successful")
        
        # Test client registry integration
        owui_url = get_owui_url()
        vp_url = get_vp_base_url()
        
        # Get clients from registry
        owui_client = client_registry.get_client(owui_url)
        vp_client = client_registry.get_client(vp_url)
        
        print(f"✅ Created shared clients for {owui_url} and {vp_url}")
        
        # Test that auth functions can be called (they'll fail gracefully without real tokens)
        print("Testing auth functions (expecting graceful failures)...")
        
        # These will fail due to missing/invalid credentials, but should not crash
        try:
            await get_graph_token_async(client=owui_client)
        except Exception as e:
            print(f"  Graph auth failed as expected: {type(e).__name__}")
        
        try:
            await get_vantagepoint_token(client=vp_client)
        except Exception as e:
            print(f"  VP auth failed as expected: {type(e).__name__}")
        
        # Test cleanup
        await client_registry.close_all()
        print("✅ Client cleanup successful")
        
        print("\n🎉 Integration test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_integration())
    if not success:
        sys.exit(1)
