# Environment configuration and logging utilities
import os
import json
import logging
from typing import Dict, Any
from dotenv import load_dotenv
from utils.security import mask_token

load_dotenv()


def get_environment_config() -> Dict[str, Any]:
    """
    Load and return environment configuration with masked sensitive values for logging.
    
    Returns:
        Dict containing environment configuration
    """
    return {
        "GIA_URL": os.environ.get("GIA_URL", "http://localhost:8080"),
        "OWUI_JWT": mask_token(os.environ.get("OWUI_JWT"), 10),
        "HARDCODED_FILE_ID": os.environ.get("HARDCODED_FILE_ID"),
        "OPENAI_API_KEY": mask_token(os.environ.get("OPENAI_API_KEY"), 10),
        "OPENAI_MODEL": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "DEBUG": os.environ.get("DEBUG", False),
        "VP_BASE_URL": os.environ.get("VP_BASE_URL"),
        "VP_SP_GETVACATION": os.environ.get("VP_SP_GETVACATION"),
    }


def log_environment_config(logger: logging.Logger) -> None:
    """
    Log environment configuration with masked sensitive values.
    
    Args:
        logger: Logger instance to use for logging
    """
    env_vars = get_environment_config()
    logger.debug("Loaded environment variables:\n%s", json.dumps(env_vars, indent=2))


def validate_required_env() -> None:
    """
    Validate that required environment variables are set.
    
    Raises:
        RuntimeError: If required environment variables are missing
    """
    jwt = os.environ.get("OWUI_JWT")
    if not jwt:
        raise RuntimeError("OWUI_JWT is required in the environment.")


# Environment variable getters
def get_tool_name() -> str:
    return os.environ.get("TOOL_NAME", "GIA:HR POLICY")

def get_owui_url() -> str:
    return os.environ.get("GIA_URL", "http://localhost:8080")


def get_owui_jwt() -> str:
    return os.environ.get("OWUI_JWT", "")


def get_hardcoded_file_id() -> str:
    return os.environ.get("HARDCODED_FILE_ID", "")


def get_openai_model() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def get_openai_api_key() -> str:
    return os.environ.get("OPENAI_API_KEY", "")


def get_openai_model() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def get_debug_mode() -> bool:
    return bool(os.environ.get("DEBUG", True))


def get_vp_base_url() -> str:
    return os.environ.get("VP_BASE_URL", "")


def get_vp_procedure() -> str:
    return os.environ.get("VP_SP_GETVACATION", "")
