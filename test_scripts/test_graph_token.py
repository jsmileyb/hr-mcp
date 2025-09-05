import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from auth import get_graph_token_async

async def main():
    token = await get_graph_token_async()
    if token and token.get("access_token"):
        print(f"Access token (truncated): {token['access_token'][:40]}...")
    else:
        print("Failed to obtain token.")

if __name__ == "__main__":
    asyncio.run(main())
