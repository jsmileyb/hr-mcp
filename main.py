from typing import Optional
import os, json, logging, sys, uuid, math, time

import httpx
import asyncio
import re

from fastapi import FastAPI, HTTPException, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
import time

from utils.config import TOOL_NAME
from utils.environment import (
    log_environment_config, 
    validate_required_env,
    get_owui_url,
    get_owui_jwt,
    get_openai_model,
    get_hardcoded_handbook_file_id,
    get_hardcoded_state_file_id,
    get_debug_mode
)
from utils.api_models import AskReq, AskResp
from utils.employment_data import EmploymentResp, build_employment_payload
from utils.vacation_data import VacationResp
from utils.http_client import ensure_model, post_chat_completions, post_chat_completions_stream
from utils.response_processor import normalize_owui_response
from utils.client_registry import client_registry
from auth import (
    get_cached_service_token,
    get_current_user_email,
    get_graph_token_async,
    call_pa_workflow_async,
    get_vantagepoint_token
)
from utils.vantagepoint import get_vacation_days
from utils.accrual_parser import get_accrual
from utils.page_index import find_pto_pages

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

# Add timing middleware for performance debugging
@app.middleware("http")
async def log_request_timing(request: Request, call_next):
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"
    
    logger.info(f"🚀 Request started: {request.method} {request.url.path} from {client_ip}")
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    logger.info(f"✅ Request completed: {request.method} {request.url.path} - {process_time:.2f}s from {client_ip}")
    
    # Add timing header for debugging
    response.headers["X-Process-Time"] = str(process_time)
    return response

logging.basicConfig(
    level=logging.DEBUG if get_debug_mode() else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(TOOL_NAME)

# =========================
# Config / HTTP client
# =========================
OWUI = get_owui_url()
JWT = get_owui_jwt()
HARDCODED_HANBOOK_FILE_ID = get_hardcoded_handbook_file_id()
HARDCODED_STATE_FILE_ID = get_hardcoded_state_file_id()
MODEL_USED = get_openai_model()

# Optional: map your requested model name to an OWUI-registered model id.
# Example: MODEL_ALIAS_JSON='{"gpt-5":"gpt-5o"}'
MODEL_ALIAS = {"gpt-5": "gpt-5"}  # or "gpt-5o" if that's the registered ID

# Shared async client (init on startup)
client: httpx.AsyncClient | None = None

# Log environment configuration
log_environment_config(logger)

# Validate required environment variables
validate_required_env()


@app.on_event("startup")
async def _startup():
    global client
    client = httpx.AsyncClient(
        base_url=OWUI,
        headers={"Accept": "application/json"},
        # timeout=httpx.Timeout(connect=5, read=30, write=30, pool=30),
        timeout=httpx.Timeout(connect=10, read=60, write=60, pool=60),
        limits=httpx.Limits(max_keepalive_connections=32, max_connections=128),
        http2=True, 
    )
    
    # Register the main GIA client in the registry
    client_registry.set_gia_client(client)
    
    logger.info("HTTP client initialized for GIA at %s", OWUI)


@app.on_event("shutdown")
async def _shutdown():
    global client
    if client:
        await client.aclose()
        logger.info("HTTP client closed")
    
    # Close all registered clients
    await client_registry.close_all()
    logger.info("All shared clients closed")


# =========================
# Routes
# =========================
ENRICH_CACHE: dict[str, dict] = {}
MAX_CACHE = 200
ENRICH_TTL_SECS = 900  # 15 minutes

def _prune_cache():
    now = time.time()
    for k in list(ENRICH_CACHE.keys()):
        if now - ENRICH_CACHE[k].get('ts', now) > ENRICH_TTL_SECS:
            ENRICH_CACHE.pop(k, None)
    # size cap
    if len(ENRICH_CACHE) > MAX_CACHE:
        # drop oldest
        oldest = sorted(ENRICH_CACHE.items(), key=lambda x: x[1].get('ts', 0))[: len(ENRICH_CACHE)-MAX_CACHE]
        for k,_ in oldest:
            ENRICH_CACHE.pop(k, None)

async def _enrich_accrual_answer(rid: str, req_question: str, model_id: str, accrual_data, pto_pages):
    """Background task that calls OWUI for narrative + citations and stores result in cache."""
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": (
                "Provide a concise PTO accrual explanation with explicit page number references. "
                "You are given the user question; respond using handbook sources."
            )},
            {"role": "user", "content": req_question}
        ],
        "files": [{"id": "0312fc8a-9c2c-448f-accd-a9bb6c375488", "type": "file"}],
    }
    try:
        owui_resp = await post_chat_completions(client, payload, JWT)
        text, sources = normalize_owui_response(owui_resp)
        if text:
            # inject local pages if missing
            if pto_pages and all('pages' not in s for s in sources or []):
                sources = (sources or []) + [{"title": "Employee Handbook PTO Section", "pages": pto_pages, "type": "local"}]
            ENRICH_CACHE[rid] = {"type": "accrual_enrichment", "text": text, "sources": sources, "ts": time.time()}
        else:
            ENRICH_CACHE[rid] = {"type": "accrual_enrichment", "error": "empty_response", "ts": time.time()}
    except Exception as e:
        ENRICH_CACHE[rid] = {"type": "accrual_enrichment", "error": str(e), "ts": time.time()}
    finally:
        _prune_cache()

