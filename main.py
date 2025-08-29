from typing import List, Optional, Tuple, Any
import os, json, logging, sys, uuid

import httpx

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import time
from datetime import datetime, timezone

from utils.config import TOOL_NAME  # keep your import
from auth.vp_auth import get_vantagepoint_token
import re
import xmltodict

load_dotenv()

# =========================
# App & Logging
# =========================
app = FastAPI(
    title="HR Handbook and Policy MCP for GIA",
    version="0.0.1",
    description="MCP Server to retrieve HR policies and employee information.",
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
JWT = os.environ.get("OWUI_JWT")
HARDCODED_FILE_ID = os.environ.get("HARDCODED_FILE_ID")  # optional
OPENAI_API_KEY = os.environ.get(
    "OPENAI_API_KEY"
)  # set this if you want post-processing
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")  # pick your fave
DEBUG = os.environ.get("DEBUG", False)
VP_BASE_URL = os.environ.get("VP_BASE_URL")

PROCEDURE = os.environ.get("VP_SP_GETVACATION")


# Log all relevant environment variables (mask sensitive values)
def mask_token(token: str | None, show_last: int = 10) -> str | None:
    if not token:
        return None
    if len(token) <= show_last:
        return "*" * len(token)
    return "*" * (len(token) - show_last) + token[-show_last:]


env_vars = {
    "GIA_URL": OWUI,
    "OWUI_JWT": mask_token(JWT, 10),
    "HARDCODED_FILE_ID": HARDCODED_FILE_ID,
    "OPENAI_API_KEY": mask_token(OPENAI_API_KEY, 10),
    "OPENAI_MODEL": OPENAI_MODEL,
    "DEBUG": DEBUG,
}
logger.debug("Loaded environment variables:\n%s", json.dumps(env_vars, indent=2))

if not JWT:
    raise RuntimeError("OWUI_JWT is required in the environment.")

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
        headers={"Authorization": f"Bearer {JWT}"},
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
    stream: bool = Field(True, description="Use streamed responses (server-side)")


class AskResp(BaseModel):
    normalized_text: Optional[str] = None
    sources: Optional[list] = None
    instructions: Optional[str] = None


class LeadershipInfo(BaseModel):
    hrp_employee_id: Optional[str] = None
    hrp_name: Optional[str] = None
    hrp_email: Optional[str] = None
    director_id: Optional[str] = None
    director_name: Optional[str] = None
    director_email: Optional[str] = None
    mvp_id: Optional[str] = None
    mvp_name: Optional[str] = None
    mvp_email: Optional[str] = None
    evp_id: Optional[str] = None
    evp_name: Optional[str] = None
    evp_email: Optional[str] = None


class EmploymentSummary(BaseModel):
    employee_id: Optional[str] = None
    display_name: Optional[str] = None
    email: Optional[str] = None
    cll: Optional[str] = None
    market: Optional[str] = None
    department: Optional[str] = None
    nomination_level: Optional[str] = None
    nomination_date: Optional[str] = None
    latest_hire_date: Optional[str] = None
    original_hire_date: Optional[str] = None
    years_with_gresham_smith: Optional[float] = None
    los_years: Optional[float] = None


class EmploymentResp(BaseModel):
    # What we’ll send back from /get-my-leadership (aka ask_employment_details)
    leadership: LeadershipInfo
    summary: EmploymentSummary


class VacationResp(BaseModel):
    employee_id: Optional[str] = None
    starting_balance: Optional[float] = None
    current_balance: Optional[float] = None
    instructions: Optional[str] = None

# =========================
# Helpers
# =========================

async def get_service_token() -> str:
    """
    Exchange the bootstrap JWT for a service/API token via /api/v1/auths/api_key.
    Caches the token. Returns (token, token_type).
    """
    global _service_token, _service_token_type
    if client is None:
        raise RuntimeError("HTTP client not initialized")

    # Your env expects GET here; Accept JSON; client already has Bearer <JWT>
    try:
        r = await client.get("/api/v1/auths/api_key", headers={"Accept": "application/json", "Authorization": f"Bearer {JWT}"})
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


async def ensure_model(model_name: str, key: str) -> str:
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

    # Make sure we have the service token
    await get_service_token()

    desired = MODEL_ALIAS.get(model_name, model_name)
    try:
        r = await client.get("/api/models", headers={"Accept": "application/json", "Authorization": f"Bearer {JWT}"})
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


async def get_current_user_email(key) -> str:
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


async def get_graph_token_async() -> Optional[str]:
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


async def call_pa_workflow_async(payload: dict, token: Optional[str]) -> Optional[dict]:
    logger.debug(f"call_pa_workflow_async payload: {json.dumps(payload, indent=2)} token: {'set' if token else 'unset'}")
    PA_URL = os.environ.get("PA_URL")
    if not PA_URL:
        logger.error("PA_URL not set")
        return None

    headers = {"Content-Type": "application/json"}
    # If your Flow is protected by Entra ID / custom connector, include the bearer:
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(timeout=60) as ac:
            # r = await ac.post(PA_URL, json=payload, headers=headers)
            r = await ac.post(PA_URL, json=payload)
        if r.status_code == 200:
            return r.json()
        logger.error("PA workflow call failed %s: %s", r.status_code, r.text[:400])
        return None
    except httpx.HTTPError as e:
        logger.error("PA workflow call error: %s", e)
        return None


def _years_between(iso_date: Optional[str]) -> Optional[float]:
    if not iso_date:
        return None
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "")).replace(
            tzinfo=timezone.utc
        )
        now = datetime.now(timezone.utc)
        return round((now - dt).days / 365.25, 2)
    except Exception:
        return None


