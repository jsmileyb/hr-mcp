"""
GIA HR Assistant Thinking Indicator (Expanded Tracks)
Author: Smiley Baltz
Version: 0.0.4
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
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
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
        <context>You are chatting with {{USER_EMAIL}}.</context>
        """.replace(
                "\n", " "
            ).strip(),
            description="System Message",
        )
        PRIORITY: int = Field(
            title="Priority",
            default=15,
            description="Priority for executing the filter",
        )
        LOG_LEVEL: str = Field(
            title="Logging Level",
            default="DEBUG",
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
        RANDOMIZE: bool = Field(
            title="Randomize Picks",
            default=True,
            description="If true, occasionally randomize message selection for more variety",
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
        # NEW: People — leadership info, employee lookup, HRP assignments
        "people": {
            "Casual": [
                "Looking up your people details—who reports to whom and why coffee matters.",
                "Connecting dots across org charts—one tidy line at a time.",
                "Finding your HR Partner and their superpowers… capes optional.",
            ],
            "Professional": [
                "Retrieving leadership and HR Partner assignments for you, {name}.",
                "Verifying reporting lines and department details.",
                "Confirming the correct contact for your request.",
            ],
            "Super Cheerful": [
                "🧭 Org compass engaged—HRP and leaders, assemble!",
                "Your support squad is loading—names, titles, and high-fives included.",
                "People data aligned—time to make magic happen!",
            ],
        },
        # NEW: Tenure — years of service, hire date
        "tenure": {
            "Casual": [
                "Counting work-birthdays—cake eligibility under review.",
                "Dusting off the hire-date scrapbook—memories + math.",
                "Pinning your service milestone—confetti pending approval.",
            ],
            "Professional": [
                "Calculating years of service and confirming hire dates, {name}.",
                "Reconciling HRIS history for accurate tenure.",
                "Preparing milestone details you can share.",
            ],
            "Super Cheerful": [
                "🎉 Service stars aligning—anniversary stats incoming!",
                "Milestone meter: rising rapidly. Cake ETA: delicious.",
                "Your tenure just waved hello—so polite!",
            ],
        },
        # NEW: Benefits — insurance, 401k, perks
        "benefits": {
            "Casual": [
                "Peeking into the benefits toolkit—health, wealth, and wellness.",
                "Comparing plan acronyms like a pro—PPO vs HSA showdown.",
                "Checking who’s covered and where the perks live.",
            ],
            "Professional": [
                "Reviewing your benefits elections and eligibility, {name}.",
                "Confirming plan details, coverage dates, and dependents.",
                "Cross-referencing 401(k) and insurance documentation.",
            ],
            "Super Cheerful": [
                "🩺🧠 Benefits buffet loading—coverage with a side of calm.",
                "Perk radar pinging—good things ahead!",
                "Your plan info is suiting up—ready to help.",
            ],
        },
        # General fallback (expanded)
        "general": {
            "Casual": [
                "HR is thinking… and yes, we brought snacks.",
                "Filing this under ‘Good Choices’ (subfolder: PTO).",
                "Polishing the compliance halo—gotta keep it shiny.",
                "Plotting a route from policy to permission—no tolls.",
                "Proofreading policy punctuation—Oxford comma says hi.",
                # Added for variety
                "Comparing notes with the HR crystal ball—data wins.",
                "Turning big questions into tidy checklists.",
                "Taking a lap around HRIS—back in a jiffy.",
                "Sharpening pencils and answers—both required.",
                "Queuing a tiny parade for accuracy.",
            ],
            "Professional": [
                "Reviewing your request and confirming relevant records, {name}.",
                "Reconciling data across HRIS and policy sources.",
                "Preparing a concise, documented response.",
                "Ensuring equitable and consistent application of policy.",
                "Finalizing details for accuracy and clarity.",
                # Added for variety
                "Validating data lineage to ensure correctness.",
                "Summarizing findings and recommended next steps.",
                "Checking for regional or role-based exceptions.",
                "Coordinating across systems to prevent gaps.",
                "Documenting outcomes for future reference.",
            ],
            "Super Cheerful": [
                "✨ Spinning up the People Ops Optimizer—results incoming!",
                "Your request is getting the VIP HR treatment.",
                "Compliance cape on, empathy dial set to ‘perfect’!",
                "Good news loading… kindness protocol engaged.",
                "Checklist checked. Twice. (We’re fancy.)",
                # Added for variety
                "Answers are stretching—ready to perform!",
                "HR rocket fuel: engaged. Stand by for clarity.",
                "Signals strong, smiles stronger—here we go!",
                "The helpfulness meter just peaked. Nice.",
                "Sparkles applied—accuracy included by default.",
            ],
        },
    }

    # Patient hints (unchanged)
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
            for key in ("name", "username"):
                val = user.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip().split()[0]
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
    def _externals_involved(body: dict) -> bool:
        """
        Only treat the task as 'external' if the upstream explicitly says so.
        Signals (in order of precedence):
          1) body.task.requires_external == True
          2) body.task.systems or body.task.endpoints is a non-empty list
          3) body.metadata.requires_external == True (optional backstop)
        """
        task = body.get("task") if isinstance(body.get("task"), dict) else {}
        meta = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
        if (
            isinstance(task.get("requires_external"), bool)
            and task["requires_external"]
        ):
            return True
        for key in ("systems", "endpoints"):
            val = task.get(key)
            if isinstance(val, (list, tuple)) and len(val) > 0:
                return True
        if (
            isinstance(meta.get("requires_external"), bool)
            and meta["requires_external"]
        ):
            return True
        return False

    @staticmethod
    def _normalize_tone(tone: str) -> str:
        t = (tone or "").strip().lower()
        if t.startswith("pro"):
            return "Professional"
        if t.startswith("super"):
            return "Super Cheerful"
        return "Casual"

    # -----------------------------
    # UPDATED: Broader task detection (prevents getting stuck on 'general')
    # -----------------------------
    @staticmethod
    def _detect_task_track(body: dict) -> str:
        """
        Detect task type from explicit body.task.type / metadata.task_type or via keywords.
        """
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
            if t in ["benefits", "insurance", "401k", "perk", "perks"]:
                return "benefits"
            if t in [
                "people",
                "employee",
                "leadership",
                "org",
                "hrp",
                "partner",
                "assignment",
            ]:
                return "people"
            if t in ["tenure", "service", "anniversary", "hiredate", "hire_date"]:
                return "tenure"
            if t in ["general", "other"]:
                return "general"

        # Fallback keyword detection across likely text fields
        text_fields: List[str] = []
        for k in ("query", "prompt", "text", "message"):
            v = body.get(k)
            if isinstance(v, str):
                text_fields.append(v)
        for scope in ("metadata", "context"):
            v = body.get(scope, {})
            for kk, vv in v.items() if isinstance(v, dict) else []:
                if isinstance(vv, str):
                    text_fields.append(vv)
        hay = " ".join(text_fields).lower()

        def has_any(words: List[str]) -> bool:
            return any(w in hay for w in words)

        pto_kw = ["pto", "vacation", "time off", "leave", "holiday", "accrual"]
        payroll_kw = [
            "payroll",
            "pay",
            "paystub",
            "w-2",
            "w2",
            "withholding",
            "deduction",
            "tax",
        ]
        policy_kw = [
            "policy",
            "handbook",
            "guideline",
            "procedure",
            "benefit policy",
            "eligibility",
        ]
        benefits_kw = [
            "benefits",
            "insurance",
            "medical",
            "dental",
            "vision",
            "401k",
            "hsa",
            "fsa",
            "perk",
        ]
        people_kw = [
            "employee",
            "manager",
            "leader",
            "leadership",
            "org chart",
            "assignment",
            "hrp",
            "partner",
        ]
        tenure_kw = [
            "tenure",
            "hire date",
            "years of service",
            "anniversary",
            "service award",
        ]

        if has_any(pto_kw):
            return "pto"
        if has_any(payroll_kw):
            return "payroll"
        if has_any(policy_kw):
            return "policy"
        if has_any(benefits_kw):
            return "benefits"
        if has_any(people_kw):
            return "people"
        if has_any(tenure_kw):
            return "tenure"
        return "general"

    def _pick_message(self, track: str, tone: str, name: str) -> str:
        tone_key = self._normalize_tone(tone)
        library = self.TRACKS.get(track, self.TRACKS["general"]).get(
            tone_key, self.TRACKS["general"]["Casual"]
        )
        # Variety boost: randomize when enabled
        if getattr(self.valves, "RANDOMIZE", True):
            msg = random.choice(library)
        else:
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
        name = self._get_first_name(body, user)
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
                    hint = self.PATIENCE_HINTS[
                        patience_index % len(self.PATIENCE_HINTS)
                    ]
                    patience_index += 1
                    line = f"{base_line}  {hint}"
                else:
                    line = base_line
            else:
                line = base_line

            await __event_emitter__(
                {"type": "status", "data": {"description": line, "done": False}}
            )
            await asyncio.sleep(self.valves.ROTATE_SECONDS)

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
        # template = template.replace("{{USER_NAME}}", user_name or "Unknown")
        template = template.replace("{{USER_EMAIL}}", user_email or "Unknown")

        appended_message = template + last_message
        body["messages"][-1]["content"] = appended_message

        logger.debug(
            "%s Final message after appending system context: %s",
            "*" * 75,
            appended_message,
        )

        asyncio.create_task(
            self._update_thinking_status(__event_emitter__, body, __user__)
        )
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
                    "description": f"Filed the paperwork in {elapsed} seconds",
                    "done": True,
                },
            }
        )
        logger.debug("%s Here is the body at outlet: %s", "#%#" * 50, body)
        return body
