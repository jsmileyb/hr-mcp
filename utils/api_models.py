# Pydantic models for API requests and responses
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class AskReq(BaseModel):
    question: str = Field(..., description="User question")
    model: str = Field(
        "gpt-5", description="Model id as registered in GIA (/api/models)"
    )
    stream: bool = Field(False, description="Use streamed responses (server-side)")


class AskResp(BaseModel):
    normalized_text: Optional[str] = None
    sources: Optional[List[dict]] = None  # Updated to be more specific about sources structure
    instructions: Optional[str] = None
    accrual_data: Optional[Dict[str, Any]] = None  # Structured fallback for PTO accrual lookups