def build_employment_payload(raw: dict) -> EmploymentResp:
    # Pull top-level fields with safe defaults
    market = (raw or {}).get("Market")
    leadership = LeadershipInfo(
        hrp_employee_id=raw.get("hrpEmployeeID"),
        hrp_name=raw.get("hrpName"),
        hrp_email=raw.get("hrpEmail"),
        director_id=raw.get("Director_ID"),
        director_name=raw.get("Director_Name"),
        director_email=raw.get("Director_Email"),
        mvp_id=raw.get("MVP_ID"),
        mvp_name=raw.get("MVP_Name"),
        mvp_email=raw.get("MVP_Email"),
        evp_id=raw.get("EVP_ID"),
        evp_name=raw.get("EVP_Name"),
        evp_email=raw.get("EVP_Email"),
    )

    # If NOT Corporate Services, we care about MVP/EVP; otherwise Director is primary.
    if market and market.strip().lower() != "corporate services":
        # If MVP/EVP missing, keep Director as fallback (already populated)
        pass  # data is already in the model
    else:
        # Corporate Services → Director path (already in model)
        pass

    summary = EmploymentSummary(
        employee_id=raw.get("EmployeeID"),
        display_name=raw.get("DisplayName"),
        email=raw.get("Email"),
        cll=raw.get("CLL"),
        market=market,
        department=raw.get("Department"),
        nomination_level=raw.get("NominationLevel"),
        nomination_date=raw.get("NominationDate"),
        latest_hire_date=raw.get("LatestHireDate"),
        original_hire_date=raw.get("OriginalHireDate"),
        years_with_gresham_smith=raw.get("YearsWithGreshamSmith"),
        los_years=_years_between(raw.get("LatestHireDate")),
    )

    return EmploymentResp(leadership=leadership, summary=summary)


