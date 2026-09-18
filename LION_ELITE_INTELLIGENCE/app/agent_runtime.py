import json
import logging
import os
from datetime import datetime, timedelta

from celery import Celery
from celery.signals import worker_ready, worker_shutting_down
from sqlalchemy import select, update

from .agent_control import (
    AgentCommitment,
    AgentDefinition,
    AgentEvent,
    AgentMessage,
    AgentTask,
    bootstrap_agents,
)
from .database import Base, SessionLocal, engine


logger = logging.getLogger("lion-elite-agent-runtime")
broker_url = os.getenv("REDIS_URL", "memory://")
celery_app = Celery("lion_elite_agents", broker=broker_url, backend=os.getenv("CELERY_RESULT_BACKEND") or None)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=int(os.getenv("AGENT_SOFT_TIME_LIMIT", "240")),
    task_time_limit=int(os.getenv("AGENT_HARD_TIME_LIMIT", "280")),
    broker_connection_retry_on_startup=True,
    timezone="America/New_York",
    beat_schedule={
        "community-heartbeat-every-minute": {
            "task": "agents.community_cycle",
            "schedule": 60.0,
        }
    },
)


def _capabilities(agent: AgentDefinition) -> list[str]:
    try:
        return json.loads(agent.capabilities_json or "[]")
    except json.JSONDecodeError:
        return []


def deterministic_route(task: AgentTask, agents: list[AgentDefinition]) -> tuple[str, str]:
    text = f"{task.title} {task.objective}".lower()
    routing = [
        ("github", ["code", "github", "deploy", "website", "app", "api"]),
        ("finance", ["money", "cost", "margin", "budget", "revenue", "finance"]),
        ("sales", ["lead", "sales", "offer", "prospect", "close"]),
        ("delivery", ["client", "milestone", "scope", "quality", "deliver"]),
        ("content", ["content", "campaign", "post", "caption", "brand"]),
        ("relationships", ["message", "email", "follow up", "relationship", "reply"]),
        ("operations", ["workflow", "process", "automation", "system", "operations"]),
        ("guardrails", ["legal", "medical", "delete", "credential", "privacy", "risk"]),
    ]
    enabled = {agent.slug for agent in agents if agent.enabled}
    primary = next((slug for slug, words in routing if slug in enabled and any(word in text for word in words)), "operations")
    reviewer_order = ["guardrails", "delivery", "finance", "operations", "github", "sales", "relationships", "content", "ai-boss"]
    partner = next((slug for slug in reviewer_order if slug in enabled and slug != primary), "ai-boss")
    return primary, partner


def ai_route(task: AgentTask, agents: list[AgentDefinition]) -> tuple[str, str, str | None]:
    if not os.getenv("OPENAI_API_KEY"):
        primary, partner = deterministic_route(task, agents)
        return primary, partner, None
    try:
        from openai import OpenAI
        roster = [{"slug": a.slug, "role": a.role, "capabilities": _capabilities(a)} for a in agents if a.enabled]
        prompt = {
            "community_rule": "All agents have equal standing. Pick one owner and one different accountability partner. AI Boss is a coordinator, not a superior.",
            "task": {"title": task.title, "objective": task.objective, "action_type": task.action_type, "risk_level": task.risk_level},
            "agents": roster,
            "output": {"primary": "agent slug", "partner": "different agent slug", "reason": "brief reason"},
        }
        response = OpenAI().responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            input="Return only valid JSON. Route this task within an equal peer community:\n" + json.dumps(prompt),
        )
        decision = json.loads(response.output_text)
        valid = {a.slug for a in agents if a.enabled}
        primary, partner = decision.get("primary"), decision.get("partner")
        if primary not in valid or partner not in valid or primary == partner:
            raise ValueError("Invalid AI routing decision")
        return primary, partner, decision.get("reason")
    except Exception:
        logger.exception("AI routing failed; using deterministic route")
        primary, partner = deterministic_route(task, agents)
        return primary, partner, None


def build_peer_plan(task: AgentTask, primary: str, partner: str) -> str:
    if not os.getenv("OPENAI_API_KEY"):
        return json.dumps({
            "objective": task.objective,
            "owner": primary,
            "accountability_partner": partner,
            "steps": [
                "Confirm the requested outcome and constraints",
                "Complete the smallest verifiable unit of work",
                "Record evidence and unresolved risks",
                "Request independent peer review",
            ],
            "completion_rule": "Peer approval is required; consequential actions also require human approval.",
        })
    try:
        from openai import OpenAI
        response = OpenAI().responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            input=(
                "Create a concise execution plan as valid JSON with keys steps, evidence_required, risks, and peer_review_checklist. "
                f"Task: {task.title}. Objective: {task.objective}. Owner: {primary}. Accountability partner: {partner}. "
                "The agents are equal peers; make responsibilities explicit and do not authorize external side effects."
            ),
        )
        return response.output_text
    except Exception:
        logger.exception("AI planning failed; using resilient fallback")
        return build_peer_plan_without_ai(task, primary, partner)


