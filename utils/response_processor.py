# Response processing utilities
import json
import logging
from typing import Tuple, List, Any, AsyncGenerator

logger = logging.getLogger(__name__)


def normalize_owui_response(owui: dict) -> Tuple[str, list]:
    """
    Returns (assistant_text, sources_list)

    Supports:
      - {"stream": [ { "sources":[... ] }, {chunk}, {chunk}, ... ] }
      - {"raw_text": "..."} (fallback from post_chat_completions)
      - {"ndjson": [...]}  (rare)
      - Plain {"choices":[...]} JSON (if OWUI ever returns full JSON)
    
    Optimized to:
    - Return early on [DONE] signal
    - Use list appending instead of string concatenation
    - Handle sources efficiently
    """
    text_parts: list[str] = []
    sources: list[Any] = []

    if not isinstance(owui, dict):
        return (str(owui), sources)

    # 1) Stream shape - optimized processing
    if "stream" in owui and isinstance(owui["stream"], list):
        for i, item in enumerate(owui["stream"]):
            # Check for early termination signal
            if isinstance(item, str) and item == "[DONE]":
                break
            
            # first element often contains retrieval sources
            if i == 0 and isinstance(item, dict) and "sources" in item:
                try:
                    sources = item["sources"]
                except Exception:
                    sources = []
            
            # subsequent chunks with token deltas
            if isinstance(item, dict):
                # Check if this is a termination signal in dict form
                if item.get("finish_reason") == "stop" or item.get("type") == "done":
                    break
                    
                for ch in item.get("choices", []):
                    delta = (ch or {}).get("delta") or {}
                    c = delta.get("content")
                    if isinstance(c, str):
                        text_parts.append(c)
                        
                    # Check for finish reason in choice - should break out of both loops
                    if (ch or {}).get("finish_reason") == "stop":
                        return ("".join(text_parts).strip(), sources)
        
        return ("".join(text_parts).strip(), sources)

    # 2) Raw text fallback
    if "raw_text" in owui:
        return (str(owui["raw_text"]).strip(), sources)

    # 3) NDJSON fallback - optimized processing
    if "ndjson" in owui and isinstance(owui["ndjson"], list):
        for line in owui["ndjson"]:
            # Check for early termination
            if isinstance(line, str) and line.strip() == "[DONE]":
                break
                
            if isinstance(line, dict):
                # Check for termination signal in dict form
                if line.get("finish_reason") == "stop" or line.get("type") == "done":
                    break
                    
                # Check choices for finish_reason
                for ch in line.get("choices", []):
                    delta = (ch or {}).get("delta") or {}
                    content = delta.get("content")
                    if isinstance(content, str):
                        text_parts.append(content)
                    
                    # Check for finish reason in choice - return immediately
                    if (ch or {}).get("finish_reason") == "stop":
                        return ("".join(text_parts).strip(), sources)
        return ("".join(text_parts).strip(), sources)

    # 4) OpenAI-like full JSON (unlikely via OWUI, but harmless)
    if "choices" in owui:
        try:
            content = (((owui.get("choices") or [{}])[0]).get("message") or {}).get(
                "content"
            )
            if isinstance(content, str):
                return (content.strip(), sources)
        except Exception:
            pass

    logger.debug("Response from GIA: %r", owui)

    # last resort: stringify
    return (json.dumps(owui, ensure_ascii=False), sources)


async def normalize_owui_response_streaming(owui_stream) -> AsyncGenerator[Tuple[str, list], None]:
    """
    Streaming version of normalize_owui_response that yields (text_chunk, sources) tuples
    as they become available, avoiding the need to concatenate the entire response.
    
    Yields:
        Tuple[str, list]: (text_chunk, sources_list) - sources only sent once at start
    """
    sources: list[Any] = []
    sources_sent = False
    item_count = 0

    if hasattr(owui_stream, '__aiter__'):
        # Async iterable stream
        async for item_data in owui_stream:
            # Handle the case where iterator yields (index, item) tuples
            if isinstance(item_data, tuple) and len(item_data) == 2:
                i, item = item_data
            else:
                i = item_count
                item = item_data
            
            item_count += 1
            
            # Extract sources from first item
            if i == 0 and isinstance(item, dict) and "sources" in item and not sources_sent:
                try:
                    sources = item["sources"]
                    yield ("", sources)  # Send sources first
                    sources_sent = True
                except Exception:
                    sources = []
            
            # Check for early termination
            if isinstance(item, str) and item == "[DONE]":
                break
                
            if isinstance(item, dict):
                # Check for termination signal
                if item.get("finish_reason") == "stop" or item.get("type") == "done":
                    break
                    
                # Extract content from choices
                for ch in item.get("choices", []):
                    delta = (ch or {}).get("delta") or {}
                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        yield (content, [] if sources_sent else sources)
                        if not sources_sent:
                            sources_sent = True
                    
                    # Check for finish reason in choice
                    if (ch or {}).get("finish_reason") == "stop":
                        return
                        
    elif isinstance(owui_stream, dict):
        # Fallback to regular normalize_owui_response for dict input
        text, sources = normalize_owui_response(owui_stream)
        yield (text, sources)
    else:
        # Handle other types
        yield (str(owui_stream), [])


def get_sources_from_owui(owui: dict) -> list:
    """
    Quick utility to extract just the sources from an OWUI response
    without processing the entire text content.
    """
    if not isinstance(owui, dict):
        return []
    
    # Stream shape
    if "stream" in owui and isinstance(owui["stream"], list):
        stream_data = owui["stream"]
        if stream_data and isinstance(stream_data[0], dict) and "sources" in stream_data[0]:
            try:
                return stream_data[0]["sources"]
            except Exception:
                pass
    
    # Direct sources
    if "sources" in owui:
        try:
            return owui["sources"]
        except Exception:
            pass
    
    return []
