"""Inbound replies: record one, and make the classification binding.

`sdr.classify_reply` decides what a reply means. This decides what happens to
the lead as a result, and that split is the point — a classification nothing
acts on is a log line, and "never continue an automated sequence after an
explicit opt-out" has to be a property of the stored record, not of whichever
code path happens to read the classification next.

So suppression is written to the lead (`do_not_contact`), not held in the
response. Anything that sends consults the lead, which means a sender that has
never heard of this module still cannot email someone who opted out.

Three rules carry the weight:

1. **Suppression is one-way.** `do_not_contact` is only ever set, never
   cleared. A later cheerful reply from the same address does not reinstate
   consent — a person who asked to be left alone and then answered a colleague's
   forward has not re-subscribed, and the one-way flag is what stops a
   misclassification two months from now from undoing a withdrawal.
2. **The response reports what was written, not what was advised.** `suppressed`
   and `sequence_stopped` describe the lead's state after the write. A field
   that reported the recommendation would read identically on a reply that was
   recorded and one that was rejected.
3. **An auto-reply changes nothing.** It carries no intent, so it neither
   suppresses nor advances the stage, and it is still recorded — the record is
   how "we emailed them four times and they were on leave" is visible later.

Recording a reply is deliberately **not** idempotent on text: two identical
"unsubscribe" messages are two real events and both belong in the timeline.
What is idempotent is the effect — the second one finds the lead already
suppressed and leaves it suppressed.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from sqlalchemy.orm import Session

from .activities import LeadActivity
from .campaigns import Campaign, evaluate_icp
from .database import get_db
from .models import Lead
from .sdr import classify_reply, qualification_summary, recommended_next_action
from .tenancy import OrganizationScope, lead_in_scope, resolve_organization_id

router = APIRouter(prefix="/sdr", tags=["sdr"])

# Intent -> the stage the lead moves to. Absent means the stage is left alone,
# which is the correct handling for an auto-reply and for anything unclassified:
# moving a lead on the strength of a reply we could not read is how a pipeline
# reports progress that did not happen.
STAGE_FOR_INTENT: dict[str, str] = {
    "opt_out": "do_not_contact",
    "legal_escalation": "do_not_contact",
    "interested": "replied",
    "objection": "replied",
    "not_interested": "lost",
}

# Intents that withdraw permission to contact. A legal demand is included: it is
# not a tidy unsubscribe, but it certainly is not permission to keep sending.
SUPPRESSING_INTENTS = frozenset({"opt_out", "legal_escalation"})

# How long to wait before the next touch when the sequence has NOT stopped. Only
# reachable for an auto-reply, which is the one classification that means
# "nobody has read this yet".
AUTO_REPLY_RETRY_DAYS = 3


def apply_reply_to_lead(lead: Lead, reply: dict, now: datetime | None = None) -> dict:
    """Mutate `lead` according to a classified reply. Does not commit.

    Returns what was actually changed, so a caller can report the write rather
    than the recommendation. Takes the classification as an argument instead of
    the text so the decision and the effect stay separable and separately
    testable.
    """
    moment = now or datetime.utcnow()
    intent = reply.get("intent")
    changed: dict = {"suppressed": False, "stage_changed": None}

    if intent in SUPPRESSING_INTENTS and not lead.do_not_contact:
        lead.do_not_contact = True
        changed["suppressed"] = True

    stage = STAGE_FOR_INTENT.get(intent)
    # A suppressed lead's stage is never moved off do_not_contact by a later
    # reply, so the pipeline cannot show a contact as live again once they are
    # out.
    if lead.do_not_contact:
        stage = "do_not_contact"
    if stage and lead.status != stage:
        changed["stage_changed"] = stage
        lead.status = stage

    lead.updated_at = moment
    return changed


def _next_follow_up(reply: dict, now: datetime) -> datetime | None:
    """When to touch this lead again — None when the sequence has stopped.

    Keyed on `stop_sequence` rather than on the intent name so a classification
    added later cannot fall through into "schedule another email".
    """
    if reply.get("stop_sequence", True):
        return None
    return now + timedelta(days=AUTO_REPLY_RETRY_DAYS)


class ReplyIn(BaseModel):
    text: str | None = Field(default=None, description="The raw reply body.")
    received_at: datetime | None = None
    # Free-form provenance (a mailbox, a form, a forwarded thread) kept on the
    # activity so a disputed suppression can be traced to its source.
    channel: str = Field(default="email", max_length=50)


class ClassifyIn(BaseModel):
    text: str | None = None


@router.post("/classify")
def classify_only(payload: ClassifyIn) -> dict:
    """Classify a reply without touching any record.

    Separate from recording on purpose: this is for previewing the rules, and a
    preview endpoint that quietly suppressed a contact would be a trap.
    """
    return {"classification": classify_reply(payload.text), "applied": False}


@router.post("/leads/{lead_id}/replies", status_code=201)
def record_reply(
    lead_id: int,
    payload: ReplyIn,
    db: Session = Depends(get_db),
    organization_id: int | None = Depends(OrganizationScope),
) -> dict:
    lead = lead_in_scope(db, lead_id, organization_id)
    received = payload.received_at or datetime.utcnow()

    reply = classify_reply(payload.text)
    changed = apply_reply_to_lead(lead, reply, now=received)

    activity = LeadActivity(
        lead_id=lead.id,
        activity_type="reply",
        outcome=f"reply_{reply['intent']}",
        notes=(payload.text or "")[:2000] or None,
        next_follow_up_at=_next_follow_up(reply, received),
        created_at=received,
    )
    db.add(activity)
    db.commit()
    db.refresh(lead)

    return {
        "lead_id": lead.id,
        "activity_id": activity.id,
        "classification": reply,
        # The lead's state after the write, not the advice. `sequence_stopped`
        # is true whenever nothing further is scheduled, including when the lead
        # was already suppressed before this reply arrived.
        "suppressed": bool(lead.do_not_contact),
        "suppressed_by_this_reply": changed["suppressed"],
        "sequence_stopped": activity.next_follow_up_at is None,
        "stage": lead.status,
        "stage_changed": changed["stage_changed"],
        "next_action": recommended_next_action(lead.status, reply),
    }


@router.get("/leads/{lead_id}/brief")
def lead_brief(
    lead_id: int,
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
    organization_id: int | None = Depends(OrganizationScope),
) -> dict:
    """Everything a person needs before touching this lead.

    The ICP breakdown needs a campaign, because fit is defined per campaign.
    Without one this says so rather than scoring against a default and
    presenting the result as if it meant something for this prospect.
    """
    lead = lead_in_scope(db, lead_id, organization_id)
    org = resolve_organization_id(db, organization_id)

    lead_dict = {
        "company_name": lead.company_name,
        "category": lead.category,
        "city": lead.city,
        "state": lead.state,
        "website": lead.website,
        "public_email": lead.public_email,
        "public_phone": lead.public_phone,
        "owner_name": lead.owner_name,
        # Carried into the summary so permission is stated ahead of fit.
        "do_not_contact": bool(lead.do_not_contact),
    }

    qualification: dict | None = None
    if campaign_id is not None:
        campaign = db.get(Campaign, campaign_id)
        if not campaign or campaign.organization_id != org:
            raise HTTPException(status_code=404, detail="Campaign not found")
        evaluation = evaluate_icp(lead_dict, campaign.icp)
        qualification = {
            "campaign_id": campaign.id,
            "summary": qualification_summary(evaluation, lead_dict),
            **evaluation,
        }

    last_reply = db.scalar(
        select(LeadActivity)
        .where(LeadActivity.lead_id == lead.id, LeadActivity.activity_type == "reply")
        .order_by(LeadActivity.created_at.desc())
        .limit(1)
    )
    reply = classify_reply(last_reply.notes) if last_reply else None

    return {
        "lead_id": lead.id,
        "company": lead.company_name,
        "stage": lead.status,
        "score": lead.score,
        "do_not_contact": bool(lead.do_not_contact),
        "contactable": not lead.do_not_contact,
        "qualification": qualification,
        "qualification_unavailable": None
        if qualification
        else "No campaign_id supplied; fit is defined per campaign, so no ICP breakdown is shown.",
        "last_reply": None
        if not last_reply
        else {
            "received_at": last_reply.created_at,
            "outcome": last_reply.outcome,
            "classification": reply,
        },
        "next_action": recommended_next_action(lead.status, reply),
    }
