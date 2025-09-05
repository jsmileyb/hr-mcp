# Data transformation utilities for employment and HR data
from typing import Optional
from pydantic import BaseModel
from utils.datetime_utils import years_between
from datetime import datetime



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

    model_config = {
        "exclude_none": True,
        "orm_mode": True,
    }



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

    model_config = {
        "exclude_none": True,
        "orm_mode": True,
    }



class EmploymentResp(BaseModel):
    """
    Response model for /get-my-leadership (ask_employment_details)
    """
    leadership: LeadershipInfo
    summary: EmploymentSummary

    model_config = {
        "exclude_none": True,
        "orm_mode": True,
    }



def build_employment_payload(raw: dict) -> EmploymentResp:
    """
    Build structured employment response from raw employee data.
    """
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

    # Format nomination_date as MM/dd/yyyy or spell out the date if possible
    def format_date(date_str):
        if not date_str:
            return None
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.strftime("%m/%d/%Y")
        except ValueError:
            try:
                dt = datetime.fromisoformat(date_str)
                return dt.strftime("%m/%d/%Y")
            except Exception:
                return date_str

    summary = EmploymentSummary(
        employee_id=raw.get("EmployeeID"),
        display_name=raw.get("DisplayName"),
        email=raw.get("Email"),
        cll=raw.get("CLL"),
        market=market,
        department=raw.get("Department"),
        nomination_level=raw.get("NominationLevel"),
        nomination_date=format_date(raw.get("NominationDate")),
        latest_hire_date=format_date(raw.get("LatestHireDate")),
        original_hire_date=format_date(raw.get("OriginalHireDate")),
        years_with_gresham_smith=raw.get("YearsWithGreshamSmith"),
        los_years=years_between(raw.get("LatestHireDate")),
    )

    return EmploymentResp(leadership=leadership, summary=summary)