@app.post("/ask-file", summary="Ask HR policy questions using the Employee Handbook")
async def ask_file(req: AskReq = Body(...)):
    """
    Handbook-based HR questions. Use this when the user asks about PTO accrual rates (PTO Benefit Accrual), benefits, time-off rules, or other HR procedures documented in the employee handbook.
    
    Ask HR policy questions against the Employee Handbook via GIA, with optional OpenAI post-processing.

    Returns: 
        - If stream=True: Server-Sent Events (SSE) streaming response
        - If stream=False: Structured JSON response containing the answer with sources

    Raises: 
        HTTPException if the request fails or if no relevant information is found.

    """
    rid = uuid.uuid4().hex[:8]

    q_preview = (req.question or "").replace("\n", " ")
    if len(q_preview) > 160:
        q_preview = q_preview[:160] + "…"


    model_id = MODEL_USED
    logger.debug("ask_file[%s] resolved_model=%s", rid, model_id)

    if not HARDCODED_HANBOOK_FILE_ID and get_debug_mode():
        logger.warning(
            "ask_file[%s] HARDCODED_HANBOOK_FILE_ID is not set; request may fail", rid
        )

    # Detect PTO accrual style question early
    lower_q = (req.question or '').lower()
    is_accrual_query = any(k in lower_q for k in ["accrual", "pto", "vacation rate", "benefit accrual"]) and "rate" in lower_q

    # Attempt to extract years and CLL tokens (simple heuristics)
    # More robust: capture floats then floor
    years_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:years|year|yrs?)", lower_q)
    years_val = math.floor(float(years_match.group(1))) if years_match else 0
    cll_match = re.search(r"\b([A-Z]{1,2}\d)\b", req.question or '')  # e.g. P5, TP7
    cll_val = cll_match.group(1).upper() if cll_match else None

    accrual_data = None
    pto_pages = []
    if is_accrual_query:
        try:
            handbook_md_path = os.path.join(os.getcwd(), '.source', 'marker', 'employee-handbook-markdown', 'employee-handbook.md')
            if os.path.exists(handbook_md_path):
                accrual_data = get_accrual(handbook_md_path, years_val, cll_val)
                # Extract known PTO related page numbers locally so we always have page refs
                pto_pages = find_pto_pages(handbook_md_path)
        except Exception as e:
            logger.warning("ask_file[%s] local accrual parse failed: %s", rid, e)

    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": req.question}],
        "files": [{"id": "041f9216-9099-4369-ab67-2adc418ae981", "type": "file"}],
    }
    logger.debug(f"ask_file[{rid}] payload_prepared")

    async def call_owui():
        return await post_chat_completions(client, payload, JWT)

    # Add overall timeout for legacy (non-accrual) path
    OWUI_TIMEOUT = 45  # seconds - adjust as needed

    # Local-first fast return for accrual queries when not streaming
    if is_accrual_query and not req.stream and accrual_data:
        # Build immediate answer from local data
        res = accrual_data['result']
        annual = int(res.get('annual_hours')) if res.get('annual_hours') is not None else None
        hpp = res.get('hours_per_pay_period')
        base_text = (
            f"PTO Accrual Rate (local) for CLL {cll_val or 'N/A'} and {years_val} years: "
            f"{annual} hours annually (rounded down) ≈ {hpp} hours per pay period (24 pay periods)."
        )
        pages_line = f"Handbook page(s): {', '.join(map(str, pto_pages))}." if pto_pages else ''
        immediate_text = base_text + ("\n" + pages_line if pages_line else '')
        # schedule enrichment
        asyncio.create_task(_enrich_accrual_answer(rid, req.question, model_id, accrual_data, pto_pages))
        return {
            'request_id': rid,
            'normalized_text': immediate_text,
            'sources': ([{"title": "Employee Handbook PTO Section", "pages": pto_pages, "type": "local"}] if pto_pages else []),
            'instructions': 'Background enrichment scheduled; poll /ask-file-result/{request_id} for enriched narrative with citations.',
            'accrual_data': {**accrual_data, 'pages': pto_pages},
            'enrichment_pending': True,
            'owui_timeout': False,
            'latency_seconds': 0.0,
        }

    if req.stream:
        # For streaming, we currently do not inject structured accrual fallback mid-stream; could be extended.
        async def generate_stream():
            # Prepend guidance chunk if accrual query and local data present
            if accrual_data:
                intro = {"type": "local_accrual", "data": accrual_data}
                yield f"data: {json.dumps(intro)}\n\n"
            stream_payload = {
                "model": model_id,
                "messages": [
                    {"role": "system", "content": (
                        "Your response requires source mapping to the Employee Handbook and State Appendix - ALL RESPONSES must include the page number(s) where the information was found. "
                        "For PTO accrual rates (PTO Benefit Accrual), you MUST include both the Career Ladder Level (CLL) and the years of service, and ROUND DOWN to the nearest whole number of hours. "
                        "Use the sources provided to map page numbers and document sections to show employees where to find the information. "
                        "The link to the EMPLOYEE HANDBOOK is: https://gspnet4.sharepoint.com/sites/HR/Shared%20Documents/employee-handbook.pdf. "
                        "The link to the STATE APPENDIX is: https://gspnet4.sharepoint.com/sites/HR/Shared%20Documents/State-Appendix.pdf. "
                        "When providing accrual information, reference the specific table data from the sources and include details about Career Ladder Levels (P7-P9, TP7-TP9, OR7-OR9, M1-M4, A5-A6, I5-I6, T7-T8 get 200 hours; P5-P6, TP5-TP6, OR5-OR6, T6, I4, A4 start at 164.45 hours; all others follow the years-of-service table). "
                        "DO NOT make up content - if you cannot find an answer, state that you cannot find the answer and refer the user to the Employee Handbook, the State Appendix, their HRP, or contact hr@greshamsmith.com."
                    )},
                    {"role": "user", "content": req.question}
                ],
                "files": [{"id": "041f9216-9099-4369-ab67-2adc418ae981", "type": "file"}],
            }
            async for chunk in post_chat_completions_stream(client, stream_payload, JWT):
                yield chunk
        return StreamingResponse(generate_stream(), media_type="text/event-stream", headers={"Cache-Control":"no-cache","Connection":"keep-alive","X-Accel-Buffering":"no"})

    # Non-streaming path
    start = time.time()
    try:
        owui_resp = await asyncio.wait_for(call_owui(), timeout=OWUI_TIMEOUT)
        elapsed = time.time() - start
        logger.debug(f"ask_file[{rid}] OWUI elapsed={elapsed:.2f}s")
    except asyncio.TimeoutError:
        owui_resp = {"timeout": True}
        logger.warning("ask_file[%s] OWUI call timed out after %ss", rid, OWUI_TIMEOUT)

    normalized_text, sources = normalize_owui_response(owui_resp) if not owui_resp.get('timeout') else (None, [])

    # If this was an accrual query and OWUI failed to produce sources or text, build a synthesized answer
    synthesized = None
    if is_accrual_query and accrual_data and (not normalized_text or not sources):
        res = accrual_data['result']
        annual = res.get('annual_hours')
        hpp = res.get('hours_per_pay_period')
        if annual:
            synthesized = (
                f"PTO accrual (fallback local parse) for {years_val} years and CLL {cll_val or 'N/A'}: "
                f"annual {int(annual)} hours (rounded down) ≈ {hpp} hours per pay period (24 pay periods). "
                "Source: Employee Handbook PTO accrual table (local parsed)."
            )
            normalized_text = (normalized_text + "\n\n" + synthesized) if normalized_text else synthesized

    # If no sources but we have local page numbers, fabricate a minimal local source entry
    if is_accrual_query and pto_pages:
        local_source = {
            "title": "Employee Handbook PTO Section",
            "pages": pto_pages,
            "type": "local",
            "note": "Local parsed page references (handbook markdown)."
        }
        if not sources:
            sources = [local_source]
        elif all('pages' not in s for s in sources):
            # Append if existing sources lack explicit page data
            sources.append(local_source)

    # Remove stale disclaimer if present and inject page refs line
    if is_accrual_query and pto_pages and normalized_text:
        disclaimer_pattern = re.compile(r"I couldn[’']t retrieve the exact Employee Handbook page to cite just now[^\n]*", re.IGNORECASE)
        normalized_text = disclaimer_pattern.sub('', normalized_text).strip()
        pages_line = f"Handbook page(s): {', '.join(map(str, pto_pages))}."
        if pages_line not in normalized_text:
            normalized_text += ("\n\n" + pages_line)

    response_payload = {
        'normalized_text': normalized_text,
        'sources': sources,
        'instructions': (
            "Your response requires source mapping to the Employee Handbook and State Appendix and must include the page number(s) where the information was found. "
            "For PTO accrual rates (PTO Benefit Accrual), you MUST include both the Career Ladder Level (CLL) and the years of service, and ROUND DOWN to the nearest whole number of hours. "
            "The link to the EMPLOYEE HANDBOOK is: https://gspnet4.sharepoint.com/sites/HR/Shared%20Documents/employee-handbook.pdf. "
            "The link to the STATE APPENDIX is: https://gspnet4.sharepoint.com/sites/HR/Shared%20Documents/State-Appendix.pdf. "
            "When providing accrual information, reference the specific table data from the sources and include details about Career Ladder Levels (P7-P9, TP7-TP9, OR7-OR9, M1-M4, A5-A6, I5-I6, T7-T8 get 200 hours; P5-P6, TP5-TP6, OR5-OR6, T6, I4, A4 start at 164.45 hours; all others follow the years-of-service table). "
            "DO NOT make up content - if you cannot find an answer, state that you cannot find the answer and refer the user to the Employee Handbook, the State Appendix, their HRP, or contact hr@greshamsmith.com."
        ),
        'accrual_data': ({**accrual_data, 'pages': pto_pages} if (is_accrual_query and accrual_data) else None),
        'request_id': rid,
        'enrichment_pending': False,
        'owui_timeout': bool(owui_resp.get('timeout')),
        'latency_seconds': round(time.time() - start, 2),
    }

    return response_payload


