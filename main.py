from typing import List, Optional, Tuple, Any
import os, json, logging, sys, uuid

from openai import OpenAI  # pip install openai>=1.0.0
import httpx
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from utils.config import TOOL_NAME  # keep your import

load_dotenv()

# =========================
# App & Logging
# =========================
app = FastAPI(
    title="HR Handbook and Policy MCP for GIA",
    version="0.0.1",
    description="FastAPI microservice that proxies retrieval-backed chat completions to GIA using file or collection IDs.",
)

origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.DEBUG if os.environ.get("DEBUG") else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(TOOL_NAME)

# =========================
# Config / HTTP client
# =========================
OWUI = os.environ.get("GIA_URL", "http://localhost:8080")
TOKEN = os.environ.get("OWUI_TOKEN")
HARDCODED_FILE_ID = os.environ.get("HARDCODED_FILE_ID")  # optional
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")  # set this if you want post-processing
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")  # pick your fave
DEBUG = os.environ.get("DEBUG", False)

# Log all relevant environment variables (mask sensitive values)
def mask_token(token: str | None, show_last: int = 10) -> str | None:
    if not token:
        return None
    if len(token) <= show_last:
        return "*" * len(token)
    return "*" * (len(token) - show_last) + token[-show_last:]

env_vars = {
    "GIA_URL": OWUI,
    "OWUI_TOKEN": mask_token(TOKEN, 10),
    "HARDCODED_FILE_ID": HARDCODED_FILE_ID,
    "OPENAI_API_KEY": mask_token(OPENAI_API_KEY, 10),
    "OPENAI_MODEL": OPENAI_MODEL,
    "DEBUG": DEBUG,
}
logger.debug("Loaded environment variables:\n%s", json.dumps(env_vars, indent=2))

if not TOKEN:
    raise RuntimeError("OWUI_TOKEN is required in the environment.")

# Optional: map your requested model name to an OWUI-registered model id.
# Example: MODEL_ALIAS_JSON='{"gpt-5":"gpt-5o"}'
MODEL_ALIAS = {"gpt-5": "gpt-5"}  # or "gpt-5o" if that’s the registered ID

# Shared async client (init on startup)
client: httpx.AsyncClient | None = None


@app.on_event("startup")
async def _startup():
    global client
    client = httpx.AsyncClient(
        base_url=OWUI,
        headers={"Authorization": f"Bearer {TOKEN}"},
        timeout=60,
    )
    logger.info("HTTP client initialized for GIA at %s", OWUI)


@app.on_event("shutdown")
async def _shutdown():
    global client
    if client:
        await client.aclose()
        logger.info("HTTP client closed")


# =========================
# Pydantic models
# =========================
class AskReq(BaseModel):
    question: str = Field(..., description="User question")
    model: str = Field(
        "gpt-5", description="Model id as registered in GIA (/api/models)"
    )
    stream: bool = Field(False, description="Use streamed responses (server-side)")
    post_process: bool = Field(
        True, description="If true, send OWUI output to OpenAI for refinement"
    )


class AskResp(BaseModel):
    # raw: dict
    normalized_text: Optional[str] = None
    sources: Optional[list] = None
    final_text: Optional[str] = None  # present when post_process=True
    instructions: Optional[str] = None


# =========================
# Helpers
# =========================


async def ensure_model(model_name: str) -> str:
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

    desired = MODEL_ALIAS.get(model_name, model_name)

    try:
        r = await client.get("/api/models")
        r.raise_for_status()
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
            # dict-of-dicts: {"gpt-5": {...}, "gpt-4o": {...}}
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

    if desired in models_set:
        return desired

    logger.warning(
        "Requested model '%s' not registered. Available: %s",
        desired,
        sorted(models_set),
    )
    raise HTTPException(
        status_code=400,
        detail={
            "error": f"Model '{model_name}' is not registered in GIA",
            "alias_applied": desired if desired != model_name else None,
            "available_models": sorted(models_set),
        },
    )


async def post_chat_completions(payload: dict) -> dict:
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
        # Ask politely for JSON
        r = await client.post(
            "/api/chat/completions",
            json=payload,
            headers={"Accept": "application/json"},
        )
        r.raise_for_status()
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


def _ensure_openai_client() -> OpenAI:
    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=500, detail="OPENAI_API_KEY not set but post_process=True"
        )
    try:
        return OpenAI(api_key=OPENAI_API_KEY)
    except Exception as e:
        logger.exception("Failed to init OpenAI client")
        raise HTTPException(status_code=500, detail=f"OpenAI client error: {e}")


