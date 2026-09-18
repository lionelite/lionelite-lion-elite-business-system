import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base, get_db


router = APIRouter(prefix="/agents", tags=["agent-control"])
DASHBOARD_PATH = Path(__file__).with_name("agent_dashboard.html")

DEFAULT_AGENTS = [
    ("ai-boss", "AI Boss", "Peer coordinator", "Facilitate planning, routing, conflict resolution, and recovery without outranking peers.", ["routing", "planning", "mediation", "recovery"]),
    ("sales", "Sales Agent", "Revenue partner", "Qualify opportunities and create value-based sales plans.", ["sales", "offers", "pipeline", "follow_up"]),
    ("delivery", "Delivery Agent", "Client outcomes partner", "Protect scope, quality, deadlines, margin, and client acceptance.", ["delivery", "qa", "milestones", "client_success"]),
    ("finance", "Finance Agent", "Financial accountability partner", "Track cash, cost, profit, budgets, and financial risk.", ["finance", "margin", "forecasting", "cost_control"]),
    ("content", "Content Agent", "Brand communication partner", "Produce accurate on-brand content tied to measurable goals.", ["content", "campaigns", "brand", "copy"]),
    ("relationships", "Relationship Agent", "Community partner", "Maintain respectful communication, follow-ups, and stakeholder context.", ["relationships", "crm", "communication", "retention"]),
    ("github", "GitHub Agent", "Engineering coordination partner", "Translate outcomes into issues, branches, reviews, tests, and releases.", ["github", "engineering", "code_review", "release"]),
    ("operations", "Operations Agent", "Systems reliability partner", "Keep workflows documented, measurable, available, and recoverable.", ["operations", "automation", "reliability", "documentation"]),
    ("guardrails", "Guardrails Agent", "Risk and accountability partner", "Challenge unsafe, noncompliant, irreversible, or poorly evidenced actions.", ["risk", "privacy", "approval", "audit"]),
]

HUMAN_APPROVAL_ACTIONS = {"money", "contract", "destructive", "credentials", "legal", "medical", "external_sensitive"}


