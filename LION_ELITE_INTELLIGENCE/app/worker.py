import base64
import logging
import os
from datetime import datetime, timedelta
from email.utils import parseaddr
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import func, select

from .activities import LeadActivity
from .automation_rules import classify_reply, daily_send_limit, inside_outreach_window, sending_enabled
from .database import Base, SessionLocal, engine
from .google_services import gmail_service, send_gmail
from .models import Lead
from .outreach import build_partnership_email

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("lei-worker")
EASTERN = ZoneInfo("America/New_York")


def _header(message: dict, name: str) -> str:
    for header in message.get("payload", {}).get("headers", []):
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""


def _body_text(payload: dict) -> str:
    body_data = payload.get("body", {}).get("data")
    if body_data:
        return base64.urlsafe_b64decode(body_data).decode(errors="ignore")
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data")
            if data:
                return base64.urlsafe_b64decode(data).decode(errors="ignore")
    return ""


def sent_today_count(db) -> int:
    now = datetime.now(tz=EASTERN)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
    return db.scalar(
        select(func.count()).select_from(LeadActivity).where(
            LeadActivity.activity_type == "email",
            LeadActivity.outcome == "sent",
            LeadActivity.created_at >= start,
        )
    ) or 0


def send_outreach_batch() -> dict:
    if not sending_enabled():
        return {"status": "disabled", "sent": 0}
    if not inside_outreach_window():
        return {"status": "outside_window", "sent": 0}

    with SessionLocal() as db:
        remaining = max(0, daily_send_limit() - sent_today_count(db))
        if remaining == 0:
            return {"status": "daily_limit_reached", "sent": 0}

        stmt = (
            select(Lead)
            .where(
                Lead.status == "new",
                Lead.public_email.is_not(None),
                Lead.do_not_contact.is_(False),
            )
            .order_by(Lead.score.desc(), Lead.created_at.asc())
            .limit(min(remaining, int(os.getenv("SEND_BATCH_SIZE", "5"))))
        )
        leads = list(db.scalars(stmt).all())
        sent = 0

        for lead in leads:
            try:
                message = build_partnership_email(lead)
                result = send_gmail(lead.public_email, message.subject, message.body)
                db.add(LeadActivity(
                    lead_id=lead.id,
                    activity_type="email",
                    outcome="sent",
                    notes=f"Gmail message id: {result.get('id', '')}",
                    next_follow_up_at=datetime.utcnow() + timedelta(days=3),
                ))
                lead.status = "contacted"
                db.commit()
                sent += 1
            except Exception:
                db.rollback()
                logger.exception("Failed to send outreach for lead %s", lead.id)

        return {"status": "complete", "sent": sent}


def process_replies() -> dict:
    service = gmail_service()
    result = service.users().messages().list(
        userId="me",
        q=os.getenv("REPLY_QUERY", "in:inbox newer_than:2d -label:LEI_PROCESSED"),
        maxResults=int(os.getenv("REPLY_BATCH_SIZE", "50")),
    ).execute()
    message_ids = result.get("messages", [])
    processed = 0

    with SessionLocal() as db:
        for item in message_ids:
            message = service.users().messages().get(userId="me", id=item["id"], format="full").execute()
            sender = parseaddr(_header(message, "From"))[1].lower()
            if not sender:
                continue
            lead = db.scalar(select(Lead).where(func.lower(Lead.public_email) == sender))
            if not lead:
                continue

            text = _body_text(message.get("payload", {}))
            classification = classify_reply(text)
            if classification == "opt_out":
                lead.do_not_contact = True
                lead.status = "do_not_contact"
            elif classification == "interested":
                lead.status = "qualified"

            db.add(LeadActivity(
                lead_id=lead.id,
                activity_type="email",
                outcome=f"reply_{classification}",
                notes=text[:2000],
                next_follow_up_at=None if classification == "opt_out" else datetime.utcnow() + timedelta(days=1),
            ))
            db.commit()
            processed += 1

            processed_label = os.getenv("GMAIL_PROCESSED_LABEL_ID")
            if processed_label:
                service.users().messages().modify(
                    userId="me",
                    id=item["id"],
                    body={"addLabelIds": [processed_label]},
                ).execute()

    return {"processed": processed}


def run_cycle() -> None:
    Base.metadata.create_all(bind=engine)
    try:
        logger.info("Reply result: %s", process_replies())
    except Exception:
        logger.exception("Reply processing failed")
    try:
        logger.info("Outreach result: %s", send_outreach_batch())
    except Exception:
        logger.exception("Outreach cycle failed")


def main() -> None:
    scheduler = BlockingScheduler(timezone="America/New_York")
    scheduler.add_job(run_cycle, "interval", minutes=int(os.getenv("WORKER_INTERVAL_MINUTES", "15")), max_instances=1, coalesce=True)
    run_cycle()
    scheduler.start()


if __name__ == "__main__":
    main()
