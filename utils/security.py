# Security and token utilities
from typing import Optional


def mask_token(token: str | None, show_last: int = 10) -> str | None:
    """
    Mask sensitive tokens for logging purposes.
    
    Args:
        token: The token to mask
        show_last: Number of characters to show at the end
        
    Returns:
        Masked token string or None if token is None
    """
    if not token:
        return None
    if len(token) <= show_last:
        return "*" * len(token)
    return "*" * (len(token) - show_last) + token[-show_last:]
