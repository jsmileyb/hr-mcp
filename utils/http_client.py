import json
import logging
from typing import Dict, AsyncGenerator
import httpx
import asyncio
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
import time

from auth import get_cached_service_token, make_authenticated_request

logger = logging.getLogger(__name__)
_CACHE = {"models": set(), "ts": 0}
_TTL = 300  # 5 minutes
_LOCK = asyncio.Lock()


async def ensure_model(client: httpx.AsyncClient, model_name: str, jwt: str, model_alias: Dict[str, str]) -> str:
    """
    Ensure OWUI recognizes the requested model. Applies MODEL_ALIAS mapping.
    Handles payloads that are:
      - ["gpt-5","gpt-4o", ...]
      - [{"id":"gpt-5"}, {"name":"gpt-4o"}, ...]
      - {"models":[...]} / {"data":[...]} wrappers
      - dict-of-dicts keyed by model id
      - or even a JSON string body (sigh)
    """
    if client is None:
        raise RuntimeError("HTTP client not initialized")

    now = time.time()
    async with _LOCK:
        if not _CACHE["models"] or now - _CACHE["ts"] > _TTL:
            # Fetch from /api/models once and cache
            try:
                r = await make_authenticated_request(
                    client, jwt, "GET", "/api/models",
                    headers={"Accept": "application/json"}
                )
                payload = r.json()
            except httpx.HTTPError as e:
                logger.error("Failed to fetch models from GIA: %s", e)
                raise HTTPException(status_code=502, detail=f"GIA /api/models error: {e}")
            except Exception as e:
                logger.exception("Non-HTTP error parsing /api/models")
                raise HTTPException(status_code=502, detail=f"Bad /api/models payload: {e}")

            models_set: set[str] = set()

            def add_from_list(items):
                for item in items:
                    if isinstance(item, str):
                        models_set.add(item)
                    elif isinstance(item, dict):
                        for k in ("id", "name", "model", "slug"):
                            v = item.get(k)
                            if isinstance(v, str):
                                models_set.add(v)

            if isinstance(payload, list):
                add_from_list(payload)
            elif isinstance(payload, dict):
                for key in ("models", "data", "items", "result"):
                    v = payload.get(key)
                    if isinstance(v, list):
                        add_from_list(v)
                if not models_set:
                    if payload and all(isinstance(v, (dict, str)) for v in payload.values()):
                        models_set.update(map(str, payload.keys()))
                if not models_set:
                    for k in ("id", "name", "model", "slug"):
                        v = payload.get(k)
                        if isinstance(v, str):
                            models_set.add(v)
            elif isinstance(payload, str):
                try:
                    inner = json.loads(payload)
                    if isinstance(inner, list):
                        add_from_list(inner)
                    elif isinstance(inner, dict):
                        for key in ("models", "data", "items", "result"):
                            v = inner.get(key)
                            if isinstance(v, list):
                                add_from_list(v)
                except Exception:
                    models_set.add(payload)

            if not models_set:
                logger.error("Unexpected /api/models payload: %r", payload)
                raise HTTPException(status_code=502, detail="Unexpected /api/models payload")

            _CACHE["models"] = models_set
            _CACHE["ts"] = now

    desired = model_alias.get(model_name, model_name)
    if desired in _CACHE["models"]:
        return desired

    logger.warning(
        "Requested model '%s' not registered. Available: %s",
        desired,
        sorted(_CACHE["models"]),
    )
    raise HTTPException(
        status_code=400,
        detail={
            "error": f"Model '{model_name}' is not registered in GIA",
            "alias_applied": desired if desired != model_name else None,
            "available_models": sorted(_CACHE["models"]),
        },
    )


async def post_chat_completions(client: httpx.AsyncClient, payload: dict, jwt: str) -> dict:
    """
    Call OWUI /api/chat/completions and be tolerant:
    - JSON response
    - SSE-ish text/event-stream containing 'data: {json}'
    - NDJSON
    - text/plain with JSON as text
    - empty body (error)
    """
    if client is None:
        raise RuntimeError("HTTP client not initialized")
    
    try:
        # Use authenticated request with service token
        r = await make_authenticated_request(
            client, jwt, "POST", "/api/chat/completions",
            json=payload,
            headers={"Accept": "application/json"}
        )
    except httpx.HTTPStatusError as e:
        logger.error(
            "OWUI /api/chat/completions %s: %s", e.response.status_code, e.response.text
        )
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        logger.error("HTTP error calling /api/chat/completions: %s", e)
        raise HTTPException(status_code=502, detail=str(e))

    ctype = (r.headers.get("content-type") or "").lower()

    # JSON happy path
    if "application/json" in ctype:
        try:
            return r.json()
        except Exception as e:
            logger.error(
                "JSON parse failed despite application/json. Body (first 400): %r",
                r.text[:400],
            )
            raise HTTPException(
                status_code=502, detail=f"Bad JSON from /api/chat/completions: {e}"
            )

    # SSE stream
    if "text/event-stream" in ctype or "stream" in ctype:
        text = r.text
        events = []
        for line in text.splitlines():
            line = line.strip()
            if not line or not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if chunk == "[DONE]":
                break
            try:
                events.append(json.loads(chunk))
            except Exception:
                logger.debug("Non-JSON SSE line: %r", line)
        if events:
            return {"stream": events}
        logger.error(
            "SSE response had no JSON 'data:' lines. First 400: %r", text[:400]
        )
        raise HTTPException(
            status_code=502, detail="Empty/invalid SSE body from /api/chat/completions"
        )

    # NDJSON
    if "ndjson" in ctype:
        objs = []
        for line in r.text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                objs.append(json.loads(line))
            except Exception:
                logger.debug("Non-JSON NDJSON line: %r", line[:200])
        if objs:
            return {"ndjson": objs}
        raise HTTPException(
            status_code=502, detail="Invalid NDJSON body from /api/chat/completions"
        )

    # text/plain or unknown content-type
    txt = r.text.strip()
    if txt:
        try:
            return json.loads(txt)
        except Exception:
            logger.warning(
                "Non-JSON response (ctype=%s). Returning raw_text. First 400: %r",
                ctype,
                txt[:400],
            )
            return {"raw_text": txt, "content_type": ctype or None}

    logger.error("Empty 200 OK response from /api/chat/completions")
    raise HTTPException(
        status_code=502, detail="Empty response from /api/chat/completions"
    )


