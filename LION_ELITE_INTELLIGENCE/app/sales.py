import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Lead
from .outreach import build_partnership_email

router = APIRouter(prefix="/sales", tags=["sales"])


@router.get("/leads/{lead_id}/outreach-preview")
def outreach_preview(lead_id: int, db: Session = Depends(get_db)) -> dict:
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if lead.do_not_contact:
        raise HTTPException(status_code=409, detail="Lead is marked do not contact")
    if not lead.public_email:
        raise HTTPException(status_code=409, detail="Lead has no verified public email")

    message = build_partnership_email(lead)
    return {
        "lead_id": lead.id,
        "to": lead.public_email,
        "subject": message.subject,
        "body": message.body,
        "status": lead.status,
    }


@router.get("/call-queue")
def call_queue(
    db: Session = Depends(get_db),
    min_score: int = Query(default=70, ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict]:
    stmt = (
        select(Lead)
        .where(
            Lead.score >= min_score,
            Lead.public_phone.is_not(None),
            Lead.do_not_contact.is_(False),
            Lead.status.in_(["new", "contacted", "follow_up"]),
        )
        .order_by(Lead.score.desc(), Lead.created_at.asc())
        .limit(limit)
    )
    leads = list(db.scalars(stmt).all())
    return [
        {
            "id": lead.id,
            "score": lead.score,
            "company": lead.company_name,
            "owner": lead.owner_name,
            "phone": lead.public_phone,
            "email": lead.public_email,
            "category": lead.category,
            "location": ", ".join(filter(None, [lead.city, lead.state])),
            "partnership_angle": lead.partnership_angle,
            "status": lead.status,
            "suggested_opener": (
                f"Hi, this is Alexander with Lion Elite Beauty. "
                f"I am calling because {lead.company_name} looks like a strong fit for "
                f"{(lead.partnership_angle or 'a referral partnership').lower()}."
            ),
        }
        for lead in leads
    ]


@router.get("/call-queue.csv")
def export_call_queue(
    db: Session = Depends(get_db),
    min_score: int = Query(default=70, ge=0, le=100),
    limit: int = Query(default=500, ge=1, le=1000),
) -> Response:
    stmt = (
        select(Lead)
        .where(
            Lead.score >= min_score,
            Lead.public_phone.is_not(None),
            Lead.do_not_contact.is_(False),
        )
        .order_by(Lead.score.desc(), Lead.created_at.asc())
        .limit(limit)
    )
    leads = list(db.scalars(stmt).all())

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "lead_id",
        "score",
        "company",
        "owner",
        "phone",
        "email",
        "category",
        "city",
        "state",
        "partnership_angle",
        "status",
        "call_opener",
    ])

    for lead in leads:
        writer.writerow([
            lead.id,
            lead.score,
            lead.company_name,
            lead.owner_name or "",
            lead.public_phone or "",
            lead.public_email or "",
            lead.category,
            lead.city or "",
            lead.state or "",
            lead.partnership_angle or "",
            lead.status,
            f"Hi, this is Alexander with Lion Elite Beauty. I am calling because {lead.company_name} looks like a strong fit for a partnership.",
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=lion_elite_call_queue.csv"},
    )
