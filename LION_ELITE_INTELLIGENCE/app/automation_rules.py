import os
from datetime import datetime
from zoneinfo import ZoneInfo

from .sdr import legacy_classification

EASTERN = ZoneInfo("America/New_York")

# Kept as the record of what this module used to match on its own. The live
# vocabulary is `sdr.OPT_OUT_PHRASES` / `sdr.POSITIVE_PHRASES`; these are
# retained only because external callers import them, and every term in them is
# covered there.
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
    """Three-value reply classification, delegated to `sdr.classify_reply`.

    This was a second implementation of reply classification with its own word
    lists. Two classifiers deciding whether someone opted out is one classifier
    too many: whichever one a given caller happened to import decided whether a
    person kept being emailed. `sdr` is the single implementation now, and this
    is the adapter for callers that still want the old string.

    Prefer `sdr.classify_reply` in new code — it returns `stop_sequence`
    explicitly, which is the field that actually governs sending, and this
    three-value answer cannot express "stop, but this is not an opt-out".
    """
    return legacy_classification(text)


def daily_send_limit() -> int:
    return max(1, int(os.getenv("DAILY_SEND_LIMIT", "25")))


def follow_up_limit() -> int:
    return max(0, int(os.getenv("MAX_FOLLOW_UPS", "2")))


def sending_enabled() -> bool:
    return os.getenv("AUTONOMOUS_SENDING_ENABLED", "false").lower() == "true"


def require_verified_public_email() -> bool:
    return os.getenv("REQUIRE_VERIFIED_PUBLIC_EMAIL", "true").lower() == "true"
