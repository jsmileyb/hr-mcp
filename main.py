from typing import List
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel, Field
from utils.config import TOOL_NAME
import logging
import sys

app = FastAPI(
    title="LONG TITLE FOR YOUR TOOL GOES HERE",
    version="0.0.1",
    description="ADD A LONG DESCRIPTION OF YOUR TOOL HERE",
)


origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(TOOL_NAME)   

# -------------------------------
# Pydantic models
# -------------------------------


# -------------------------------
# Routes
# -------------------------------