def build_peer_plan_without_ai(task: AgentTask, primary: str, partner: str) -> str:
    return json.dumps({
        "objective": task.objective, "owner": primary, "accountability_partner": partner,
        "steps": ["Clarify", "Execute", "Verify", "Request peer review"],
        "evidence_required": ["work product", "verification result", "known limitations"],
    })


@celery_app.task(name="agents.dispatch", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def dispatch_agent_task(self, task_id: int) -> dict:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        claimed = db.execute(
            update(AgentTask)
            .where(AgentTask.id == task_id, AgentTask.status.in_(["queued", "retrying"]))
            .values(status="routing", started_at=datetime.utcnow(), attempts=AgentTask.attempts + 1)
        )
        db.commit()
        if claimed.rowcount == 0:
            task = db.get(AgentTask, task_id)
            return {"task_id": task_id, "status": task.status if task else "missing"}

        task = db.get(AgentTask, task_id)
        bootstrap_agents(db)
        agents = list(db.scalars(select(AgentDefinition).where(AgentDefinition.enabled.is_(True))).all())
        primary = task.assigned_to_slug
        partner = task.accountability_partner_slug
        reason = None
        if not primary or not partner or primary == partner:
            primary, partner, reason = ai_route(task, agents)
        task.assigned_to_slug = primary
        task.accountability_partner_slug = partner
        task.status = "in_progress"
        for agent in agents:
            if agent.slug in {primary, partner}:
                agent.status = "busy"
                agent.last_heartbeat_at = datetime.utcnow()

        for slug, responsibility in [
            (primary, "Own execution, communicate blockers early, and provide verifiable evidence."),
            (partner, "Stay engaged, challenge assumptions, help remove blockers, and independently review the result."),
        ]:
            if not db.scalar(select(AgentCommitment).where(AgentCommitment.task_id == task.id, AgentCommitment.agent_slug == slug)):
                db.add(AgentCommitment(task_id=task.id, agent_slug=slug, responsibility=responsibility, due_at=task.due_at))

        db.add(AgentMessage(
            thread_id=task.thread_id, task_id=task.id, sender_slug="ai-boss", recipient_slug=None,
            message_type="routing", content=f"{primary} owns execution; {partner} is the accountability partner. {reason or 'Routed by capabilities.'}",
            requires_response=True,
        ))
        plan = build_peer_plan(task, primary, partner)
        task.result = plan
        task.status = "peer_review"
        db.add(AgentMessage(
            thread_id=task.thread_id, task_id=task.id, sender_slug=primary, recipient_slug=partner,
            message_type="review_request", content=plan, requires_response=True,
        ))
        db.add(AgentEvent(agent_slug=primary, task_id=task.id, event_type="work_ready_for_review", detail=task.title))
        db.commit()
        return {"task_id": task.id, "status": task.status, "owner": primary, "partner": partner}


@celery_app.task(name="agents.community_cycle")
def community_cycle() -> dict:
    Base.metadata.create_all(bind=engine)
    now = datetime.utcnow()
    stale_cutoff = now - timedelta(minutes=int(os.getenv("AGENT_STALE_MINUTES", "5")))
    recovered = 0
    reminders = 0
    with SessionLocal() as db:
        bootstrap_agents(db)
        agents = list(db.scalars(select(AgentDefinition).where(AgentDefinition.enabled.is_(True))).all())
        for agent in agents:
            if not agent.last_heartbeat_at or agent.last_heartbeat_at < stale_cutoff:
                if agent.status != "offline":
                    db.add(AgentEvent(agent_slug=agent.slug, event_type="agent_offline", detail="Heartbeat missed; peers must cover open commitments"))
                agent.status = "offline"

        queued = list(db.scalars(select(AgentTask).where(AgentTask.status == "queued").order_by(AgentTask.priority.desc()).limit(50)).all())
        for task in queued:
            dispatch_agent_task.delay(task.id)
            recovered += 1

        overdue = list(db.scalars(select(AgentTask).where(
            AgentTask.due_at.is_not(None), AgentTask.due_at < now,
            AgentTask.status.notin_(["completed", "cancelled"]),
        )).all())
        for task in overdue:
            existing = db.scalar(select(AgentMessage).where(
                AgentMessage.task_id == task.id, AgentMessage.message_type == "accountability_alert",
                AgentMessage.created_at >= now - timedelta(hours=6),
            ))
            if not existing:
                db.add(AgentMessage(
                    thread_id=task.thread_id, task_id=task.id, sender_slug="ai-boss", recipient_slug=None,
                    message_type="accountability_alert",
                    content=f"Commitment missed on '{task.title}'. Owner and accountability partner must respond with recovery steps.",
                    requires_response=True,
                ))
                db.add(AgentEvent(agent_slug="community", task_id=task.id, event_type="missed_commitment", detail=task.title))
                reminders += 1
        db.commit()
    return {"queued_recovered": recovered, "accountability_alerts": reminders}


@worker_ready.connect
def on_worker_ready(**_kwargs) -> None:
    Base.metadata.create_all(bind=engine)
    logger.info("Agent community worker ready")


@worker_shutting_down.connect
def on_worker_shutdown(**_kwargs) -> None:
    logger.info("Agent worker draining; in-flight tasks will finish or be retried idempotently")
