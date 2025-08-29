"""
title: GIA Personalization
version: 0.1.1
"""

import logging
import pytz
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional

# Get a module-level logger
logger = logging.getLogger(__name__)
# Optional: basic config if your app doesn't set logging up elsewhere.
# Safe to remove if your framework already configures logging.
if not logging.getLogger().hasHandlers():
    logging.basicConfig(
        level=logging.DEBUG, format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )


class Filter:
    class Valves(BaseModel):
        system_message: str = Field(
            default="""        
        <context>
        - You are chatting with {{USER_NAME}}.
        </context>

        Use personalized responses with this context when appropriate. 
        For example, when answering question from the user, you can say "I'm here to help you with that {{FIRST_NAME}}, or "That's in interesting point, {{FIRST_NAME}}.
        If asked to be more formal, you should respond with {{USER_NAME}}, or if the user asks for a name, you should respond with {{USER_NAME}}.

        """.replace(
                "\n", " "
            ).strip(),
            description="System Message",
        )

    def __init__(self):
        self.valves = self.Valves()

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        # Be defensive: __user__ might be None or missing "name"
        user_name = (__user__ or {}).get("name") or ""
        first_name = user_name.split(" ")[0] if user_name else ""

        # Debug info
        if len(body.get("messages", [])) > 1:
            logger.info("Messages array length: %s", len(body["messages"]))
        logger.info("%s user payload: %s", "^" * 25, __user__)
        logger.info("Request body: %s", body)
        logger.info("User name: %s", user_name)

        messages = body.get("messages", [])

        system_prompt = next(
            (message for message in messages if message.get("role") == "system"),
            None,
        )
        if system_prompt:
            template = system_prompt.get("content", "")
        else:
            logger.info("No system message. Using fallback template.")
            template = self.valves.system_message

        # Personalize
        template = template.replace("{{USER_NAME}}", user_name or "Unknown")
        template = template.replace("{{FIRST_NAME}}", first_name or "Unknown")

        if system_prompt:
            system_prompt["content"] = template
        else:
            system_prompt = {"role": "system", "content": template}

        filtered_messages = [system_prompt] + [
            message for message in messages if message.get("role") != "system"
        ]
        body["messages"] = filtered_messages
        return body
