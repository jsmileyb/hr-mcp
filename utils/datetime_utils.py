# Date and time utilities
from typing import Optional
from datetime import datetime, timezone


def years_between(iso_date: Optional[str]) -> Optional[float]:
    """
    Calculate years between an ISO date string and now.
    
    Args:
        iso_date: ISO format date string
        
    Returns:
        Number of years as float, or None if date is invalid
    """
    if not iso_date:
        return None
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "")).replace(
            tzinfo=timezone.utc
        )
        now = datetime.now(timezone.utc)
        return round((now - dt).days / 365.25, 2)
    except Exception:
        return None
