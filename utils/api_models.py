# Pydantic models for API requests and responses
from typing import Optional, List
from pydantic import BaseModel, Field


class AskReq(BaseModel):
    question: str = Field(..., description="User question")
    model: str = Field(
        "gpt-5", description="Model id as registered in GIA (/api/models)"
    )  
