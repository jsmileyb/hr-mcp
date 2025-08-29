# Vacation data models and utilities
from typing import Optional
from pydantic import BaseModel


class VacationResp(BaseModel):
    employee_id: Optional[str] = None
    starting_balance: Optional[float] = None
    current_balance: Optional[float] = None
    instructions: Optional[str] = None