async def get_vacation_days(payload: dict, token: Optional[str]) -> Optional[dict]:
    """
    Get vacation days for a specific employee using the Power Automate API.
    Args:
        email (str): The email address of the employee.
    Returns:
        dict: API response XML.
    Raises:
        requests.HTTPError: If the API call fails.
    """

    access_token = token
    # logger.info(f"[GET Vantagepoint API Token: {access_token}]")

    url = f"{VP_BASE_URL}/api/Utilities/InvokeCustom/{PROCEDURE}"
    
    logger.debug(f"[GET /get_vacation_days] Request URL: {url}")
    logger.debug(f"[GET /get_vacation_days] Payload: {payload}")
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/xml",
        "Content-Type": "application/json"
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
    
    xml = response.text
    # Remove leading/trailing quotes if present
    xml = xml.strip()
    if xml.startswith('"') and xml.endswith('"'):
        xml = xml[1:-1]
    
    # Handle escaped characters - decode them properly
    xml = xml.encode().decode('unicode_escape')
    
    # Remove the schema block
    xml = re.sub(r'<xs:schema.*?</xs:schema>', '', xml, flags=re.DOTALL)
    # Remove empty <Table></Table> elements
    xml = re.sub(r'<Table>\s*</Table>', '', xml, flags=re.DOTALL)
    # Remove any control characters (non-printable)
    xml = re.sub(r'[^\x09\x0A\x0D\x20-\x7E]+', '', xml)
    # Strip leading/trailing whitespace again
    xml = xml.strip()
    
    logger.debug(f"[GET /get_vacation_days] Cleaned XML: {xml[:500]}...")  # Log first 500 chars for brevity
    
    # Parse the XML to dict
    parsed_xml = xmltodict.parse(xml)
    
    # Extract vacation balance data and clean up field names
    try:
        # Navigate to the Table data
        new_dataset = parsed_xml.get('NewDataSet', {})
        table_data = new_dataset.get('Table', {})
        
        # Extract and clean up the vacation data
        vacation_data = {
            "employee_id": table_data.get('Employee'),
            "starting_balance": float(table_data.get('Starting_x0020_Balance', 0)) if table_data.get('Starting_x0020_Balance') else None,
            "current_balance": float(table_data.get('Current_x0020_Balance', 0)) if table_data.get('Current_x0020_Balance') else None
        }
        
        logger.debug(f"Extracted vacation data: {vacation_data}")
        return vacation_data
        
    except Exception as e:
        logger.error(f"Error parsing vacation XML data: {e}")
        logger.debug(f"Parsed XML structure: {parsed_xml}")
        # Return the raw parsed XML as fallback
        return parsed_xml


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


# =========================
# Routes
# =========================
@app.post("/ask-file",response_model=AskResp,summary="Ask HR policy questions using the Employee Handbook")
async def ask_file(req: AskReq = Body(...)):
    """
    Handbook-based HR questions. Use this when the user asks about PTO policy, benefits, time-off rules, or other HR procedures documented in the employee handbook.
    
    Ask HR policy questions against the Employee Handbook via GIA, with optional OpenAI post-processing.

    Returns: 
        A structured response containing the answer to the HR policy question, along with relevant sources from the Employee Handbook.

    Raises: 
        HTTPException if the request fails or if no relevant information is found.

    """
    rid = uuid.uuid4().hex[:8]

    q_preview = (req.question or "").replace("\n", " ")
    if len(q_preview) > 160:
        q_preview = q_preview[:160] + "…"

    logger.debug(
        "ask_file[%s] incoming model=%s stream=%s q_preview=%r",
        rid,
        req.model,
        bool(req.stream),
        q_preview,
    )

    key = await get_service_token()
    model_id = await ensure_model(req.model, key)
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
        f"~~~ payload: {payload} ~~~",
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

    logger.debug("ask_file[%s] done", rid)
    logger.debug(f"This is the normalized_text: {normalized_text}")

    return {
        "normalized_text": normalized_text,
        "sources": sources,
        "instructions": (
            "Your response requires source mapping to the Employee Handbook and must include the page number(s) where the information was found. "
            f"Use {sources} to map page numbers to show employees where to find the information the link to the handbook is: https://gspnet4.sharepoint.com/sites/HR/Shared%20Documents/employee-handbook.pdf. "
            "DO NOT make up content - if you cannot find an answer, state the you cannot find the answer and refer the user to the Employee Handbook, their HRP, or contact hr@greshamsmith.com. "
        ),
    }


