# Service Authentication Script
import httpx
import logging
import os
from fastapi import HTTPException
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

async def get_service_token(client: httpx.AsyncClient, jwt: str) -> str:
    """
    Exchange the bootstrap JWT for a service/API token via /api/v1/auths/api_key.
    Caches the token. Returns (token, token_type).
    """
    if client is None:
        raise RuntimeError("HTTP client not initialized")

    # Your env expects GET here; Accept JSON; client already has Bearer <JWT>
    try:
        r = await client.get("/api/v1/auths/api_key", headers={"Accept": "application/json", "Authorization": f"Bearer {jwt}"})
        r.raise_for_status()
        payload = r.json()
    except httpx.HTTPError as e:
        logger.error("Failed to fetch /api/v1/auths/api_key: %s", e)
        raise HTTPException(status_code=502, detail=f"GIA /api/v1/auths/api_key error: {e}")
    except Exception as e:
        logger.exception("Non-HTTP error parsing /api/v1/auths/api_key")
        raise HTTPException(status_code=502, detail=f"Bad /api/v1/auths/api_key payload: {e}")

    # Token fields per your sample: { "token": "...", "token_type": "Bearer", "email": ... }
    key = payload.get("api_key")
    if not key:
        raise HTTPException(status_code=502, detail="No 'api_key' in /api/v1/auths/ response")

    logger.debug(f"Returned key is: {key}")
    return key


async def get_current_user_email(client: httpx.AsyncClient, key: str) -> str:
    """
    Fetch the authenticated user's email from OWUI /api/v1/auths/.
    Uses service token if available, otherwise the bootstrap JWT.
    """
    if client is None:
        raise RuntimeError("HTTP client not initialized")

    # We can also refresh service token here; but GET works with JWT in many setups.
    try:
        r = await client.get("/api/v1/auths/", headers={"Accept": "application/json", "Authorization": f"Bearer {key}"})
        r.raise_for_status()
        payload = r.json()
    except httpx.HTTPError as e:
        logger.error("Failed to fetch /api/v1/auths/: %s", e)
        raise HTTPException(status_code=502, detail=f"GIA /api/v1/auths/ error: {e}")

    if not payload:
        raise HTTPException(status_code=502, detail="No payload in /api/v1/auths/ response")
    return payload
