# Power Automate Workflow Authentication and Communication Script
import httpx
import logging
import json
import os
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from utils.client_registry import client_registry

load_dotenv()

logger = logging.getLogger(__name__)

async def call_pa_workflow_async(
    payload: Dict[str, Any], 
    token: Optional[str], 
    client: Optional[httpx.AsyncClient] = None
) -> Optional[Dict[str, Any]]:
    """
    Call Power Automate workflow with optional authentication token.
    
    Args:
        payload: JSON payload to send to the workflow
        token: Optional bearer token for authentication
        client: Optional shared AsyncClient to use, otherwise gets one from registry
        
    Returns:
        Response JSON dict or None if call fails
    """
    logger.debug(f"call_pa_workflow_async payload: {json.dumps(payload, indent=2)} token: {'set' if token else 'unset'}")
    
    PA_URL = os.environ.get("PA_URL")
    if not PA_URL:
        logger.error("PA_URL not set")
        return None

    # Use provided client or get one from registry
    if client is None:
        client = client_registry.get_client(PA_URL)

    headers = {"Content-Type": "application/json"}
    # If your Flow is protected by Entra ID / custom connector, include the bearer:
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        # r = await ac.post(PA_URL, json=payload, headers=headers)
        r = await client.post(PA_URL, json=payload)
        if r.status_code == 200:
            return r.json()
        logger.error("PA workflow call failed %s: %s", r.status_code, r.text[:400])
        return None
    except httpx.HTTPError as e:
        logger.error("PA workflow call error: %s", e)
        return None
