import os
from datetime import datetime
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

OPT_OUT_TERMS = {
    "remove",
    "unsubscribe",
    "stop",
    "do not contact",
    "don't contact",
    "no more emails",
}

INTEREST_TERMS = {
    "interested",
    "let's talk",
    "lets talk",
    "book a call",
    "schedule",
    "tell me more",
}


def inside_outreach_window(now: datetime | None = None) -> bool:
    current = (now or datetime.now(tz=EASTERN)).astimezone(EASTERN)
    start_hour = int(os.getenv("OUTREACH_START_HOUR", "7"))
    end_hour = int(os.getenv("OUTREACH_END_HOUR", "18"))
    weekdays_only = os.getenv("OUTREACH_WEEKDAYS_ONLY", "true").lower() == "true"

    if weekdays_only and current.weekday() >= 5:
        return False
    return start_hour <= current.hour < end_hour


def classify_reply(text: str) -> str:
    normalized = " ".join((text or "").lower().split())
    if any(term in normalized for term in OPT_OUT_TERMS):
        return "opt_out"
    if any(term in normalized for term in INTEREST_TERMS):
        return "interested"
    return "neutral"


def daily_send_limit() -> int:
    return max(1, int(os.getenv("DAILY_SEND_LIMIT", "25")))


def follow_up_limit() -> int:
    return max(0, int(os.getenv("MAX_FOLLOW_UPS", "2")))


def sending_enabled() -> bool:
    return os.getenv("AUTONOMOUS_SENDING_ENABLED", "false").lower() == "true"


def require_verified_public_email() -> bool:
    return os.getenv("REQUIRE_VERIFIED_PUBLIC_EMAIL", "true").lower() == "true"
