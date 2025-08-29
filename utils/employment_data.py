# Data transformation utilities for employment and HR data
from typing import Optional
from pydantic import BaseModel, Field
from utils.datetime_utils import years_between


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
    # What we'll send back from /get-my-leadership (aka ask_employment_details)
    leadership: LeadershipInfo
    summary: EmploymentSummary


def build_employment_payload(raw: dict) -> EmploymentResp:
    """
    Build structured employment response from raw employee data.
    
    Args:
        raw: Raw employee data dictionary
        
    Returns:
        EmploymentResp: Structured employment response
    """
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
        los_years=years_between(raw.get("LatestHireDate")),
    )

    return EmploymentResp(leadership=leadership, summary=summary)
