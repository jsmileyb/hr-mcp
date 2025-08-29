"""
title: GIA HR Assistant Thinking Indicator
author: Smiley Baltz
version: 0.0.1
description: Playful HR "Thinking..." indicator with tone, task-type tracks, and first-name injection.
"""

import time
import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional
from pydantic import BaseModel, Field
import random
import logging
import re

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
# User redactor (place it here!)
# -----------------------------
def _redact_user(u: Optional[dict]) -> Optional[dict]:
    if not isinstance(u, dict):
        return None
    redact_keys = {"api_key", "oauth_sub", "profile_image_url"}
    return {k: ("<redacted>" if k in redact_keys else v) for k, v in u.items()}


# -----------------------------
# Filter
# -----------------------------
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
        TONE: str = Field(
            title="Tone",
            default="Casual",
            description="Response tone: Casual | Professional | Super Cheerful",
        )
        ROTATE_SECONDS: float = Field(
            title="Rotate Seconds",
            default=3.5,
            description="How often to rotate the message (seconds)",
        )
        SHOW_PATIENCE_HINTS: bool = Field(
            title="Emphasize External System Patience",
            default=True,
            description="If true, inject patient messaging when external systems are involved",
        )

    # -----------------------------
    # Tone/Track Response Library
    # -----------------------------
    TRACKS: Dict[str, Dict[str, List[str]]] = {
        # PTO: time off, balances, accruals, holidays
        "pto": {
            "Casual": [
                "Hey {name}, counting those sweet, sweet accruals… carry the beach, subtract the meetings.",
                "Running PTO math—no PTO left behind. 🏖️",
                "Checking blackout dates and solar eclipses… just in case.",
                "Reconciling ‘out of office’ with ‘out of PTO’—plot twist pending.",
                "Paging your accrual engine—it says you deserve sunscreen.",
            ],
            "Professional": [
                "Reviewing PTO accruals and carryover rules for you, {name}.",
                "Confirming balances, holidays, and any blackout dates.",
                "Cross-referencing tenure-based accruals and policy thresholds.",
                "Validating manager approvals and effective dates.",
                "Ensuring fairness and compliance across leave policies.",
            ],
            "Super Cheerful": [
                "🌞 Hey {name}! Your vacation dreams are meeting their balance. It’s a love story!",
                "Loading the PTO piñata—stand by for candy math!",
                "Sprinkling holidays like confetti—pure joy, zero calories!",
                "Beach mode negotiating with calendar mode… peace talks underway!",
                "Your accruals just high-fived HR. Cute.",
            ],
        },
        # Policy: handbook, guidelines, eligibility, compliance
        "policy": {
            "Casual": [
                "Consulting the Employee Handbook—page mysteriously marked with a coffee ring.",
                "Doing the HR two-step: review, document, smile.",
                "Translating HR-ese to human—snacks may be involved.",
                "Double-checking decimals—policies have feelings too.",
                "Phone-a-friend: the Handbook. It always picks up. Eventually.",
            ],
            "Professional": [
                "Locating the relevant section of the Employee Handbook for you, {name}.",
                "Verifying eligibility, scope, and any regional exceptions.",
                "Citing the policy source with version and effective date.",
                "Reconciling policy text with current practice—consistency matters.",
                "Documenting interpretation and next steps for clarity.",
            ],
            "Super Cheerful": [
                "📘 Handbook huddle! Section {section} is warming up the spotlight. (We’ll find it, promise.)",
                "Captain Compliance just adjusted their cape. We got this!",
                "Bringing policies and plain English together like besties.",
                "Shining the policy halo—sparkly AND compliant!",
                "Policy pit-stop complete—clarity fuel topped off!",
            ],
        },
        # Payroll: pay periods, taxes, W-2, deductions
        "payroll": {
            "Casual": [
                "Syncing with Payroll’s good vibes… and their spreadsheets.",
                "Counting beans that officially count—deductions, taxes, the works.",
                "Matching job codes and Jedi codes—both must align.",
                "Asking the spreadsheet guardian for a blessing. She nods.",
                "Queuing the kindness protocol: clarify, confirm, celebrate.",
            ],
            "Professional": [
                "Reviewing pay period details and applicable deductions for you, {name}.",
                "Confirming tax withholdings and year-to-date values.",
                "Reconciling payroll records with HRIS for accuracy.",
                "Checking effective dates for compensation changes.",
                "Preparing a clean summary you can reference later.",
            ],
            "Super Cheerful": [
                "💸 Payroll party! Your numbers are lining up like champs.",
                "Polishing the compliance halo while the digits dance.",
                "Spreadsheets are doing jazz hands—deductions included!",
                "Numbers confirmed, confetti standing by!",
                "Your pay info and HR are officially on speaking terms. Cute!",
            ],
        },
        # General fallback
        "general": {
            "Casual": [
                "HR is thinking… and yes, we brought snacks.",
                "Filing this under ‘Good Choices’ (subfolder: PTO).",
                "Polishing the compliance halo—gotta keep it shiny.",
                "Plotting a route from policy to permission—no tolls.",
                "Proofreading policy punctuation—Oxford comma says hi.",
            ],
            "Professional": [
                "Reviewing your request and confirming relevant records, {name}.",
                "Reconciling data across HRIS and policy sources.",
                "Preparing a concise, documented response.",
                "Ensuring equitable and consistent application of policy.",
                "Finalizing details for accuracy and clarity.",
            ],
            "Super Cheerful": [
                "✨ Spinning up the People Ops Optimizer—results incoming!",
                "Your request is getting the VIP HR treatment.",
                "Compliance cape on, empathy dial set to ‘perfect’!",
                "Good news loading… kindness protocol engaged.",
                "Checklist checked. Twice. (We’re fancy.)",
            ],
        },
    }

    # Patient hints appended/rotated when externals are involved
    PATIENCE_HINTS: List[str] = [
        "Heads up: checking external systems can take a sec—real data > fast guesses.",
        "Still syncing with HRIS/Payroll—slower than normal Q&A, but worth the accuracy.",
        "Verifying with live systems (balances, approvals, dates). Thanks for your patience!",
        "External checks running—coffee break optional, correctness mandatory.",
        "Almost there—policy meets platform, and platforms like to think.",
    ]

    def __init__(self):
        self.start_time = None
        self.is_thinking = False
        self.current_response_index = 0
        self.last_rotation_time = None
        self.valves = self.Valves()  # default valves until inlet replaces
        setup_logging(self.valves.LOG_LEVEL)

    # -----------------------------
    # Helpers
    # -----------------------------
    @staticmethod
    def _get_first_name(body: dict, user: Optional[dict] = None) -> str:
        """
        Prefer __user__ info (authoritative), then fall back to body fields.
        """
        # 1) __user__ takes precedence
        if isinstance(user, dict):
            # Try 'name' first (full name), fall back to username (rare)
            for key in ("name", "username"):
                val = user.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip().split()[0]
            # If there's a nested 'info' with a name-like thing
            if isinstance(user.get("info"), dict):
                for key in ("first_name", "given_name"):
                    val = user["info"].get(key)
                    if isinstance(val, str) and val.strip():
                        return val.strip().split()[0]

        # 2) Fall back to body-sourced locations
        candidates = [
            ("employee", "first_name"),
            ("employee", "name"),
            ("user", "first_name"),
            ("user", "name"),
            ("metadata", "employee_first_name"),
            ("metadata", "first_name"),
            ("context", "first_name"),
        ]
        for a, b in candidates:
            try:
                val = (body.get(a) or {}).get(b)
                if isinstance(val, str) and val.strip():
                    return val.strip().split()[0]
            except Exception:
                pass
        return "there"


    @staticmethod
    def _detect_task_track(body: dict) -> str:
        """
        Detect the task type from body.task.type if provided, otherwise fallback to keyword detection.
        """
        # Direct override if provided
        task_obj = body.get("task") or body.get("metadata") or {}
        task_type = None
        if isinstance(task_obj, dict):
            task_type = task_obj.get("type") or task_obj.get("task_type")

        if isinstance(task_type, str):
            t = task_type.strip().lower()
            if t in ["pto", "vacation", "leave", "holiday"]:
                return "pto"
            if t in ["policy", "handbook", "guideline"]:
                return "policy"
            if t in ["payroll", "pay", "compensation"]:
                return "payroll"
            if t in ["general", "other"]:
                return "general"

        # --- fallback keyword detection ---
        text_fields = []
        for k in ("query", "prompt", "text", "message"):
            v = body.get(k)
            if isinstance(v, str):
                text_fields.append(v)
        for scope in ("metadata", "context"):
            v = body.get(scope, {})
            for kk, vv in (v.items() if isinstance(v, dict) else []):
                if isinstance(vv, str):
                    text_fields.append(vv)

        hay = " ".join(text_fields).lower()

        # keywords
        pto_kw = ["pto", "vacation", "time off", "leave", "holiday", "accrual"]
        policy_kw = ["policy", "handbook", "guideline", "procedure", "benefit", "eligibility"]
        payroll_kw = ["payroll", "pay", "paystub", "w-2", "w2", "withholding", "deduction", "tax"]

        def has_any(words: List[str]) -> bool:
            return any(w in hay for w in words)

        if has_any(pto_kw):
            return "pto"
        if has_any(payroll_kw):
            return "payroll"
        if has_any(policy_kw):
            return "policy"
        return "general"


    @staticmethod
    def _externals_involved(body: dict) -> bool:
        """
        Only treat the task as 'external' if the upstream explicitly says so.

        Signals (in order of precedence):
          1) body.task.requires_external == True
          2) body.task.systems or body.task.endpoints is a non-empty list
          3) body.metadata.requires_external == True  (optional backstop)
        """
        task = body.get("task") if isinstance(body.get("task"), dict) else {}
        meta = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}

        # 1) Primary explicit flag
        if isinstance(task.get("requires_external"), bool) and task["requires_external"]:
            return True

        # 2) Non-empty system lists also imply external checks
        for key in ("systems", "endpoints"):
            val = task.get(key)
            if isinstance(val, (list, tuple)) and len(val) > 0:
                return True

        # 3) Optional backstop if your pipeline prefers metadata
        if isinstance(meta.get("requires_external"), bool) and meta["requires_external"]:
            return True

        # Otherwise, we do NOT show patience hints
        return False


    @staticmethod
    def _normalize_tone(tone: str) -> str:
        t = (tone or "").strip().lower()
        if t.startswith("pro"):
            return "Professional"
        if t.startswith("super"):
            return "Super Cheerful"
        return "Casual"

    def _pick_message(self, track: str, tone: str, name: str) -> str:
        tone_key = self._normalize_tone(tone)
        library = self.TRACKS.get(track, self.TRACKS["general"]).get(tone_key, self.TRACKS["general"]["Casual"])
        msg = library[self.current_response_index % len(library)]
        return msg.format(name=name, section="4.2")

    # -----------------------------
    # Async updaters
    # -----------------------------
    async def _update_thinking_status(
        self,
        __event_emitter__: Callable[[Any], Awaitable[None]],
        body: dict,
        user: Optional[dict] = None,
    ):
        logger.debug("Starting thinking status updates")
        self.is_thinking = True
        self.start_time = time.time()
        self.last_rotation_time = self.start_time
        name = self._get_first_name(body, user)  # <<— now uses __user__ first
        track = self._detect_task_track(body)
        externals = self._externals_involved(body)
        tone = self.valves.TONE

        patience_index = 0
        patience_gap = 2  # rotate a patience note every other cycle if externals

        while self.is_thinking:
            now = time.time()
            if now - self.last_rotation_time >= float(self.valves.ROTATE_SECONDS):
                self.current_response_index += 1
                self.last_rotation_time = now

            base_line = self._pick_message(track, tone, name)

            if self.valves.SHOW_PATIENCE_HINTS and externals:
                if (self.current_response_index % patience_gap) == 0:
                    hint = self.PATIENCE_HINTS[patience_index % len(self.PATIENCE_HINTS)]
                    patience_index += 1
                    line = f"{base_line}  {hint}"
                else:
                    line = base_line
            else:
                line = base_line

            await __event_emitter__({"type": "status", "data": {"description": line, "done": False}})
            await asyncio.sleep(0.5)


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
        if "valves" in body and isinstance(body["valves"], dict):
            try:
                self.valves = self.Valves(**{**self.Valves().dict(), **body["valves"]})
            except Exception:
                self.valves = self.Valves()

        setup_logging(self.valves.LOG_LEVEL)

        # Safe, redacted log for debugging (won’t leak keys/images)
        logger.debug(f"Inlet called; user={_redact_user(__user__)}")

        # spin background updater
        asyncio.create_task(self._update_thinking_status(__event_emitter__, body, __user__))
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
        logger.debug("Outlet called - stopping HR thinking indicator")
        self.is_thinking = False
        end_time = time.time()
        elapsed = int(max(0, end_time - (self.start_time or end_time)))

        await __event_emitter__(
            {
                "type": "status",
                "data": {
                    "description": f"Filed the paperwork in {elapsed} seconds",
                    "done": True,
                },
            }
        )
        return body

