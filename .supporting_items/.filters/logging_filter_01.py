"""
GIA HR Assistant Thinking Indicator (Expanded Tracks)
Author: Smiley Baltz
Version: 0.0.3
Description: Playful HR "Thinking..." indicator with tone, task-type tracks, first-name injection,
plus expanded non-general tracks and optional randomization.
"""

import time
import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional
from pydantic import BaseModel, Field
import random
import logging

logger = logging.getLogger(__name__)

# -----------------------------
# Logging
# -----------------------------
def setup_logging(log_level: str = "INFO") -> None:
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    if logger.handlers:
        logger.handlers.clear()
    ch = logging.StreamHandler()
    ch.setLevel(numeric_level)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    logger.setLevel(numeric_level)


# -----------------------------
# Filter
# -----------------------------
class Filter:
    class Valves(BaseModel):
        system_message: str = Field(
            default="""        
        <context>You are chatting with {{USER_NAME}} and email address is {{USER_EMAIL}}.</context>
        """.replace(
                "\n", " "
            ).strip(),
            description="System Message",
        )
        LOG_LEVEL: str = Field(
            title="Logging Level",
            default="INFO",
            description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
        )

    def __init__(self):
        self.start_time = None
        self.is_thinking = False
        self.current_response_index = 0
        self.last_rotation_time = None
        self.valves = self.Valves()  # default valves until inlet replaces
        setup_logging(self.valves.LOG_LEVEL)

     # -----------------------------
    # Open WebUI hooks
    # -----------------------------
    async def inlet(
        self,
        body: dict,
        __event_emitter__: Callable[[Any], Awaitable[None]] = None,
        __user__: Optional[dict] = None,
    ) -> dict:
        """
        Invoked at the start of processing to show a "Thinking..." indicator.
        """
        setup_logging(self.valves.LOG_LEVEL)
        
        user_name = (__user__ or {}).get("name") or ""
        user_email = (__user__ or {}).get("email") or ""
        logger.debug(f"Outlet called for user: {user_name}")
        logger.debug("Outlet called - stopping HR thinking indicator")
        
        if "valves" in body and isinstance(body["valves"], dict):
            try:
                self.valves = self.Valves(**{**self.Valves().dict(), **body["valves"]})
            except Exception:
                self.valves = self.Valves()

        last_message = body.get("messages", [])[-1]["content"]
        template = self.valves.system_message

        # Personalize
        template = template.replace("{{USER_NAME}}", user_name or "Unknown")
        template = template.replace("{{USER_EMAIL}}", user_email or "Unknown")

        appended_message = template + last_message
        body["messages"][-1]["content"] = appended_message
        
        logger.debug("%s Final message after appending system context: %s", "*" * 75, appended_message)
        
        return body

    async def outlet(
        self,
        body: dict,
        __event_emitter__: Callable[[Any], Awaitable[None]] = None,
        __user__: Optional[dict] = None,
    ) -> dict:
        """
        Invoked after processing to stop the indicator and summarize duration.
        """
        self.is_thinking = False
        end_time = time.time()
        elapsed = int(max(0, end_time - (self.start_time or end_time)))

        await __event_emitter__(
            {
                "type": "status",
                "data": {
                    "description": f"Thought for {elapsed} seconds",
                    "done": True,
                },
            }
        )
        logger.debug("%s Here is the body at outlet: %s", "#%#" * 50, body)
        return body
