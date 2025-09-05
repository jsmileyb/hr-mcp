# Authentication Module - Central import for all auth functions
"""
Authentication module providing centralized access to all authentication functions.
Import this module to access authentication functionality across the application.
"""

from .service_auth import (
    extract_single_user_email,
    get_service_token, 
    get_cached_service_token, 
    get_current_user_email, 
    make_authenticated_request,
    clear_token_cache
)
from .graph_auth import get_graph_token_async
from .power_automate_auth import call_pa_workflow_async
from .vp_auth import get_vantagepoint_token

__all__ = [
    "get_service_token",
    "get_cached_service_token", 
    "extract_single_user_email",
    "get_current_user_email",
    "make_authenticated_request",
    "clear_token_cache",
    "get_graph_token_async",
    "call_pa_workflow_async",
    "get_vantagepoint_token",
]
