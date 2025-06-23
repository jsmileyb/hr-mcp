# app/config.py

import os
from dotenv import load_dotenv

# Load .env once at startup
load_dotenv()

# Access values globally
TOOL_NAME = os.getenv("TOOL_NAME", "UNASSIGNED_TOOL_NAME")