from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from .google_services import create_calendar_event
from .worker import process_replies, send_outreach_batch

router = APIRouter(prefix="/integrations", tags=["integrations"])


class CalendarBooking(BaseModel):
    summary: str
    start_iso: datetime
    end_iso: datetime
    attendee_email: EmailStr | None = None
    description: str | None = None


@router.post("/calendar/book")
def book_calendar(payload: CalendarBooking) -> dict:
    if payload.end_iso <= payload.start_iso:
        raise HTTPException(status_code=422, detail="end_iso must be after start_iso")
    event = create_calendar_event(
        summary=payload.summary,
        start_iso=payload.start_iso.isoformat(),
        end_iso=payload.end_iso.isoformat(),
        attendee_email=str(payload.attendee_email) if payload.attendee_email else None,
        description=payload.description,
    )
    return {"event_id": event.get("id"), "event_link": event.get("htmlLink"), "status": event.get("status")}


@router.post("/worker/send-cycle")
def run_send_cycle() -> dict:
    return send_outreach_batch()


@router.post("/worker/process-replies")
def run_reply_cycle() -> dict:
    return process_replies()