@app.post("/get-my-leadership",response_model=EmploymentResp,summary="Get my leadership & employment details")
async def ask_employment_details(req: AskReq = Body(...)):
    """
    Employee-specific leadership details. Use this when the user asks *who* their HRP, Director, MVP/EVP, or CLL is, or requests personal employment details like hire date, employee ID, nomination level/date, or length of service.

    Returns: 
        A structured response containing the employee's leadership details and relevant employment information.

    Raises: 
        HTTPException if the request fails or if no relevant information is found.

    """
    rid = uuid.uuid4().hex[:8]
    logger.debug("ask_employment_details[%s] model=%s", rid, req.model)
    logger.debug(f"{'~' * 25}This is the request: {req}")

    # 1) Get token (if your Flow requires it)
    graph_auth = await get_graph_token_async()
    key = await get_service_token()

    current_user = await get_current_user_email(key)
    email = current_user.get("email")
    payload = {"CompanyEmailAddress": email}
    employee_details = await call_pa_workflow_async(payload, graph_auth)
    if not employee_details:
        raise HTTPException(
            status_code=502, detail="Power Automate workflow returned no data"
        )

    # 3) Build structured, market-aware response
    payload = build_employment_payload(employee_details)
    return payload

@app.post("/get-my-vacation", response_model=VacationResp, summary="Get my vacation details")
async def ask_vacation_details(req: AskReq = Body(...)):
    """
    Employee-specific vacation details. Use this when the user asks about their vacation balance, upcoming time off, or related inquiries.

    Returns: 
        A structured response containing the employee's vacation details and relevant information.
    """
    rid = uuid.uuid4().hex[:8]
    logger.debug("ask_vacation_details[%s] model=%s", rid, req.model)
    logger.debug(f"{'~' * 25}This is the request: {req}")

    graph_auth = await get_graph_token_async()
    key = await get_service_token()

    current_user = await get_current_user_email(key)
    email = current_user.get("email")
    payload = {"CompanyEmailAddress": email}
    employee_details = await call_pa_workflow_async(payload, graph_auth)
    if not employee_details:
        raise HTTPException(
            status_code=502, detail="Power Automate workflow returned no data"
        )
    logger.debug(f"This is the employee details: {employee_details}")
    vp_token_response = await get_vantagepoint_token()
    if not vp_token_response:
        raise HTTPException(
            status_code=502, detail="Vantagepoint API token retrieval failed"
        )
    logger.debug(f"[GET Vantagepoint API Token: {vp_token_response}]")
    body = {
        "EEID": employee_details.get("EmployeeID")
    }
    vacation_details = await get_vacation_days(body, vp_token_response.get("access_token"))

    if not vacation_details:
        raise HTTPException(
            status_code=502, detail="Vantagepoint Stored Procedure returned no data"
        )
    
    linked_call = AskReq(
        question=f"What is my PTO accrual rate for {employee_details.get('YearsWithGreshamSmith')} and {employee_details.get('CLL')}",
        model=req.model,
        stream=True
    )
    
    return {
        "employee_id": vacation_details.get("employee_id"),
        "starting_balance": vacation_details.get("starting_balance"),
        "current_balance": vacation_details.get("current_balance"),
        "instructions": (
            "The return values are in hours - show the results in hours and days. Our standard work day is 8 hours. "
            "If no vacation balance is found, refer the user to their HRP or manager - do not offer to refer to the servicedesk@greshamsmith.com."
            f"Refer to the \"/ask-file\" endpoint for a breakdown on accrual details for individual employees using a company tenure using: {linked_call} "
            )
    }

