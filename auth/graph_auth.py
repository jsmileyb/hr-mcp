# Microsoft Graph Authentication Script
import httpx
import logging
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

async def get_graph_token_async() -> Optional[str]:
    """
    Acquire Microsoft Graph token for client credentials flow.
    Returns access token or None if acquisition fails.
    """
    GRAPH_TOKEN_URL = os.environ.get("GRAPH_TOKEN_URL")
    GRAPH_CLIENT_ID = os.environ.get("GRAPH_CLIENT_ID")
    GRAPH_SECRET = os.environ.get("GRAPH_SECRET")
    
    if not all([GRAPH_TOKEN_URL, GRAPH_CLIENT_ID, GRAPH_SECRET]):
        logger.error("GRAPH_* env vars missing; cannot acquire token")
        return None

    data = {
        "grant_type": "client_credentials",
        "client_id": GRAPH_CLIENT_ID,
        "client_secret": GRAPH_SECRET,
        # Power Automate resource (Flow) – confirm in your tenant; this often works:
        "scope": "https://service.flow.microsoft.com//.default",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as ac:
            r = await ac.post(
                GRAPH_TOKEN_URL,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        r.raise_for_status()
        token = r.json().get("access_token")
        if not token:
            logger.error("No access_token in token response: %s", r.text[:400])
        return token
    except httpx.HTTPError as e:
        logger.error("Failed to obtain token: %s", e)
        return None
