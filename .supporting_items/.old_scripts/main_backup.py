from typing import Optional
import os, json, logging, sys, uuid

import httpx

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from utils.config import TOOL_NAME
from utils.environment import (
    get_environment_config, 
    log_environment_config, 
    validate_required_env,
    get_owui_url,
    get_owui_jwt,
    get_hardcoded_file_id,
    get_debug_mode
)
from utils.api_models import AskReq, AskResp
from utils.employment_data import EmploymentResp, build_employment_payload
from utils.vacation_data import VacationResp
from utils.http_client import ensure_model, post_chat_completions
from utils.response_processor import normalize_owui_response
from auth import (
    get_service_token,
    get_current_user_email,
    get_graph_token_async,
    call_pa_workflow_async,
    get_vantagepoint_token
)
from utils.vantagepoint import get_vacation_days

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
HARDCODED_FILE_ID = get_hardcoded_file_id()
# Log environment configuration
log_environment_config(logger)

# Validate required environment variables
validate_required_env()

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

    key = await get_service_token(client, JWT)
    model_id = await ensure_model(client, req.model, JWT, MODEL_ALIAS)
    logger.debug("ask_file[%s] resolved_model=%s", rid, model_id)

    if not HARDCODED_FILE_ID and get_debug_mode():
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

    owui_resp = await post_chat_completions(client, payload)
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
    key = await get_service_token(client, JWT)

    current_user = await get_current_user_email(client, key)
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
    key = await get_service_token(client, JWT)

    current_user = await get_current_user_email(client, key)
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

