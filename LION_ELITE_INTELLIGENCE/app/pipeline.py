from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Lead, Opportunity
from .schemas import OpportunityCreate, OpportunityRead, OpportunityUpdate, PipelineCard

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

VALID_STAGES = {
    "new",
    "researched",
    "call_today",
    "contacted",
    "follow_up",
    "meeting_booked",
    "proposal_sent",
    "partner",
    "lost",
}


def validate_stage(stage: str) -> str:
    normalized = stage.strip().lower()
    if normalized not in VALID_STAGES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid stage. Use one of: {', '.join(sorted(VALID_STAGES))}",
        )
    return normalized


@router.post("/opportunities", response_model=OpportunityRead, status_code=201)
def create_opportunity(payload: OpportunityCreate, db: Session = Depends(get_db)) -> Opportunity:
    lead = db.get(Lead, payload.lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    existing = db.scalar(select(Opportunity).where(Opportunity.lead_id == payload.lead_id))
    if existing:
        raise HTTPException(status_code=409, detail="Opportunity already exists for this lead")

    data = payload.model_dump()
    data["stage"] = validate_stage(data["stage"])
    opportunity = Opportunity(**data)
    db.add(opportunity)
    lead.status = data["stage"]
    db.commit()
    db.refresh(opportunity)
    return opportunity


@router.get("/opportunities", response_model=list[PipelineCard])
def list_pipeline(
    db: Session = Depends(get_db),
    stage: str | None = None,
    assigned_rep: str | None = None,
    min_score: int = Query(default=0, ge=0, le=100),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[PipelineCard]:
    stmt = (
        select(Opportunity, Lead)
        .join(Lead, Lead.id == Opportunity.lead_id)
        .where(Lead.score >= min_score)
    )

    if stage:
        stmt = stmt.where(Opportunity.stage == validate_stage(stage))
    if assigned_rep:
        stmt = stmt.where(Opportunity.assigned_rep == assigned_rep)

    rows = db.execute(
        stmt.order_by(
            Opportunity.next_follow_up_at.asc().nullslast(),
            Lead.score.desc(),
            Opportunity.created_at.asc(),
        ).limit(limit)
    ).all()

    return [
        PipelineCard(
            opportunity_id=opportunity.id,
            lead_id=lead.id,
            company_name=lead.company_name,
            owner_name=lead.owner_name,
            public_phone=lead.public_phone,
            public_email=lead.public_email,
            category=lead.category,
            city=lead.city,
            state=lead.state,
            score=lead.score,
            stage=opportunity.stage,
            assigned_rep=opportunity.assigned_rep,
            partnership_type=opportunity.partnership_type,
            estimated_annual_value=opportunity.estimated_annual_value,
            next_follow_up_at=opportunity.next_follow_up_at,
            last_contact_at=opportunity.last_contact_at,
        )
        for opportunity, lead in rows
    ]


@router.patch("/opportunities/{opportunity_id}", response_model=OpportunityRead)
def update_opportunity(
    opportunity_id: int,
    payload: OpportunityUpdate,
    db: Session = Depends(get_db),
) -> Opportunity:
    opportunity = db.get(Opportunity, opportunity_id)
    if not opportunity:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    changes = payload.model_dump(exclude_unset=True)
    if "stage" in changes and changes["stage"] is not None:
        changes["stage"] = validate_stage(changes["stage"])

    for field, value in changes.items():
        setattr(opportunity, field, value)

    if "stage" in changes:
        opportunity.lead.status = changes["stage"]
        if changes["stage"] == "proposal_sent" and not opportunity.proposal_sent_at:
            opportunity.proposal_sent_at = datetime.utcnow()
        if changes["stage"] in {"partner", "lost"} and not opportunity.closed_at:
            opportunity.closed_at = datetime.utcnow()

    db.commit()
    db.refresh(opportunity)
    return opportunity


@router.post("/opportunities/{opportunity_id}/advance", response_model=OpportunityRead)
def advance_opportunity(opportunity_id: int, db: Session = Depends(get_db)) -> Opportunity:
    opportunity = db.get(Opportunity, opportunity_id)
    if not opportunity:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    stages = [
        "new",
        "researched",
        "call_today",
        "contacted",
        "follow_up",
        "meeting_booked",
        "proposal_sent",
        "partner",
    ]
    if opportunity.stage == "lost":
        raise HTTPException(status_code=409, detail="Lost opportunities cannot be advanced")

    current_index = stages.index(opportunity.stage) if opportunity.stage in stages else 0
    next_stage = stages[min(current_index + 1, len(stages) - 1)]
    opportunity.stage = next_stage
    opportunity.lead.status = next_stage

    if next_stage == "contacted":
        opportunity.last_contact_at = datetime.utcnow()
    if next_stage == "proposal_sent":
        opportunity.proposal_sent_at = datetime.utcnow()
    if next_stage == "partner":
        opportunity.closed_at = datetime.utcnow()

    db.commit()
    db.refresh(opportunity)
    return opportunity


@router.get("/summary")
def pipeline_summary(db: Session = Depends(get_db)) -> dict:
    stage_rows = db.execute(
        select(Opportunity.stage, func.count(Opportunity.id), func.coalesce(func.sum(Opportunity.estimated_annual_value), 0))
        .group_by(Opportunity.stage)
    ).all()

    total_value = db.scalar(select(func.coalesce(func.sum(Opportunity.estimated_annual_value), 0))) or 0
    active_value = db.scalar(
        select(func.coalesce(func.sum(Opportunity.estimated_annual_value), 0)).where(
            Opportunity.stage.not_in(["partner", "lost"])
        )
    ) or 0
    partners = db.scalar(
        select(func.count()).select_from(Opportunity).where(Opportunity.stage == "partner")
    ) or 0
    overdue = db.scalar(
        select(func.count()).select_from(Opportunity).where(
            Opportunity.next_follow_up_at.is_not(None),
            Opportunity.next_follow_up_at < datetime.utcnow(),
            Opportunity.stage.not_in(["partner", "lost"]),
        )
    ) or 0

    return {
        "total_pipeline_value": float(total_value),
        "active_pipeline_value": float(active_value),
        "partners_won": partners,
        "overdue_follow_ups": overdue,
        "by_stage": {
            stage: {"count": count, "estimated_annual_value": float(value)}
            for stage, count, value in stage_rows
        },
    }