async def post_chat_completions_stream(client: httpx.AsyncClient, payload: dict, jwt: str) -> AsyncGenerator[str, None]:
    """
    Stream /api/chat/completions response directly to the client.
    
    This function handles:
    - Server-Sent Events (SSE) streaming
    - NDJSON streaming  
    - Regular JSON responses (converted to single chunk)
    - Source extraction from first chunk
    
    Yields: SSE-formatted strings ready for client consumption
    """
    if client is None:
        raise RuntimeError("HTTP client not initialized")
    
    try:
        # Force streaming in the payload
        payload = {**payload, "stream": True}
        
        # Use authenticated request with service token
        async with client.stream(
            "POST", 
            "/api/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {await get_cached_service_token(client, jwt)}",
                "Accept": "text/event-stream, application/json",
                "Cache-Control": "no-cache"
            }
        ) as response:
            if response.status_code != 200:
                error_text = await response.aread()
                logger.error("OWUI streaming error %s: %s", response.status_code, error_text.decode())
                raise HTTPException(status_code=response.status_code, detail=error_text.decode())
            
            ctype = (response.headers.get("content-type") or "").lower()
            logger.debug("Streaming response content-type: %s", ctype)
            
            sources_sent = False
            
            # Handle SSE streaming
            if "text/event-stream" in ctype or "stream" in ctype:
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                        
                    if line.startswith("data: "):
                        data_part = line[6:].strip()
                        
                        if data_part == "[DONE]":
                            yield "data: [DONE]\n\n"
                            break
                            
                        try:
                            chunk_data = json.loads(data_part)
                            
                            # Extract sources from first chunk if present
                            if not sources_sent and "sources" in chunk_data:
                                sources_event = {
                                    "type": "sources",
                                    "sources": chunk_data["sources"]
                                }
                                yield f"data: {json.dumps(sources_event)}\n\n"
                                sources_sent = True
                            
                            # Forward the chunk as-is
                            yield f"data: {data_part}\n\n"
                            
                        except json.JSONDecodeError:
                            # Forward non-JSON lines as-is (might be control messages)
                            yield f"data: {data_part}\n\n"
                    else:
                        # Forward other SSE lines (like event:, id:, etc.)
                        yield f"{line}\n"
                        
            # Handle NDJSON streaming
            elif "ndjson" in ctype:
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                        
                    try:
                        chunk_data = json.loads(line)
                        
                        # Extract sources from first chunk if present
                        if not sources_sent and "sources" in chunk_data:
                            sources_event = {
                                "type": "sources", 
                                "sources": chunk_data["sources"]
                            }
                            yield f"data: {json.dumps(sources_event)}\n\n"
                            sources_sent = True
                        
                        # Convert NDJSON to SSE format
                        yield f"data: {line}\n\n"
                        
                    except json.JSONDecodeError:
                        logger.debug("Non-JSON NDJSON line: %r", line[:200])
                        
            # Handle regular JSON response (convert to single chunk)
            else:
                content = await response.aread()
                try:
                    data = json.loads(content.decode())
                    
                    # Extract sources if present
                    if "sources" in data:
                        sources_event = {
                            "type": "sources",
                            "sources": data["sources"] 
                        }
                        yield f"data: {json.dumps(sources_event)}\n\n"
                    
                    # Send content as single chunk
                    yield f"data: {json.dumps(data)}\n\n"
                    yield "data: [DONE]\n\n"
                    
                except json.JSONDecodeError:
                    # Handle non-JSON response
                    text_chunk = {
                        "choices": [{
                            "delta": {
                                "content": content.decode()
                            }
                        }]
                    }
                    yield f"data: {json.dumps(text_chunk)}\n\n"
                    yield "data: [DONE]\n\n"
                    
    except httpx.HTTPError as e:
        logger.error("HTTP error in streaming: %s", e)
        error_chunk = {
            "error": {
                "message": str(e),
                "type": "http_error"
            }
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"
        yield "data: [DONE]\n\n"
