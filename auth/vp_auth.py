# Vantagepoint Authentication Script
import httpx
from utils.client_registry import client_registry
from urllib.parse import urlencode
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

VP_BASE_URL = os.environ.get("VP_BASE_URL")
VP_USERNAME = os.environ.get("VP_USERNAME")
VP_PASSWORD = os.environ.get("VP_PASSWORD")
VP_DATABASE = os.environ.get("VP_DATABASE")
VP_CLIENT_ID = os.environ.get("VP_CLIENT_ID")
VP_CLIENT_SECRET = os.environ.get("VP_CLIENT_SECRET")

async def get_vantagepoint_token(client: Optional[httpx.AsyncClient] = None):
    """
    Authenticate with Vantagepoint API and return the access token response.
    
    Args:
        client: Optional shared AsyncClient to use, otherwise gets one from registry
    """
    # Use provided client or get one from registry
    if client is None:
        client = client_registry.get_client(VP_BASE_URL)
    
    url = f"{VP_BASE_URL}/api/token"
    payload_dict = {
        "Username": VP_USERNAME,
        "Password": VP_PASSWORD,
        "grant_type": "password",
        "Integrated": "N",
        "database": VP_DATABASE,
        "Client_Id": VP_CLIENT_ID,
        "client_secret": VP_CLIENT_SECRET,
    }
    payload = urlencode(payload_dict)
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    response = await client.post(url, headers=headers, data=payload)
    response.raise_for_status()
    return response.json()

if __name__ == "__main__":
    import asyncio
    token_response = asyncio.run(get_vantagepoint_token())
    print(token_response)