async def post_process_with_openai(text: str, sources: list, user_question: str) -> str:
    """
    Use OpenAI to turn the OWUI raw/stream text into a clean, structured answer.
    - Tight prompt that: removes tokenization artifacts, organizes bullets, and (optionally) includes source refs.
    """
    client = _ensure_openai_client()

    # Keep prompt short & deterministic. You can tune style here.
    system_msg = (
        "You are a terse, accurate assistant. Clean up the provided draft answer: "
        "fix broken words, remove token-by-token artifacts, and present a concise, structured response. "
        "If the text already includes headings/bullets, keep them tidy. "
        "Only include details actually present in the draft. If fount, **ALWAYS** include a short 'Sources' list with page reference."
        # "A direct link to the Employee Handbook is available and you can link to it here: https://gspnet4.sharepoint.com/sites/HR/Shared%20Documents/employee-handbook.pdf."
    )

    # Convert sources to a compact list (title/page if present)
    src_lines = []
    for s in sources or []:
        try:
            doc = (s or {}).get("document") or []
            meta = (s or {}).get("metadata") or []
            # Try to find a useful label
            name = page = None
            if isinstance(meta, list) and meta:
                m0 = meta[0]
                name = (
                    (m0.get("name") or m0.get("source") or "").strip()
                    if isinstance(m0, dict)
                    else ""
                )
                page = m0.get("page_label") or m0.get("page") or ""
            label = name or "document"
            if page:
                label = f"{label} p.{page}"
            src_lines.append(f"- {label}")
        except Exception:
            continue

    user_msg = f"""User question:
{user_question}

Draft to clean:
{text}

Sources (REQUIRED):
{chr(10).join(src_lines) if src_lines else "(none)"}"""

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=1,
        )
        cleaned = resp.choices[0].message.content.strip()
        return cleaned
    except Exception as e:
        logger.error("OpenAI post-process failed: %s", e)
        # Fall back to original text so the endpoint still succeeds
        return text or f"(post-process failed: {e})"


# =========================
# Routes
# =========================
@app.post(
    "/ask-file",
    response_model=AskResp,
    summary="Ask HR policy questions using the Employee Handbook",
    description=(
        "Interact with HR policy by querying the Employee Handbook for company policy information via GIA; "
        "optionally post-processes the answer with OpenAI for a clean, concise response."
    ),
)
async def ask_file(req: AskReq = Body(...)):
    """Ask HR policy questions against the Employee Handbook via GIA, with optional OpenAI post-processing."""
    rid = uuid.uuid4().hex[:8]

    q_preview = (req.question or "").replace("\n", " ")
    if len(q_preview) > 160:
        q_preview = q_preview[:160] + "…"

    logger.debug(
        "ask_file[%s] incoming model=%s stream=%s post_process=%s q_preview=%r",
        rid,
        req.model,
        bool(req.stream),
        bool(req.post_process),
        q_preview,
    )

    model_id = await ensure_model(req.model)
    logger.debug("ask_file[%s] resolved_model=%s", rid, model_id)

    if not HARDCODED_FILE_ID and DEBUG:
        logger.warning(
            "ask_file[%s] HARDCODED_FILE_ID is not set; request may fail", rid
        )

    payload = {
        "model": model_id,
        "stream": bool(req.stream),
        "messages": [{"role": "user", "content": req.question}],
        "files": [{"id": HARDCODED_FILE_ID, "type": "file", "status": "processed"}],
    }
    logger.debug(
            "ask_file[%s] payload prepared with file_id=%r", rid, HARDCODED_FILE_ID
        )

    owui_resp = await post_chat_completions(payload)
    logger.debug(f"~~~ owui_resp: {owui_resp} ~~~")
    logger.debug(
        "ask_file[%s] received OWUI response keys=%s",
        rid,
        (
            list(owui_resp.keys())
            if isinstance(owui_resp, dict)
            else type(owui_resp).__name__
        ),
    )

    # Normalize OWUI output
    normalized_text, sources = normalize_owui_response(owui_resp)
    logger.debug(
        "ask_file[%s] normalized len=%d sources=%d",
        rid,
        len(normalized_text or ""),
        len(sources or []),
    )

    final_text = None
    if req.post_process:
        logger.debug("ask_file[%s] post_process start model=%s", rid, OPENAI_MODEL)
        final_text = await post_process_with_openai(
            text=normalized_text,
            sources=sources,
            user_question=req.question,
        )
        logger.debug(
                "ask_file[%s] post_process done len=%d", rid, len(final_text or "")
            )
    else:
        logger.debug("ask_file[%s] post_process skipped", rid)

    logger.debug("ask_file[%s] done", rid)
    logger.debug(f"This is the normalized_text: {normalized_text}")
    logger.debug(f"This is the final_text: {final_text}")

    return {
        # "raw": owui_resp,
        "normalized_text": normalized_text,
        "sources": sources,
        "final_text": final_text,
        "instructions": (
            "You can use the 'final_text' field as the best answer. "
            "Your response requires source mapping to the Employee Handbook and must include the page number(s) where the information was found. "
            "DO NOT make up content - if you cannot find an answer, state the you cannot find the answer and refer the user to the Employee Handbook, their HRP, or contact hr@greshamsmith.com. "
        ),
    }
