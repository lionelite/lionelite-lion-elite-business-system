from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from .database import Base, get_db


router = APIRouter(prefix="/delivery", tags=["delivery"])
DASHBOARD_PATH = Path(__file__).with_name("delivery_dashboard.html")


class Contractor(Base):
    __tablename__ = "delivery_contractors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    specialty: Mapped[str] = mapped_column(String(255), index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rate_type: Mapped[str] = mapped_column(String(30), default="fixed")
    rate: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    projects: Mapped[list["DeliveryProject"]] = relationship(back_populates="contractor")


class DeliveryProject(Base):
    __tablename__ = "delivery_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_name: Mapped[str] = mapped_column(String(255), index=True)
    project_name: Mapped[str] = mapped_column(String(255), index=True)
    offer_type: Mapped[str] = mapped_column(String(100), default="AI Automation")
    status: Mapped[str] = mapped_column(String(40), default="scoping", index=True)
    owner: Mapped[str] = mapped_column(String(100), default="Alexander Ringfield")
    contractor_id: Mapped[int | None] = mapped_column(ForeignKey("delivery_contractors.id"), nullable=True)
    contract_value: Mapped[float] = mapped_column(Float, default=0)
    collected_amount: Mapped[float] = mapped_column(Float, default=0)
    developer_budget: Mapped[float] = mapped_column(Float, default=0)
    actual_developer_cost: Mapped[float] = mapped_column(Float, default=0)
    software_cost: Mapped[float] = mapped_column(Float, default=0)
    other_cost: Mapped[float] = mapped_column(Float, default=0)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    acceptance_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    repo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    contractor: Mapped[Contractor | None] = relationship(back_populates="projects")
    milestones: Mapped[list["DeliveryMilestone"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )

    @property
    def forecast_cost(self) -> float:
        developer_cost = self.actual_developer_cost or self.developer_budget
        return round(developer_cost + self.software_cost + self.other_cost, 2)

    @property
    def forecast_profit(self) -> float:
        return round(self.contract_value - self.forecast_cost, 2)

    @property
    def margin_percent(self) -> float:
        return round((self.forecast_profit / self.contract_value) * 100, 1) if self.contract_value else 0


class DeliveryMilestone(Base):
    __tablename__ = "delivery_milestones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("delivery_projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="not_started", index=True)
    payout_amount: Mapped[float] = mapped_column(Float, default=0)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    acceptance_test: Mapped[str | None] = mapped_column(Text, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped[DeliveryProject] = relationship(back_populates="milestones")


class ContractorCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    specialty: str = Field(min_length=2, max_length=255)
    email: str | None = None
    rate_type: str = "fixed"
    rate: float = Field(default=0, ge=0)
    status: str = "active"
    notes: str | None = None


class ContractorRead(ContractorCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


class ProjectCreate(BaseModel):
    client_name: str = Field(min_length=2, max_length=255)
    project_name: str = Field(min_length=2, max_length=255)
    offer_type: str = "AI Automation"
    status: str = "scoping"
    owner: str = "Alexander Ringfield"
    contractor_id: int | None = None
    contract_value: float = Field(default=0, ge=0)
    collected_amount: float = Field(default=0, ge=0)
    developer_budget: float = Field(default=0, ge=0)
    actual_developer_cost: float = Field(default=0, ge=0)
    software_cost: float = Field(default=0, ge=0)
    other_cost: float = Field(default=0, ge=0)
    start_date: date | None = None
    due_date: date | None = None
    scope: str | None = None
    acceptance_criteria: str | None = None
    repo_url: str | None = None
    notes: str | None = None


class ProjectUpdate(BaseModel):
    status: str | None = None
    contractor_id: int | None = None
    collected_amount: float | None = Field(default=None, ge=0)
    developer_budget: float | None = Field(default=None, ge=0)
    actual_developer_cost: float | None = Field(default=None, ge=0)
    software_cost: float | None = Field(default=None, ge=0)
    other_cost: float | None = Field(default=None, ge=0)
    due_date: date | None = None
    scope: str | None = None
    acceptance_criteria: str | None = None
    repo_url: str | None = None
    notes: str | None = None


class ProjectRead(ProjectCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    forecast_cost: float
    forecast_profit: float
    margin_percent: float
    created_at: datetime
    updated_at: datetime


class MilestoneCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    status: str = "not_started"
    payout_amount: float = Field(default=0, ge=0)
    due_date: date | None = None
    acceptance_test: str | None = None


class MilestoneUpdate(BaseModel):
    status: str | None = None
    payout_amount: float | None = Field(default=None, ge=0)
    due_date: date | None = None
    acceptance_test: str | None = None
    accepted: bool | None = None


class MilestoneRead(MilestoneCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    accepted_at: datetime | None
    created_at: datetime


@router.get("", response_class=HTMLResponse)
def delivery_dashboard() -> str:
    return DASHBOARD_PATH.read_text(encoding="utf-8")


@router.post("/api/contractors", response_model=ContractorRead, status_code=201)
def create_contractor(payload: ContractorCreate, db: Session = Depends(get_db)) -> Contractor:
    contractor = Contractor(**payload.model_dump())
    db.add(contractor)
    db.commit()
    db.refresh(contractor)
    return contractor


@router.get("/api/contractors", response_model=list[ContractorRead])
def list_contractors(db: Session = Depends(get_db)) -> list[Contractor]:
    return list(db.scalars(select(Contractor).order_by(Contractor.status, Contractor.name)).all())


@router.post("/api/projects", response_model=ProjectRead, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> DeliveryProject:
    if payload.contractor_id and not db.get(Contractor, payload.contractor_id):
        raise HTTPException(status_code=404, detail="Contractor not found")
    project = DeliveryProject(**payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/api/projects", response_model=list[ProjectRead])
def list_projects(status: str | None = None, db: Session = Depends(get_db)) -> list[DeliveryProject]:
    stmt = select(DeliveryProject)
    if status:
        stmt = stmt.where(DeliveryProject.status == status)
    return list(db.scalars(stmt.order_by(DeliveryProject.updated_at.desc())).all())


@router.patch("/api/projects/{project_id}", response_model=ProjectRead)
def update_project(project_id: int, payload: ProjectUpdate, db: Session = Depends(get_db)) -> DeliveryProject:
    project = db.get(DeliveryProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("contractor_id") and not db.get(Contractor, changes["contractor_id"]):
        raise HTTPException(status_code=404, detail="Contractor not found")
    for field, value in changes.items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@router.post("/api/projects/{project_id}/milestones", response_model=MilestoneRead, status_code=201)
def create_milestone(project_id: int, payload: MilestoneCreate, db: Session = Depends(get_db)) -> DeliveryMilestone:
    if not db.get(DeliveryProject, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    milestone = DeliveryMilestone(project_id=project_id, **payload.model_dump())
    db.add(milestone)
    db.commit()
    db.refresh(milestone)
    return milestone


@router.get("/api/projects/{project_id}/milestones", response_model=list[MilestoneRead])
def list_milestones(project_id: int, db: Session = Depends(get_db)) -> list[DeliveryMilestone]:
    if not db.get(DeliveryProject, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    stmt = select(DeliveryMilestone).where(DeliveryMilestone.project_id == project_id).order_by(DeliveryMilestone.id)
    return list(db.scalars(stmt).all())


@router.patch("/api/milestones/{milestone_id}", response_model=MilestoneRead)
def update_milestone(milestone_id: int, payload: MilestoneUpdate, db: Session = Depends(get_db)) -> DeliveryMilestone:
    milestone = db.get(DeliveryMilestone, milestone_id)
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")
    changes = payload.model_dump(exclude_unset=True)
    accepted = changes.pop("accepted", None)
    for field, value in changes.items():
        setattr(milestone, field, value)
    if accepted is not None:
        milestone.accepted_at = datetime.utcnow() if accepted else None
        if accepted:
            milestone.status = "accepted"
    db.commit()
    db.refresh(milestone)
    return milestone


@router.get("/api/summary")
def delivery_summary(db: Session = Depends(get_db)) -> dict:
    projects = list(db.scalars(select(DeliveryProject)).all())
    open_statuses = {"scoping", "sold", "assigned", "in_progress", "client_review"}
    today = date.today()
    return {
        "projects": len(projects),
        "active_projects": sum(p.status in open_statuses for p in projects),
        "contracted_revenue": round(sum(p.contract_value for p in projects), 2),
        "cash_collected": round(sum(p.collected_amount for p in projects), 2),
        "forecast_cost": round(sum(p.forecast_cost for p in projects), 2),
        "forecast_profit": round(sum(p.forecast_profit for p in projects), 2),
        "portfolio_margin_percent": round(
            (sum(p.forecast_profit for p in projects) / sum(p.contract_value for p in projects)) * 100, 1
        ) if sum(p.contract_value for p in projects) else 0,
        "overdue_projects": sum(bool(p.due_date and p.due_date < today and p.status not in {"complete", "cancelled"}) for p in projects),
        "unaccepted_milestones": db.scalar(
            select(func.count()).select_from(DeliveryMilestone).where(DeliveryMilestone.accepted_at.is_(None))
        ) or 0,
    }
