"""Campaigns and editable ICP criteria.

`scoring.calculate_score` encodes one audience in Python: personal trainers at
30, gyms at 25, recovery studios at 30. That is the coaching audience. Lion
Elite Clinical sells research supply to wellness, weight-management, TRT and
regenerative-medicine clinics — and under that scorer a TRT clinic falls through
to the unknown-category default of 10 while a gym scores 25. The weights are not
slightly off for this campaign, they are inverted.

A hardcoded scorer also cannot be two things at once, and the point of
BuildPipeline is that each workspace brings its own definition of a good
prospect. So ICP criteria live in the database, per campaign, per tenant.

Scoring returns **reasons alongside the number**. A score of 72 tells an
operator nothing about whether to trust it; "category wellness clinic +28,
has email +15, in target geography +10, no decision-maker named −0" tells them
what to fix. It is also what Phase 6's qualification explanations are built
from, so the reasons are produced here rather than reconstructed later by
something guessing at the arithmetic.

`scoring.calculate_score` is left alone. It is the fallback when a lead has no
campaign, and changing it would silently re-score every existing lead.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.types import JSON

from .database import Base, get_db
from .saas import Organization
from .security import require_admin_key
from .tenancy import OrganizationScope, resolve_organization_id

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

# Shape of the `icp` document. Stored as JSON rather than columns because a
# workspace defines fit in its own terms and a schema migration per customer is
# not a product.
DEFAULT_ICP: dict = {
    # category -> points. The primary signal, and the one the legacy scorer got
    # wrong for this campaign.
    "category_weights": {},
    # Points for having a reachable contact. A prospect nobody can contact is
    # not a prospect, whatever else it scores.
    "signal_weights": {
        "public_email": 15,
        "public_phone": 15,
        "owner_name": 15,
        "website": 10,
    },
    # Two-letter state codes. Empty means geography is not a criterion, which is
    # different from "no states match" — see `evaluate_icp`.
    "target_states": [],
    "geography_weight": 10,
    # Substrings that disqualify outright, whatever the rest of the score. The
    # list exists because a category tag is coarse: `clinic` covers an
    # aesthetics practice and a paediatric urgent care equally.
    "exclude_terms": [],
    # Unknown category floor. Deliberately low: an unrecognised category is an
    # unknown, and treating unknowns as mid-fit is how a list fills with rows
    # nobody converts.
    "unknown_category_points": 5,
    # At or above this, a lead is "qualified". Editable because the right
    # threshold depends on how much volume a workspace can work.
    "qualified_at": 70,
}

# Seed criteria for the first workspace. Not hardcoded behaviour — a starting
# row an operator edits. The weights reflect who actually buys research-grade
# supply: hormone and regenerative practices first, general aesthetics lower,
# and fitness businesses absent because they are not buyers for this offer.
LION_ELITE_CLINICAL_ICP: dict = {
    **DEFAULT_ICP,
    "category_weights": {
        "hormone clinic": 35,
        "trt clinic": 35,
        "regenerative medicine": 35,
        "longevity clinic": 32,
        "weight management": 30,
        "wellness clinic": 30,
        "functional medicine": 30,
        "iv therapy": 28,
        "med spa": 25,
        "medical spa": 25,
        "aesthetics": 22,
        "clinic": 15,
    },
    "target_states": ["FL", "TX", "AZ", "CA", "OH"],
    "exclude_terms": [
        # Practices this campaign must not contact about research supply. The
        # same list the BuildPipeline clinic targeting enforces, kept here so the
        # CRM refuses them even if a different sourcing path is added later.
        "pregnancy", "prenatal", "maternity", "obstetric", "preterm",
        "pediatric", "paediatric", "children", "veterinar",
        "dialysis", "oncolog", "hospice", "urgent care", "dental",
        "behavioral health", "autism", "plasma",
    ],
    # Calibrated against what a publicly-sourced clinic actually carries, not
    # chosen round. The weights top out at 100 (category 35 + four signals 55 +
    # geography 10), so a threshold of 70 demands a top category plus three of
    # four contact signals. Most clinics sourced from public listings publish
    # one contact point, so 70 marked a hormone clinic in Florida with a
    # published email — 35 + 15 + 10 = 60 — as unqualified. That is a prospect
    # worth a human's attention, and a threshold that rejects it produces an
    # empty qualified list and looks like a sourcing problem.
    #
    # 60 is the floor where a prospect is in a target category, in a target
    # state, and reachable. Below that it is missing one of those three.
    "qualified_at": 60,
}


class Campaign(Base):
    __tablename__ = "gtm_campaigns_lei"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_campaign_org_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    objective: Mapped[str] = mapped_column(String(80), default="book_meetings")
    icp: Mapped[dict] = mapped_column(JSON, default=dict)
    # Day offsets for the follow-up cadence. Configurable per campaign because
    # the right spacing differs by audience, and a cadence in code cannot be
    # tuned from conversion data.
    sequence_days: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CampaignIn(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=120, pattern=r"^[a-z0-9][a-z0-9-]*$")
    objective: str = "book_meetings"
    status: str = "draft"
    icp: dict | None = None
    sequence_days: list[int] | None = None


class CampaignUpdate(BaseModel):
    name: str | None = None
    status: str | None = None
    objective: str | None = None
    icp: dict | None = None
    sequence_days: list[int] | None = None


def merged_icp(icp: dict | None) -> dict:
    """Fill absent keys from the default.

    A caller editing one weight should not have to resend the whole document,
    and a partial ICP must not silently drop geography or the exclusion list —
    a missing `exclude_terms` would start admitting paediatric practices.
    """
    merged = {**DEFAULT_ICP, **(icp or {})}
    merged["signal_weights"] = {**DEFAULT_ICP["signal_weights"], **(merged.get("signal_weights") or {})}
    return merged


def evaluate_icp(lead: dict, icp: dict | None = None) -> dict:
    """Score a prospect against a campaign's ICP, with the reasons.

    Returns `{score, qualified, excluded, reasons}`. `excluded` is separate from
    a zero score on purpose: "scored badly" and "must not be contacted" need
    different handling downstream, and collapsing them loses the distinction at
    the one point where it matters most.
    """
    criteria = merged_icp(icp)
    haystack = " ".join(
        str(lead.get(field) or "") for field in ("company_name", "category", "notes", "website")
    ).lower()

    for term in criteria.get("exclude_terms") or []:
        if term and term.lower() in haystack:
            return {
                "score": 0,
                "qualified": False,
                "excluded": True,
                "reasons": [f"excluded: matches '{term}'"],
            }

    score = 0
    reasons: list[str] = []

    category = (lead.get("category") or "").strip().lower()
    weights = criteria.get("category_weights") or {}
    # Longest match wins, so "medical spa" is not scored by a looser "spa" entry
    # that happens to be checked first.
    matched = sorted((key for key in weights if key and key in category), key=len, reverse=True)
    if matched:
        points = int(weights[matched[0]])
        score += points
        reasons.append(f"category '{matched[0]}' +{points}")
    else:
        points = int(criteria.get("unknown_category_points", 5))
        score += points
        reasons.append(f"category '{category or 'unspecified'}' unrecognised +{points}")

    for field, points in (criteria.get("signal_weights") or {}).items():
        if lead.get(field):
            score += int(points)
            reasons.append(f"has {field} +{points}")
        else:
            reasons.append(f"no {field} +0")

    target_states = [state.upper() for state in (criteria.get("target_states") or []) if state]
    if target_states:
        state = (lead.get("state") or "").strip().upper()
        if state and state in target_states:
            points = int(criteria.get("geography_weight", 0))
            score += points
            reasons.append(f"in target geography ({state}) +{points}")
        else:
            reasons.append(f"outside target geography ({state or 'unknown'}) +0")

    score = max(0, min(score, 100))
    return {
        "score": score,
        "qualified": score >= int(criteria.get("qualified_at", 70)),
        "excluded": False,
        "reasons": reasons,
    }


def serialize(campaign: Campaign) -> dict:
    return {
        "id": campaign.id,
        "organization_id": campaign.organization_id,
        "name": campaign.name,
        "slug": campaign.slug,
        "status": campaign.status,
        "objective": campaign.objective,
        "icp": campaign.icp,
        "sequence_days": campaign.sequence_days,
    }


@router.get("")
def list_campaigns(
    db: Session = Depends(get_db),
    organization_id: int | None = Depends(OrganizationScope),
) -> list[dict]:
    org = resolve_organization_id(db, organization_id)
    if org is None:
        return []
    rows = db.scalars(
        select(Campaign).where(Campaign.organization_id == org).order_by(Campaign.created_at.desc())
    ).all()
    return [serialize(row) for row in rows]


@router.post("", dependencies=[Depends(require_admin_key)], status_code=201)
def create_campaign(
    payload: CampaignIn,
    db: Session = Depends(get_db),
    organization_id: int | None = Depends(OrganizationScope),
) -> dict:
    org = resolve_organization_id(db, organization_id)
    if org is None:
        raise HTTPException(status_code=400, detail="No organization to attach the campaign to")

    existing = db.scalar(
        select(Campaign).where(Campaign.organization_id == org, Campaign.slug == payload.slug)
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"Campaign '{payload.slug}' already exists")

    campaign = Campaign(
        organization_id=org,
        name=payload.name,
        slug=payload.slug,
        status=payload.status,
        objective=payload.objective,
        icp=merged_icp(payload.icp),
        sequence_days=payload.sequence_days or [0, 2, 5, 10, 21],
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return serialize(campaign)


@router.patch("/{campaign_id}", dependencies=[Depends(require_admin_key)])
def update_campaign(
    campaign_id: int,
    payload: CampaignUpdate,
    db: Session = Depends(get_db),
    organization_id: int | None = Depends(OrganizationScope),
) -> dict:
    org = resolve_organization_id(db, organization_id)
    campaign = db.get(Campaign, campaign_id)
    # Another tenant's campaign reads as absent, same rule as leads: a 403 would
    # confirm the id exists.
    if not campaign or campaign.organization_id != org:
        raise HTTPException(status_code=404, detail="Campaign not found")

    data = payload.model_dump(exclude_unset=True)
    if "icp" in data and data["icp"] is not None:
        # Merged, not replaced, so editing one weight cannot drop the exclusion
        # list and start admitting practices this campaign must not contact.
        data["icp"] = merged_icp({**(campaign.icp or {}), **data["icp"]})
    for field, value in data.items():
        setattr(campaign, field, value)

    db.commit()
    db.refresh(campaign)
    return serialize(campaign)


class ScoreRequest(BaseModel):
    company_name: str | None = None
    category: str | None = None
    state: str | None = None
    public_email: str | None = None
    public_phone: str | None = None
    owner_name: str | None = None
    website: str | None = None
    notes: str | None = None


@router.post("/{campaign_id}/score")
def score_against_campaign(
    campaign_id: int,
    payload: ScoreRequest,
    db: Session = Depends(get_db),
    organization_id: int | None = Depends(OrganizationScope),
) -> dict:
    """Score a prospect against this campaign's criteria.

    Exposed so BuildPipeline scores through the campaign rather than in the
    browser. Client-side scoring cannot be audited, cannot be tuned from
    conversion data, and differs per deployment.
    """
    org = resolve_organization_id(db, organization_id)
    campaign = db.get(Campaign, campaign_id)
    if not campaign or campaign.organization_id != org:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return evaluate_icp(payload.model_dump(), campaign.icp)


def seed_lion_elite_clinical(db: Session) -> Campaign | None:
    """Create the first workspace's campaign if it is absent.

    Idempotent, and scoped to the Lion Elite Clinical organization by slug
    rather than by id, so it cannot attach itself to whichever organization
    happens to be first.
    """
    org = db.scalar(select(Organization).where(Organization.slug == "lion-elite-clinical"))
    if org is None:
        return None

    existing = db.scalar(
        select(Campaign).where(
            Campaign.organization_id == org.id, Campaign.slug == "clinical-research-supply"
        )
    )
    if existing:
        return existing

    campaign = Campaign(
        organization_id=org.id,
        name="Clinical Research Supply",
        slug="clinical-research-supply",
        status="draft",
        objective="book_meetings",
        icp=LION_ELITE_CLINICAL_ICP,
        sequence_days=[0, 2, 5, 10, 21],
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign
