# Response processing utilities
import json
import logging
from typing import Tuple, List, Any

logger = logging.getLogger(__name__)


def normalize_owui_response(owui: dict) -> Tuple[str, list]:
    """
    Returns (assistant_text, sources_list)

    Supports:
      - {"stream": [ { "sources":[... ] }, {chunk}, {chunk}, ... ] }
      - {"raw_text": "..."} (fallback from post_chat_completions)
      - {"ndjson": [...]}  (rare)
      - Plain {"choices":[...]} JSON (if OWUI ever returns full JSON)
    """
    text_parts: list[str] = []
    sources: list[Any] = []

    if not isinstance(owui, dict):
        return (str(owui), sources)

    # 1) Stream shape
    if "stream" in owui and isinstance(owui["stream"], list):
        for i, item in enumerate(owui["stream"]):
            # first element often contains retrieval sources
            if i == 0 and isinstance(item, dict) and "sources" in item:
                try:
                    sources = item["sources"]
                except Exception:
                    sources = []
            # subsequent chunks with token deltas
            if isinstance(item, dict):
                for ch in item.get("choices", []):
                    delta = (ch or {}).get("delta") or {}
                    c = delta.get("content")
                    if isinstance(c, str):
                        text_parts.append(c)
        return ("".join(text_parts).strip(), sources)

    # 2) Raw text fallback
    if "raw_text" in owui:
        return (str(owui["raw_text"]).strip(), sources)

    # 3) NDJSON fallback
    if "ndjson" in owui and isinstance(owui["ndjson"], list):
        for line in owui["ndjson"]:
            if isinstance(line, dict):
                content = (((line.get("choices") or [{}])[0]).get("delta") or {}).get(
                    "content"
                )
                if isinstance(content, str):
                    text_parts.append(content)
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
