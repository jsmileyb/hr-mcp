# log_body_filter.py
from typing import Optional
from pydantic import BaseModel, Field
import logging
import json

LOGGER_NAME = "owui.filter.log_body"

def _setup_logger(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger

class Filter:
    class Valves(BaseModel):
        LOG_LEVEL: str = Field(default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)")

    def __init__(self):
        self.valves = self.Valves()
        self.logger = _setup_logger(self.valves.LOG_LEVEL)

    # Minimal requirement: just log the request body we receive
    def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__=None,  # kept for compatibility; not used
    ) -> dict:
        try:
            self.logger.info("INLET body: %s", json.dumps(body, ensure_ascii=False))
        except Exception as e:
            # Fallback so logging never breaks the pipeline
            self.logger.warning("Failed to JSON-serialize inlet body (%s); raw=%r", e, body)
        return body

    # Optional: log post-LLM body too. Safe no-op otherwise.
    def outlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__=None,
    ) -> dict:
        try:
            self.logger.debug("OUTLET body: %s", json.dumps(body, ensure_ascii=False))
        except Exception as e:
            self.logger.warning("Failed to JSON-serialize outlet body (%s); raw=%r", e, body)
        return body

    # (Optional) If you enable streaming on your model, you can peek at chunks as they pass:
    # def stream(self, event: dict) -> dict:
    #     self.logger.debug("STREAM event keys: %s", list(event.keys()))
    #     return event