@app.post("/get-my-leadership", response_model=EmploymentResp, summary="Get my leadership & employment details")
async def ask_employment_details(req: AskReq = Body(...)):
    """
    Employee-specific leadership details. Use this when the user asks *who* their HRP, Director, MVP/EVP, or CLL is, or requests personal employment details like hire date, employee ID, nomination level/date, or length of service.
    CLL value is required when asking about PTO/vacation accrual rates (PTO Benefit Accrual).

    Returns: 
        A structured response containing the employee's leadership details and relevant employment information.

    Raises: 
        HTTPException if the request fails or if no relevant information is found.

    """
    rid = uuid.uuid4().hex[:8]
    logger.debug("ask_employment_details[%s] model=%s", rid, req.model)

    # 1) Get token (if your Flow requires it)
    graph_auth = await get_graph_token_async()

    current_user = await get_current_user_email(client, JWT)
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

@app.get('/ask-file-result/{request_id}')
async def get_enriched_result(request_id: str):
    _prune_cache()
    data = ENRICH_CACHE.get(request_id)
    if not data:
        return {"request_id": request_id, "status": "pending"}
    return {"request_id": request_id, "status": "ready", **data}


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

    # 1) Fetch Graph token and OWUI service token concurrently
    graph_auth_coro = get_graph_token_async()
    service_token_coro = get_cached_service_token(client, JWT)
    graph_auth, service_token = await asyncio.gather(graph_auth_coro, service_token_coro)

    if not graph_auth:
        raise HTTPException(status_code=502, detail="Failed to acquire Microsoft Graph token")
    if not service_token:
        raise HTTPException(status_code=502, detail="Failed to acquire service token from GIA/OWUI")

    # 2) Resolve current user with the service token
    current_user = await get_current_user_email(client, JWT)
    email = (current_user or {}).get("email")
    if not email:
        raise HTTPException(status_code=502, detail="Could not resolve current user email from GIA/OWUI")

    # 3) Kick off PA workflow and VP token retrieval in parallel
    pa_coro = call_pa_workflow_async({"CompanyEmailAddress": email}, graph_auth)
    vp_token_coro = get_vantagepoint_token()
    employee_details, vp_token_response = await asyncio.gather(pa_coro, vp_token_coro)

    if not employee_details:
        raise HTTPException(status_code=502, detail="Power Automate workflow returned no data")
    if not vp_token_response or not vp_token_response.get("access_token"):
        raise HTTPException(status_code=502, detail="Vantagepoint API token retrieval failed")

    # 4) Vantagepoint PTO call
    body = {"EEID": employee_details.get("EmployeeID")}
    vacation_details = await get_vacation_days(body, vp_token_response.get("access_token"))
    if not vacation_details:
        raise HTTPException(status_code=502, detail="Vantagepoint Stored Procedure returned no data")

    # NOTE: Previously we embedded an executable AskReq (linked_call) in instructions. Autonomous agents
    # sometimes executed it automatically, causing duplicate /ask-file calls and adding 45-90s latency.
    # We now provide a plain-text example only. Do NOT auto-call /ask-file unless the user explicitly asks.
    example_question = (
        f"Example (do not auto-call): What is my PTO accrual rate for {employee_details.get('YearsWithGreshamSmith')} years and CLL {employee_details.get('CLL')}?"
    )

    return {
        "employee_id": vacation_details.get("employee_id"),
        "starting_balance": vacation_details.get("starting_balance"),
        "current_balance": vacation_details.get("current_balance"),
        "instructions": (
            "The return values are in hours - show the results in hours and days (8 hours = 1 day). "
            "If no vacation balance is found, refer the user to their HRP or manager (not the service desk). "
            "If the user then requests details on how accrual is calculated, you may call /ask-file once with a fully specified question including their years of service and CLL. "
            + example_question
        ),
    }
