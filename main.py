
import logging
import sys
import uuid
import asyncio
import httpx
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from utils.environment import (
    log_environment_config, validate_required_env, get_tool_name, get_owui_url, get_openai_api_key, get_hardcoded_file_id, get_debug_mode
)
from utils.api_models import AskReq
from utils.employment_data import EmploymentResp, build_employment_payload
from utils.vacation_data import VacationResp
from auth import (
    get_cached_service_token, extract_single_user_email, get_current_user_email, get_graph_token_async, call_pa_workflow_async, get_vantagepoint_token
)
from utils.vantagepoint import get_vacation_days

load_dotenv()


# --- App & Logging ---
app = FastAPI(
    title="HR Handbook and Policy MCP for GIA",
    version="0.0.1",
    description="MCP Server to retrieve HR policies and employee information."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.DEBUG if get_debug_mode() else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(get_tool_name())

def _ensure_logger():
    desired_level = logging.DEBUG if get_debug_mode() else logging.INFO
    logger.setLevel(desired_level)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logger.addHandler(h)
    logger.propagate = False

_ensure_logger()


# --- Config / HTTP client ---

OWUI = get_owui_url()
OWUI_KEY = get_openai_api_key()
HARDCODED_FILE_ID = get_hardcoded_file_id()
client: httpx.AsyncClient | None = None
log_environment_config(logger)
validate_required_env()



@app.on_event("startup")
async def _startup():
    global client
    client = httpx.AsyncClient(
        base_url=OWUI,
        headers={"Accept": "application/json"},
        timeout=httpx.Timeout(connect=10, read=60, write=60, pool=60),
        limits=httpx.Limits(max_keepalive_connections=32, max_connections=128),
        http2=True,
    )
    logger.info("HTTP client initialized for GIA at %s", OWUI)

@app.on_event("shutdown")
async def _shutdown():
    global client
    if client:
        await client.aclose()
        logger.info("HTTP client closed")
    logger.info("All shared clients closed")



# --- Routes ---

@app.post("/get-my-leadership", response_model=EmploymentResp, response_model_exclude_none=True, summary="Get my leadership & employment details")
async def ask_employment_details(req: AskReq = Body(...)):
    """
    Returns structured leadership and employment details for the current user.
    """
    rid = uuid.uuid4().hex[:8]
    logger.debug("ask_employment_details[%s] model=%s", rid, req.model)
    graph_auth = await get_graph_token_async()
    current_user = await get_current_user_email(req.user_email, client)
    email = extract_single_user_email(current_user)
    employee_details = await call_pa_workflow_async({"CompanyEmailAddress": email}, graph_auth)
    if not employee_details:
        raise HTTPException(status_code=502, detail="Power Automate workflow returned no data")
    return build_employment_payload(employee_details)


@app.post("/get-my-vacation", response_model=VacationResp, response_model_exclude_none=True, summary="Get my vacation details")
async def ask_vacation_details(req: AskReq = Body(...)):
    """
    Returns structured vacation details for the current user.
    """
    rid = uuid.uuid4().hex[:8]
    logger.debug("ask_vacation_details[%s] model=%s", rid, req.model)
    logger.debug(f"{'~' * 25}This is the request: {req}")
    graph_auth_coro = get_graph_token_async()
    graph_auth = await graph_auth_coro
    if not graph_auth:
        raise HTTPException(status_code=502, detail="Failed to acquire Microsoft Graph token")
    current_user = await get_current_user_email(req.user_email, client)
    email = extract_single_user_email(current_user)
    pa_coro = call_pa_workflow_async({"CompanyEmailAddress": email}, graph_auth)
    vp_token_coro = get_vantagepoint_token()
    employee_details, vp_token_response = await asyncio.gather(pa_coro, vp_token_coro)
    if not employee_details:
        raise HTTPException(status_code=502, detail="Power Automate workflow returned no data")
    if not vp_token_response or not vp_token_response.get("access_token"):
        raise HTTPException(status_code=502, detail="Vantagepoint API token retrieval failed")
    body = {"EEID": employee_details.get("EmployeeID")}
    vacation_details = await get_vacation_days(body, vp_token_response.get("access_token"))
    if not vacation_details:
        raise HTTPException(status_code=502, detail="Vantagepoint Stored Procedure returned no data")
    return {
        "employee_id": vacation_details.get("employee_id"),
        "starting_balance": vacation_details.get("starting_balance"),
        "current_balance": vacation_details.get("current_balance"),
        "instructions": (
            "The return values are in hours - show the results in hours and days. Our standard work day is 8 hours. "
            "If no vacation balance is found, refer the user to their HRP or manager - do not offer to refer to the servicedesk@greshamsmith.com. "
            "Refer to the 'employee-handbook.md' file for a breakdown on accrual details for individual employees using a company tenure. "
        ),
    }
