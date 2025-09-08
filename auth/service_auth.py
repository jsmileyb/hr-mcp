# Service Authentication Script

import httpx
import logging
import os
from fastapi import HTTPException
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


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


async def get_cached_service_token(client: httpx.AsyncClient, jwt: str = None) -> str:
    """
    Return the static OWUI_KEY from environment for Open WebUI authentication.
    """
    key = os.environ.get("OWUI_KEY")
    if not key:
        raise HTTPException(status_code=502, detail="OWUI_KEY environment variable is not set.")
    return key



    # No longer needed: token exchange logic removed



async def clear_token_cache():
    """
    No-op: Token cache is not used with static OWUI_KEY.
    """
    logger.debug("clear_token_cache called, but no cache is used with OWUI_KEY.")


async def make_authenticated_request(
    client: httpx.AsyncClient,
    method: str = "GET",
    endpoint: str = "",
    **kwargs
) -> httpx.Response:
    """
    Make an authenticated request using the static OWUI_KEY as API key.
    """
    if client is None:
        raise RuntimeError("HTTP client not initialized")

    # Use OWUI_KEY for Authorization
    token = await get_cached_service_token(client)
    headers = kwargs.get("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    kwargs["headers"] = headers

    response = await client.request(method, endpoint, **kwargs)
    response.raise_for_status()
    return response



# Legacy function for backward compatibility
async def get_service_token(client: httpx.AsyncClient = None, jwt: str = None) -> str:
    """
    Legacy function for backward compatibility.
    Use get_cached_service_token instead.
    """
    return await get_cached_service_token(client)


async def get_current_user_email(user: str, client: httpx.AsyncClient, jwt: str = None) -> dict:
    """
    Fetch the authenticated user's email from OWUI /api/v1/auths/.
    Uses static OWUI_KEY for authentication.
    """
    try:
        r = await make_authenticated_request(
            client,
            "GET",
            f"/api/v1/users/?page=1&query={user}&order_by=created_at&direction=asc",
            headers={"Accept": "application/json"}
        )
        payload = r.json()
    except httpx.HTTPError as e:
        logger.error("Failed to fetch /api/v1/users/: %s", e)
        raise HTTPException(status_code=502, detail=f"GIA /api/v1/users/ error: {e}")

    if not payload:
        raise HTTPException(status_code=502, detail="No payload in /api/v1/users/ response")
    return payload
