import os
from datetime import datetime
from pathlib import Path

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import DateTime, ForeignKey, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base, get_db
from .saas import Organization, current_workspace


router = APIRouter(prefix="/billing", tags=["billing"])
PAGE = Path(__file__).with_name("billing_dashboard.html")
PRICE_ENV = {"growth": "STRIPE_GROWTH_PRICE_ID", "scale": "STRIPE_SCALE_PRICE_ID"}


class BillingSubscription(Base):
    __tablename__ = "billing_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(180), nullable=True, unique=True)
    stripe_price_id: Mapped[str | None] = mapped_column(String(180), nullable=True)
    plan: Mapped[str] = mapped_column(String(30), default="trial")
    status: Mapped[str] = mapped_column(String(30), default="trialing")
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProcessedBillingEvent(Base):
    __tablename__ = "processed_billing_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stripe_event_id: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100))
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CheckoutRequest(BaseModel):
    plan: str


def _stripe_ready() -> None:
    key = os.getenv("STRIPE_SECRET_KEY")
    if not key:
        raise HTTPException(status_code=503, detail="Billing is not configured yet")
    stripe.api_key = key


def _owner(workspace) -> tuple:
    user, organization, membership = workspace
    if membership.role != "owner":
        raise HTTPException(status_code=403, detail="Only the workspace owner can manage billing")
    return user, organization


@router.get("")
def billing_page(_workspace=Depends(current_workspace)):
    from fastapi.responses import HTMLResponse
    return HTMLResponse(PAGE.read_text(encoding="utf-8"))


@router.get("/api/status")
def billing_status(workspace=Depends(current_workspace), db: Session = Depends(get_db)) -> dict:
    _, organization, membership = workspace
    subscription = db.scalar(select(BillingSubscription).where(BillingSubscription.organization_id == organization.id))
    return {
        "plan": organization.plan,
        "status": organization.subscription_status,
        "can_manage": membership.role == "owner",
        "subscription": None if not subscription else {
            "plan": subscription.plan,
            "status": subscription.status,
            "current_period_end": subscription.current_period_end,
        },
    }


@router.post("/api/checkout")
def create_checkout(payload: CheckoutRequest, request: Request, workspace=Depends(current_workspace)) -> dict:
    user, organization = _owner(workspace)
    if payload.plan not in PRICE_ENV:
        raise HTTPException(status_code=400, detail="Choose the Growth or Scale plan")
    price_id = os.getenv(PRICE_ENV[payload.plan])
    if not price_id:
        raise HTTPException(status_code=503, detail=f"{payload.plan.title()} checkout is not configured yet")
    _stripe_ready()
    base_url = str(request.base_url).rstrip("/")
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=organization.billing_customer_id or None,
        customer_email=None if organization.billing_customer_id else user.email,
        line_items=[{"price": price_id, "quantity": 1}],
        allow_promotion_codes=True,
        client_reference_id=str(organization.id),
        metadata={"organization_id": str(organization.id), "plan": payload.plan},
        subscription_data={"metadata": {"organization_id": str(organization.id), "plan": payload.plan}},
        success_url=f"{base_url}/app?billing=success",
        cancel_url=f"{base_url}/app?billing=cancelled",
    )
    return {"checkout_url": session.url}


@router.post("/api/portal")
def create_portal(request: Request, workspace=Depends(current_workspace)) -> dict:
    _, organization = _owner(workspace)
    if not organization.billing_customer_id:
        raise HTTPException(status_code=409, detail="Start a subscription before opening billing management")
    _stripe_ready()
    session = stripe.billing_portal.Session.create(
        customer=organization.billing_customer_id,
        return_url=f"{str(request.base_url).rstrip('/')}/app",
    )
    return {"portal_url": session.url}


def _sync_subscription(db: Session, subscription: dict) -> None:
    if hasattr(subscription, "to_dict"):
        subscription = subscription.to_dict()
    metadata = subscription.get("metadata") or {}
    organization_id = metadata.get("organization_id")
    plan = metadata.get("plan")
    if not organization_id or plan not in PRICE_ENV:
        return
    organization = db.get(Organization, int(organization_id))
    if not organization:
        return
    status = subscription.get("status", "incomplete")
    active = status in {"active", "trialing"}
    organization.plan = plan if active else "trial"
    organization.subscription_status = status
    organization.billing_customer_id = str(subscription.get("customer"))
    record = db.scalar(select(BillingSubscription).where(BillingSubscription.organization_id == organization.id))
    if not record:
        record = BillingSubscription(organization_id=organization.id)
        db.add(record)
    record.stripe_subscription_id = subscription.get("id")
    items = ((subscription.get("items") or {}).get("data") or [])
    record.stripe_price_id = ((items[0].get("price") or {}).get("id")) if items else None
    record.plan = organization.plan
    record.status = status
    period_end = subscription.get("current_period_end")
    record.current_period_end = datetime.utcfromtimestamp(period_end) if period_end else None


@router.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict:
    secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not secret or not stripe_signature:
        raise HTTPException(status_code=503, detail="Webhook verification is not configured")
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    if db.scalar(select(ProcessedBillingEvent).where(ProcessedBillingEvent.stripe_event_id == event["id"])):
        return {"received": True, "duplicate": True}
    if event["type"] in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
        _sync_subscription(db, event["data"]["object"])
    db.add(ProcessedBillingEvent(stripe_event_id=event["id"], event_type=event["type"]))
    db.commit()
    return {"received": True}
