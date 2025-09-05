# Service Authentication Script
import httpx
import logging
import os
import time
import asyncio
from fastapi import HTTPException
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Token cache with TTL
_TOKEN_CACHE = {
    "token": None,
    "expires_at": 0,
    "lock": asyncio.Lock()
}
_TOKEN_TTL = 3600  # 1 hour default TTL


def extract_single_user_email(user_response: dict) -> str:
    """
    Ensure the user response contains exactly one user and extract the email.
    Raises HTTPException if not found or ambiguous.
    """
    if not user_response or user_response.get("total") != 1:
        raise HTTPException(status_code=502, detail="Could not uniquely resolve current user from GIA/OWUI")
    users = user_response.get("users", [])
    if not users or not users[0].get("email"):
        raise HTTPException(status_code=502, detail="No email found for current user")
    return users[0]["email"]


async def get_cached_service_token(client: httpx.AsyncClient, jwt: str) -> str:
    """
    Get a cached service token, exchanging for a new one if needed.
    This is the main function to use for getting service tokens.
    """
    async with _TOKEN_CACHE["lock"]:
        now = time.time()
        
        # Check if we have a valid cached token
        if (_TOKEN_CACHE["token"] and 
            _TOKEN_CACHE["expires_at"] > now + 60):  # 60 second buffer
            logger.debug("Using cached service token")
            return _TOKEN_CACHE["token"]
        
        # Exchange for new token
        logger.debug("Exchanging JWT for new service token")
        token = await _exchange_service_token(client, jwt)
        
        # Cache the token
        _TOKEN_CACHE["token"] = token
        _TOKEN_CACHE["expires_at"] = now + _TOKEN_TTL
        
        return token


async def _exchange_service_token(client: httpx.AsyncClient, jwt: str) -> str:
    """
    Internal function to exchange JWT for service token.
    """
    if client is None:
        raise RuntimeError("HTTP client not initialized")

    try:
        r = await client.get(
            "/api/v1/auths/api_key", 
            headers={
                "Accept": "application/json", 
                "Authorization": f"Bearer {jwt}"
            }
        )
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

    logger.debug("Successfully exchanged JWT for service token")
    return key


async def clear_token_cache():
    """
    Clear the cached token (useful when getting 401 errors).
    """
    async with _TOKEN_CACHE["lock"]:
        _TOKEN_CACHE["token"] = None
        _TOKEN_CACHE["expires_at"] = 0
        logger.debug("Cleared service token cache")


async def make_authenticated_request(
    client: httpx.AsyncClient, 
    jwt: str, 
    method: str, 
    endpoint: str, 
    **kwargs
) -> httpx.Response:
    """
    Make an authenticated request using cached service token.
    Automatically retries once if 401 is received.
    """
    if client is None:
        raise RuntimeError("HTTP client not initialized")
    
    # Get service token
    token = await get_cached_service_token(client, jwt)
    
    # Add authorization header
    headers = kwargs.get("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    kwargs["headers"] = headers
    
    try:
        response = await client.request(method, endpoint, **kwargs)
        response.raise_for_status()
        return response
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            logger.warning("Received 401, clearing token cache and retrying")
            await clear_token_cache()
            
            # Retry with fresh token
            token = await get_cached_service_token(client, jwt)
            headers["Authorization"] = f"Bearer {token}"
            kwargs["headers"] = headers
            
            response = await client.request(method, endpoint, **kwargs)
            response.raise_for_status()
            return response
        else:
            raise


# Legacy function for backward compatibility
async def get_service_token(client: httpx.AsyncClient, jwt: str) -> str:
    """
    Legacy function for backward compatibility.
    Use get_cached_service_token instead.
    """
    return await get_cached_service_token(client, jwt)


async def get_current_user_email(user: str, client: httpx.AsyncClient, jwt: str) -> dict:
    """
    Fetch the authenticated user's email from OWUI /api/v1/auths/.
    Uses cached service token.
    
    """
    try:
        r = await make_authenticated_request(
            client, jwt, "GET", f"/api/v1/users/?page=1&query={user}&order_by=created_at&direction=asc",
            headers={"Accept": "application/json"}
        )
        payload = r.json()
    except httpx.HTTPError as e:
        logger.error("Failed to fetch /api/v1/users/: %s", e)
        raise HTTPException(status_code=502, detail=f"GIA /api/v1/users/ error: {e}")

    if not payload:
        raise HTTPException(status_code=502, detail="No payload in /api/v1/users/ response")
    return payload
