import csv
import io
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .activities import router as activities_router
from .database import Base, engine, get_db
from .models import Lead
from .sales import router as sales_router
from .schemas import LeadCreate, LeadRead, LeadUpdate
from .scoring import calculate_score

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Lion Elite Intelligence",
    version="0.4.0",
    description="CRM-ready lead intelligence API for public business prospect data.",
)
app.include_router(sales_router)
app.include_router(activities_router)

DASHBOARD_PATH = Path(__file__).with_name("dashboard.html")


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return DASHBOARD_PATH.read_text(encoding="utf-8")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "lion-elite-intelligence", "version": "0.4.0"}


def find_duplicate(db: Session, data: dict) -> Lead | None:
    duplicate_filters = []
    if data.get("public_email"):
        duplicate_filters.append(Lead.public_email == str(data["public_email"]))
    if data.get("website"):
        duplicate_filters.append(Lead.website == data["website"])
    if not duplicate_filters:
        return None
    return db.scalar(select(Lead).where(or_(*duplicate_filters)))


@app.post("/leads", response_model=LeadRead, status_code=201)
def create_lead(payload: LeadCreate, db: Session = Depends(get_db)) -> Lead:
    data = payload.model_dump()
    existing = find_duplicate(db, data)
    if existing:
        raise HTTPException(status_code=409, detail="Lead already exists")

    data["public_email"] = str(data["public_email"]) if data.get("public_email") else None
    data["score"] = calculate_score(data)
    lead = Lead(**data)
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


@app.post("/leads/bulk")
def bulk_create_leads(payload: list[LeadCreate], db: Session = Depends(get_db)) -> dict:
    created = 0
    skipped_duplicates = 0
    errors: list[dict] = []

    for index, item in enumerate(payload):
        try:
            data = item.model_dump()
            if find_duplicate(db, data):
                skipped_duplicates += 1
                continue

            data["public_email"] = str(data["public_email"]) if data.get("public_email") else None
            data["score"] = calculate_score(data)
            db.add(Lead(**data))
            created += 1
        except Exception as exc:
            errors.append({"index": index, "error": str(exc)})

    db.commit()
    return {
        "received": len(payload),
        "created": created,
        "skipped_duplicates": skipped_duplicates,
        "errors": errors,
    }


@app.get("/stats")
def stats(db: Session = Depends(get_db)) -> dict:
    total = db.scalar(select(func.count()).select_from(Lead)) or 0
    qualified = db.scalar(select(func.count()).select_from(Lead).where(Lead.score >= 80)) or 0
    new_leads = db.scalar(select(func.count()).select_from(Lead).where(Lead.status == "new")) or 0
    dnc = db.scalar(select(func.count()).select_from(Lead).where(Lead.do_not_contact.is_(True))) or 0

    status_rows = db.execute(
        select(Lead.status, func.count(Lead.id)).group_by(Lead.status).order_by(func.count(Lead.id).desc())
    ).all()
    category_rows = db.execute(
        select(Lead.category, func.count(Lead.id)).group_by(Lead.category).order_by(func.count(Lead.id).desc()).limit(10)
    ).all()

    return {
        "total_leads": total,
        "qualified_leads": qualified,
        "new_leads": new_leads,
        "do_not_contact": dnc,
        "by_status": {status: count for status, count in status_rows},
        "top_categories": {category: count for category, count in category_rows},
    }


@app.get("/leads", response_model=list[LeadRead])
def list_leads(
    db: Session = Depends(get_db),
    status: str | None = None,
    category: str | None = None,
    state: str | None = None,
    min_score: int = Query(default=0, ge=0, le=100),
    q: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[Lead]:
    stmt = select(Lead).where(Lead.score >= min_score)

    if status:
        stmt = stmt.where(Lead.status == status)
    if category:
        stmt = stmt.where(Lead.category.ilike(f"%{category}%"))
    if state:
        stmt = stmt.where(Lead.state == state.upper())
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                Lead.company_name.ilike(pattern),
                Lead.owner_name.ilike(pattern),
                Lead.city.ilike(pattern),
                Lead.notes.ilike(pattern),
            )
        )

    stmt = stmt.order_by(Lead.score.desc(), Lead.created_at.desc()).offset(offset).limit(limit)
    return list(db.scalars(stmt).all())


@app.get("/leads/{lead_id}", response_model=LeadRead)
def get_lead(lead_id: int, db: Session = Depends(get_db)) -> Lead:
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@app.patch("/leads/{lead_id}", response_model=LeadRead)
def update_lead(lead_id: int, payload: LeadUpdate, db: Session = Depends(get_db)) -> Lead:
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(lead, field, value)

    db.commit()
    db.refresh(lead)
    return lead


@app.delete("/leads/{lead_id}", status_code=204)
def delete_lead(lead_id: int, db: Session = Depends(get_db)) -> Response:
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    db.delete(lead)
    db.commit()
    return Response(status_code=204)


@app.get("/exports/leads.csv")
def export_leads_csv(
    db: Session = Depends(get_db),
    min_score: int = Query(default=0, ge=0, le=100),
    status: str | None = None,
) -> Response:
    stmt = select(Lead).where(Lead.score >= min_score, Lead.do_not_contact.is_(False))
    if status:
        stmt = stmt.where(Lead.status == status)

    leads = list(db.scalars(stmt.order_by(Lead.score.desc())).all())
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "score", "company_name", "owner_name", "category", "city", "state",
        "public_phone", "public_email", "website", "partnership_angle", "status", "notes",
    ])

    for lead in leads:
        writer.writerow([
            lead.id, lead.score, lead.company_name, lead.owner_name or "", lead.category,
            lead.city or "", lead.state or "", lead.public_phone or "", lead.public_email or "",
            lead.website or "", lead.partnership_angle or "", lead.status, lead.notes or "",
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=lion_elite_leads.csv"},
    )