class AgentDefinition(Base):
    __tablename__ = "agent_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(180))
    mission: Mapped[str] = mapped_column(Text)
    capabilities_json: Mapped[str] = mapped_column(Text, default="[]")
    autonomy_level: Mapped[str] = mapped_column(String(30), default="guarded")
    status: Mapped[str] = mapped_column(String(30), default="offline", index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(80), default=lambda: uuid4().hex, index=True)
    title: Mapped[str] = mapped_column(String(255))
    objective: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=50, index=True)
    action_type: Mapped[str] = mapped_column(String(60), default="internal")
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    created_by_slug: Mapped[str] = mapped_column(String(80), default="human")
    assigned_to_slug: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    accountability_partner_slug: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    requires_human_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_status: Mapped[str] = mapped_column(String(30), default="not_required", index=True)
    consensus_required: Mapped[int] = mapped_column(Integer, default=1)
    context_json: Mapped[str] = mapped_column(Text, default="{}")
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(80), index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=True, index=True)
    sender_slug: Mapped[str] = mapped_column(String(80), index=True)
    recipient_slug: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    message_type: Mapped[str] = mapped_column(String(40), default="discussion")
    content: Mapped[str] = mapped_column(Text)
    requires_response: Mapped[bool] = mapped_column(Boolean, default=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class AgentCommitment(Base):
    __tablename__ = "agent_commitments"
    __table_args__ = (UniqueConstraint("task_id", "agent_slug", name="uq_task_agent_commitment"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("agent_tasks.id", ondelete="CASCADE"), index=True)
    agent_slug: Mapped[str] = mapped_column(String(80), index=True)
    responsibility: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="accepted", index=True)
    blocker: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PeerReview(Base):
    __tablename__ = "agent_peer_reviews"
    __table_args__ = (UniqueConstraint("task_id", "reviewer_slug", name="uq_task_peer_reviewer"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("agent_tasks.id", ondelete="CASCADE"), index=True)
    reviewer_slug: Mapped[str] = mapped_column(String(80), index=True)
    verdict: Mapped[str] = mapped_column(String(20), index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SharedMemory(Base):
    __tablename__ = "agent_shared_memory"
    __table_args__ = (UniqueConstraint("scope", "scope_id", "key", name="uq_agent_memory_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[str] = mapped_column(String(30), default="global", index=True)
    scope_id: Mapped[str] = mapped_column(String(120), default="community", index=True)
    key: Mapped[str] = mapped_column(String(180), index=True)
    content: Mapped[str] = mapped_column(Text)
    created_by_slug: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgentEvent(Base):
    __tablename__ = "agent_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_slug: Mapped[str] = mapped_column(String(80), index=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    detail: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class TaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    objective: str = Field(min_length=5)
    priority: int = Field(default=50, ge=1, le=100)
    action_type: str = "internal"
    risk_level: str = "low"
    created_by_slug: str = "human"
    assigned_to_slug: str | None = None
    accountability_partner_slug: str | None = None
    due_at: datetime | None = None
    context: dict = Field(default_factory=dict)
    idempotency_key: str | None = None


class MessageCreate(BaseModel):
    sender_slug: str
    recipient_slug: str | None = None
    message_type: str = "discussion"
    content: str = Field(min_length=1)
    requires_response: bool = False


class CommitmentUpdate(BaseModel):
    status: str
    blocker: str | None = None


class ReviewCreate(BaseModel):
    reviewer_slug: str
    verdict: str
    notes: str | None = None


class ApprovalCreate(BaseModel):
    approved: bool
    approved_by: str = "Alexander Ringfield"
    notes: str | None = None


class MemoryWrite(BaseModel):
    scope: str = "global"
    scope_id: str = "community"
    key: str = Field(min_length=2, max_length=180)
    content: str = Field(min_length=1)
    created_by_slug: str


def _event(db: Session, agent_slug: str, event_type: str, detail: str, task_id: int | None = None) -> None:
    db.add(AgentEvent(agent_slug=agent_slug, task_id=task_id, event_type=event_type, detail=detail))


def bootstrap_agents(db: Session) -> int:
    created = 0
    for slug, name, role, mission, capabilities in DEFAULT_AGENTS:
        if not db.scalar(select(AgentDefinition).where(AgentDefinition.slug == slug)):
            db.add(AgentDefinition(
                slug=slug, name=name, role=role, mission=mission,
                capabilities_json=json.dumps(capabilities), autonomy_level="guarded",
            ))
            created += 1
    db.commit()
    return created


def serialize_agent(agent: AgentDefinition) -> dict:
    return {
        "id": agent.id, "slug": agent.slug, "name": agent.name, "role": agent.role,
        "mission": agent.mission, "capabilities": json.loads(agent.capabilities_json or "[]"),
        "autonomy_level": agent.autonomy_level, "status": agent.status, "enabled": agent.enabled,
        "last_heartbeat_at": agent.last_heartbeat_at, "created_at": agent.created_at,
    }


def serialize_task(task: AgentTask) -> dict:
    return {
        "id": task.id, "thread_id": task.thread_id, "title": task.title, "objective": task.objective,
        "status": task.status, "priority": task.priority, "action_type": task.action_type,
        "risk_level": task.risk_level, "created_by_slug": task.created_by_slug,
        "assigned_to_slug": task.assigned_to_slug, "accountability_partner_slug": task.accountability_partner_slug,
        "requires_human_approval": task.requires_human_approval, "approval_status": task.approval_status,
        "consensus_required": task.consensus_required, "result": task.result, "error": task.error,
        "due_at": task.due_at, "started_at": task.started_at, "completed_at": task.completed_at,
        "attempts": task.attempts, "created_at": task.created_at, "updated_at": task.updated_at,
    }


@router.get("", response_class=HTMLResponse)
def dashboard() -> str:
    return DASHBOARD_PATH.read_text(encoding="utf-8")


@router.post("/api/bootstrap")
def bootstrap(db: Session = Depends(get_db)) -> dict:
    return {"created": bootstrap_agents(db), "total": db.scalar(select(func.count()).select_from(AgentDefinition)) or 0}


@router.get("/api/agents")
def list_agents(db: Session = Depends(get_db)) -> list[dict]:
    bootstrap_agents(db)
    agents = list(db.scalars(select(AgentDefinition).order_by(AgentDefinition.name)).all())
    return [serialize_agent(agent) for agent in agents]


@router.post("/api/agents/{slug}/heartbeat")
def heartbeat(slug: str, db: Session = Depends(get_db)) -> dict:
    agent = db.scalar(select(AgentDefinition).where(AgentDefinition.slug == slug))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.status = "online"
    agent.last_heartbeat_at = datetime.utcnow()
    _event(db, slug, "heartbeat", "Agent reported ready")
    db.commit()
    return serialize_agent(agent)


@router.post("/api/tasks", status_code=201)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> dict:
    bootstrap_agents(db)
    requires_approval = payload.action_type in HUMAN_APPROVAL_ACTIONS or payload.risk_level == "high"
    task = AgentTask(
        title=payload.title, objective=payload.objective, priority=payload.priority,
        action_type=payload.action_type, risk_level=payload.risk_level,
        created_by_slug=payload.created_by_slug, assigned_to_slug=payload.assigned_to_slug,
        accountability_partner_slug=payload.accountability_partner_slug, due_at=payload.due_at,
        context_json=json.dumps(payload.context),
        idempotency_key=payload.idempotency_key or uuid4().hex,
        requires_human_approval=requires_approval,
        approval_status="pending" if requires_approval else "not_required",
    )
    db.add(task)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(AgentTask).where(AgentTask.idempotency_key == payload.idempotency_key))
        if not existing:
            raise HTTPException(status_code=409, detail="Duplicate task")
        return serialize_task(existing)
    db.add(AgentMessage(
        thread_id=task.thread_id, task_id=task.id, sender_slug=payload.created_by_slug,
        recipient_slug="ai-boss", message_type="task_created", content=payload.objective, requires_response=True,
    ))
    _event(db, payload.created_by_slug, "task_created", payload.title, task.id)
    db.commit()
    db.refresh(task)
    try:
        from .agent_runtime import dispatch_agent_task
        dispatch_agent_task.delay(task.id)
    except Exception:
        _event(db, "system", "queue_unavailable", "Task persisted and will be recovered by the community cycle", task.id)
        db.commit()
    return serialize_task(task)


@router.get("/api/tasks")
def list_tasks(status: str | None = None, limit: int = 100, db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(AgentTask)
    if status:
        stmt = stmt.where(AgentTask.status == status)
    tasks = list(db.scalars(stmt.order_by(AgentTask.priority.desc(), AgentTask.created_at.desc()).limit(min(limit, 500))).all())
    return [serialize_task(task) for task in tasks]


@router.get("/api/tasks/{task_id}/workspace")
def task_workspace(task_id: int, db: Session = Depends(get_db)) -> dict:
    task = db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    messages = list(db.scalars(select(AgentMessage).where(AgentMessage.task_id == task_id).order_by(AgentMessage.created_at)).all())
    commitments = list(db.scalars(select(AgentCommitment).where(AgentCommitment.task_id == task_id).order_by(AgentCommitment.id)).all())
    reviews = list(db.scalars(select(PeerReview).where(PeerReview.task_id == task_id).order_by(PeerReview.created_at)).all())
    return {
        "task": serialize_task(task),
        "messages": [{"id": m.id, "sender_slug": m.sender_slug, "recipient_slug": m.recipient_slug, "message_type": m.message_type, "content": m.content, "requires_response": m.requires_response, "created_at": m.created_at} for m in messages],
        "commitments": [{"id": c.id, "agent_slug": c.agent_slug, "responsibility": c.responsibility, "status": c.status, "blocker": c.blocker, "due_at": c.due_at} for c in commitments],
        "reviews": [{"id": r.id, "reviewer_slug": r.reviewer_slug, "verdict": r.verdict, "notes": r.notes, "created_at": r.created_at} for r in reviews],
    }


@router.post("/api/tasks/{task_id}/messages", status_code=201)
def post_message(task_id: int, payload: MessageCreate, db: Session = Depends(get_db)) -> dict:
    task = db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    message = AgentMessage(thread_id=task.thread_id, task_id=task.id, **payload.model_dump())
    db.add(message)
    _event(db, payload.sender_slug, "message", f"To {payload.recipient_slug or 'community'}: {payload.content[:180]}", task.id)
    db.commit()
    db.refresh(message)
    return {"id": message.id, "created_at": message.created_at}


@router.patch("/api/commitments/{commitment_id}")
def update_commitment(commitment_id: int, payload: CommitmentUpdate, db: Session = Depends(get_db)) -> dict:
    commitment = db.get(AgentCommitment, commitment_id)
    if not commitment:
        raise HTTPException(status_code=404, detail="Commitment not found")
    commitment.status = payload.status
    commitment.blocker = payload.blocker
    commitment.completed_at = datetime.utcnow() if payload.status == "done" else None
    _event(db, commitment.agent_slug, "commitment_updated", payload.status, commitment.task_id)
    db.commit()
    return {"id": commitment.id, "status": commitment.status}


@router.post("/api/tasks/{task_id}/reviews", status_code=201)
def peer_review(task_id: int, payload: ReviewCreate, db: Session = Depends(get_db)) -> dict:
    task = db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if payload.reviewer_slug == task.assigned_to_slug:
        raise HTTPException(status_code=422, detail="A task owner cannot peer-review their own work")
    if payload.verdict not in {"approve", "revise", "block"}:
        raise HTTPException(status_code=422, detail="Verdict must be approve, revise, or block")
    review = PeerReview(task_id=task_id, **payload.model_dump())
    db.add(review)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This agent already reviewed the task")
    if payload.verdict in {"revise", "block"}:
        task.status = "blocked" if payload.verdict == "block" else "in_progress"
    else:
        approvals = (db.scalar(select(func.count()).select_from(PeerReview).where(
            PeerReview.task_id == task_id, PeerReview.verdict == "approve"
        )) or 0)
        if approvals >= task.consensus_required:
            if task.requires_human_approval and task.approval_status != "approved":
                task.status = "waiting_approval"
            else:
                task.status = "completed"
                task.completed_at = datetime.utcnow()
    _event(db, payload.reviewer_slug, "peer_review", payload.verdict, task_id)
    db.commit()
    return {"task_id": task_id, "status": task.status, "verdict": payload.verdict}


@router.post("/api/tasks/{task_id}/approval")
def human_approval(task_id: int, payload: ApprovalCreate, db: Session = Depends(get_db)) -> dict:
    task = db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.approval_status = "approved" if payload.approved else "rejected"
    if payload.approved and task.status == "waiting_approval":
        task.status = "completed"
        task.completed_at = datetime.utcnow()
    elif not payload.approved:
        task.status = "blocked"
    _event(db, "human", "approval", f"{task.approval_status} by {payload.approved_by}: {payload.notes or ''}", task_id)
    db.commit()
    return {"task_id": task.id, "status": task.status, "approval_status": task.approval_status}


@router.put("/api/memory")
def write_memory(payload: MemoryWrite, db: Session = Depends(get_db)) -> dict:
    memory = db.scalar(select(SharedMemory).where(
        SharedMemory.scope == payload.scope, SharedMemory.scope_id == payload.scope_id, SharedMemory.key == payload.key
    ))
    if memory:
        memory.content = payload.content
        memory.created_by_slug = payload.created_by_slug
        memory.version += 1
    else:
        memory = SharedMemory(**payload.model_dump())
        db.add(memory)
    _event(db, payload.created_by_slug, "memory_written", f"{payload.scope}/{payload.scope_id}/{payload.key}")
    db.commit()
    db.refresh(memory)
    return {"id": memory.id, "version": memory.version, "updated_at": memory.updated_at}


@router.get("/api/community")
def community_overview(db: Session = Depends(get_db)) -> dict:
    bootstrap_agents(db)
    now = datetime.utcnow()
    agents = list(db.scalars(select(AgentDefinition).order_by(AgentDefinition.name)).all())
    tasks = list(db.scalars(select(AgentTask).order_by(AgentTask.updated_at.desc()).limit(100)).all())
    events = list(db.scalars(select(AgentEvent).order_by(AgentEvent.created_at.desc()).limit(100)).all())
    pending_approvals = sum(t.status == "waiting_approval" for t in tasks)
    missed = sum(bool(t.due_at and t.due_at < now and t.status not in {"completed", "cancelled"}) for t in tasks)
    return {
        "agents": [serialize_agent(a) for a in agents],
        "tasks": [serialize_task(t) for t in tasks],
        "events": [{"id": e.id, "agent_slug": e.agent_slug, "task_id": e.task_id, "event_type": e.event_type, "detail": e.detail, "created_at": e.created_at} for e in events],
        "stats": {
            "agents": len(agents), "online": sum(a.status in {"online", "busy"} for a in agents),
            "open_tasks": sum(t.status not in {"completed", "cancelled"} for t in tasks),
            "blocked_tasks": sum(t.status == "blocked" for t in tasks),
            "pending_approvals": pending_approvals, "missed_commitments": missed,
        },
    }
