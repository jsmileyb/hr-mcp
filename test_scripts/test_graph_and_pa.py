import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from auth import get_graph_token_async, call_pa_workflow_async

async def main():
    email = "smiley.baltz@greshamsmith.com"
    print("Testing get_graph_token_async()...")
    token = await get_graph_token_async()
    print(f"Token acquired: {bool(token)}")
    if not token:
        print("Failed to obtain token. Aborting workflow call.")
        return
    print(f"Testing call_pa_workflow_async() with email: {email}")
    response = await call_pa_workflow_async({"CompanyEmailAddress": email}, token)
    print(f"Workflow response keys: {list(response.keys()) if isinstance(response, dict) else type(response)}")

if __name__ == "__main__":
    asyncio.run(main())
