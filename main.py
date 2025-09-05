import logging, sys, uuid

import httpx
import asyncio

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
## StreamingResponse removed (streaming feature deprecated)
from dotenv import load_dotenv

from utils.environment import (
    log_environment_config, 
    validate_required_env,
    get_tool_name,
    get_owui_url,
    get_owui_jwt,
    get_hardcoded_file_id,
    get_debug_mode
)
from utils.api_models import AskReq
from utils.employment_data import EmploymentResp, build_employment_payload
from utils.vacation_data import VacationResp
from utils.client_registry import client_registry
from auth import (
    get_cached_service_token,
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
logger = logging.getLogger(get_tool_name())

def _ensure_logger():
    """Guarantee logger has a handler and correct level (uvicorn may override)."""
    desired_level = logging.DEBUG if get_debug_mode() else logging.INFO
    logger.setLevel(desired_level)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logger.addHandler(h)
    logger.propagate = False  # avoid duplicate root emission

_ensure_logger()

# =========================
# Config / HTTP client
# =========================
OWUI = get_owui_url()
JWT = get_owui_jwt()
HARDCODED_FILE_ID = get_hardcoded_file_id()

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
    key = await get_cached_service_token(client, JWT)

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


@app.post("/get-my-vacation", response_model=VacationResp, summary="Get my vacation details")
async def ask_vacation_details(req: AskReq = Body(...)):
    """
    Employee-specific vacation details. Use this when the user asks about their vacation balance, upcoming time off, or related inquiries.
    CLL value is required when asking about specific PTO/vacation accrual rates (PTO Benefit Accrual).
    
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

    return {
        "employee_id": vacation_details.get("employee_id"),
        "starting_balance": vacation_details.get("starting_balance"),
        "current_balance": vacation_details.get("current_balance"),
        "instructions": (
            "The return values are in hours - show the results in hours and days. Our standard work day is 8 hours. "
            "If no vacation balance is found, refer the user to their HRP or manager - do not offer to refer to the servicedesk@greshamsmith.com."
            f"Refer to the \"employee-handbook.md\" file for a breakdown on accrual details for individual employees using a company tenure. "
        ),
    }
