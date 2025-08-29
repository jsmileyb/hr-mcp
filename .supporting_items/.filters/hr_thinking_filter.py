"""
title: GIA HR Assistant Thinking Indicator
author: Smiley Baltz
version: 0.1.0
description: Displays a fun "Thinking..." indicator while GIA HR Assistant is processing a request.

"""

import time
import asyncio
from typing import Any, Awaitable, Callable
from pydantic import BaseModel, Field
import random
import logging

# Get logger for this module
logger = logging.getLogger(__name__)


# Configure the logger
def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure logging with the specified log level.
    Args:
        log_level (str): Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Convert string to logging level constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Remove existing handlers to avoid duplicates
    if logger.handlers:
        logger.handlers.clear()

    # Create console handler with the specified level
    ch = logging.StreamHandler()
    ch.setLevel(numeric_level)

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    ch.setFormatter(formatter)

    # Add the handler to the logger
    logger.addHandler(ch)
    logger.setLevel(numeric_level)

    logger.debug("Logger initialized")
    logger.info(f"Echo Pipeline logger is ready (Level: {log_level})")


# Initialize logger with default level
setup_logging()


class Filter:
    class Valves(BaseModel):
        PRIORITY: int = Field(
            title="Priority",
            default=15,
            description="Priority for executing the filter",
        )
        LOG_LEVEL: str = Field(
            title="Logging Level",
            default="INFO",
            description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
        )
        pass

    def __init__(self):
        self.start_time = None
        self.is_thinking = False
        self.responses = [
            # HR-flavored “thinking” lines
            "Consulting the Employee Handbook… page mysteriously marked with a coffee ring.",
            "Running a quick policy check—because HR loves a good citation.",
            "Verifying PTO math… carry the beach, subtract the meetings.",
            "Herding policies into compliance… please hold all confetti.",
            "Syncing with Payroll’s good vibes… and their spreadsheets.",
            "Counting PTO beans… these ones taste like vacation.",
            "Checking job codes and Jedi codes—both must align.",
            "Drafting a friendly memo to your time off balance.",
            "Phone-a-friend: the Handbook. It always answers (eventually).",
            "Doing the HR two-step: review, document, smile.",
            "Translating HR-ese to human—may involve snacks.",
            "Auditing time like a timesheet superhero (cape optional).",
            "Pulling your PTO ledger out of the ‘Do Not Disturb’ folder.",
            "Reconciling ‘out of office’ with ‘out of PTO’ (plot twist pending).",
            "Double-checking accruals—because decimals have feelings too.",
            "Measuring twice, approving once—Handbook-approved craftsmanship.",
            "Paging Section 4.2: ‘Thou shalt hydrate and log PTO.’",
            "Calling a brief stand-up with the policies. They’re… remarkably seated.",
            "Queueing the kindness protocol: clarify, confirm, celebrate.",
            "Polishing the compliance halo—gotta keep it shiny.",
            "Aligning vacation dreams with timesheet realities… negotiating peace.",
            "Loading the PTO piñata—stand by for candy math.",
            "Stamping this with ‘HR Friendly’ and a small smiley face.",
            "Checking for blackout dates and solar eclipses—both count sometimes.",
            "Turning pages faster than you can say ‘work-life balance.’",
            "Matching your request with the magical accrual engine.",
            "Consulting the calendar oracle… it prefers Mondays less.",
            "Plotting a route from policy to permission—no tolls.",
            "Running background… checks on background checks (just kidding).",
            "Spinning up the ‘People Ops Optimizer’ (™ not pending).",
            "Writing a tiny kudos note in the margins of compliance.",
            "Counting holidays like they’re sprinkles—pure joy, zero calories.",
            "Checking carryover rules—no PTO left behind.",
            "Confirming manager approvals with a wink and a timestamp.",
            "Balancing fairness, fun, and federal guidelines—easy peasy.",
            "Sweeping the handbook for gotchas—only glitter found.",
            "Reconciling calendars… your beach vs. your boss.",
            "Filing this under ‘Good Choices’ (subfolder: PTO).",
            "Clearing it with the spreadsheet guardian—she nods.",
            "Tuning the empathy dial to ‘perfectly supportive’.",
            "Proofreading policy punctuation—Oxford comma says hi.",
            "Aligning benefits with benefits of naps—research ongoing.",
            "HR is thinking… and yes, we brought snacks.",
            "Turning on the ‘vacay radar’—signal strong.",
            "Your balance and your plans are getting acquainted.",
            "Checking tenure perks—loyalty has its lounge.",
            "Calibrating fairness matrix… equitable and adorable.",
            "Cross-referencing accruals with the laws of physics.",
            "Consulting Captain Compliance—cape confirms.",
        ]

        self.current_response_index = random.randint(0, len(self.responses) - 1)
        self.last_rotation_time = None  # Will be set when inlet is called
        logger.info(
            f"Thinking filter initialized with responses: {len(self.responses)}"
        )


    async def _update_thinking_status(
        self, __event_emitter__: Callable[[Any], Awaitable[None]]
    ):
        """
        Continuously update "Thinking..." status with elapsed time every second.
        """
        logger.debug("Starting thinking status updates")
        while self.is_thinking:
            elapsed_time = int(time.time() - self.start_time)
            current_time = time.time()

            # Initialize last_rotation_time if it's None
            if self.last_rotation_time is None:
                self.last_rotation_time = current_time
                logger.debug("Initialized last_rotation_time")

            # Rotate responses every 1 second (for testing)
            if current_time - self.last_rotation_time >= 3:
                logger.debug(
                    f"Time to rotate! Current index: {self.current_response_index}"
                )
                # Force a different index than the current one
                new_index = self.current_response_index
                while (
                    new_index == self.current_response_index and len(self.responses) > 1
                ):
                    new_index = random.randint(0, len(self.responses) - 1)
                    logger.debug(f"Trying new index: {new_index}")
                self.current_response_index = new_index
                self.last_rotation_time = current_time
                logger.debug(
                    f"Rotated to new response: {self.responses[self.current_response_index]}"
                )

            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": self.responses[self.current_response_index],
                        "done": False,
                    },
                }
            )
            await asyncio.sleep(0.5)  # Update more frequently

    async def inlet(
        self,
        body: dict,
        __event_emitter__: Callable[[Any], Awaitable[None]] = None,
    ) -> dict:
        """
        This hook is invoked at the start of processing to show a "Thinking..." indicator.
        """
        logger.debug("Inlet called - starting thinking indicator")
        self.start_time = time.time()
        self.is_thinking = True
        self.last_rotation_time = self.start_time

        # Start a background task to update the "Thinking..." status
        asyncio.create_task(self._update_thinking_status(__event_emitter__))

        return body

    async def outlet(
        self,
        body: dict,
        __event_emitter__: Callable[[Any], Awaitable[None]] = None,
    ) -> dict:
        """
        This hook is invoked after the processing to calculate the elapsed time and show it.
        """
        logger.debug("Outlet called - stopping thinking indicator")
        self.is_thinking = False
        end_time = time.time()
        elapsed_time = end_time - self.start_time

        # Emit final "done" status with total elapsed time
        await __event_emitter__(
            {
                "type": "status",
                "data": {
                    "description": f"Filed the paperwork in {int(elapsed_time)} seconds",
                    "done": True,
                },
            }
        )
        
        return body
