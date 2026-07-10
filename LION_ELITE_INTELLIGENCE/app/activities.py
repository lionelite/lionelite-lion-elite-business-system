from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base, get_db
from .models import Lead


class LeadActivity(Base):
    __tablename__ = "lead_activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    activity_type: Mapped[str] = mapped_column(String(50), index=True)
    outcome: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ActivityCreate(BaseModel):
    activity_type: str = Field(pattern="^(call|email|text|meeting|note)$")
    outcome: str | None = None
    notes: str | None = None
    next_follow_up_at: datetime | None = None
    new_lead_status: str | None = None


class ActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lead_id: int
    activity_type: str
    outcome: str | None
    notes: str | None
    next_follow_up_at: datetime | None
    created_at: datetime


router = APIRouter(prefix="/activities", tags=["activities"])


@router.post("/leads/{lead_id}", response_model=ActivityRead, status_code=201)
def create_activity(lead_id: int, payload: ActivityCreate, db: Session = Depends(get_db)) -> LeadActivity:
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    activity = LeadActivity(
        lead_id=lead_id,
        activity_type=payload.activity_type,
        outcome=payload.outcome,
        notes=payload.notes,
        next_follow_up_at=payload.next_follow_up_at,
    )
    db.add(activity)

    if payload.new_lead_status:
        lead.status = payload.new_lead_status

    db.commit()
    db.refresh(activity)
    return activity


@router.get("/leads/{lead_id}", response_model=list[ActivityRead])
def list_lead_activities(
    lead_id: int,
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[LeadActivity]:
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    stmt = (
        select(LeadActivity)
        .where(LeadActivity.lead_id == lead_id)
        .order_by(LeadActivity.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


@router.get("/follow-ups")
def follow_up_queue(
    db: Session = Depends(get_db),
    due_before: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    cutoff = due_before or datetime.utcnow()
    stmt = (
        select(LeadActivity, Lead)
        .join(Lead, Lead.id == LeadActivity.lead_id)
        .where(
            LeadActivity.next_follow_up_at.is_not(None),
            LeadActivity.next_follow_up_at <= cutoff,
            Lead.do_not_contact.is_(False),
        )
        .order_by(LeadActivity.next_follow_up_at.asc())
        .limit(limit)
    )

    rows = db.execute(stmt).all()
    return [
        {
            "activity_id": activity.id,
            "lead_id": lead.id,
            "company": lead.company_name,
            "owner": lead.owner_name,
            "phone": lead.public_phone,
            "email": lead.public_email,
            "status": lead.status,
            "last_activity": activity.activity_type,
            "last_outcome": activity.outcome,
            "follow_up_due": activity.next_follow_up_at,
            "notes": activity.notes,
        }
        for activity, lead in rows
    ]
