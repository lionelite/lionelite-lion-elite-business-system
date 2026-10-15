from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LeadCreate(BaseModel):
    company_name: str = Field(min_length=2, max_length=255)
    owner_name: str | None = None
    category: str
    city: str | None = None
    state: str | None = None
    website: str | None = None
    public_phone: str | None = None
    public_email: EmailStr | None = None
    linkedin_url: str | None = None
    instagram_url: str | None = None
    source_url: str | None = None
    partnership_angle: str | None = None
    notes: str | None = None


class LeadUpdate(BaseModel):
    # `extra="forbid"` because the alternative is what actually happened: the
    # UI sent `{"stage": "Call Booked", "score": 70}`, `score` was not a field
    # here, Pydantic dropped it, and PATCH answered 200. A half-applied update
    # reported as success is worse than a rejected one, because nothing
    # downstream can tell the difference.
    model_config = ConfigDict(extra="forbid")

    status: str | None = None
    notes: str | None = None
    # Scored against the campaign ICP by the caller. Writable because the score
    # is a judgement about fit, not a derived column — and a score computed and
    # then discarded means the qualified list cannot be filtered on it.
    score: int | None = Field(default=None, ge=0, le=100)
    # One-way. Settable to True, never back to False — see `update_lead`.
    do_not_contact: bool | None = None


class LeadRead(LeadCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    score: int
    status: str
    do_not_contact: bool
    created_at: datetime
    updated_at: datetime
    # Tenancy and provenance. Stored on the model but previously absent from
    # this response, so a caller could not tell which workspace a lead belonged
    # to, nor whether it was sourced by BuildPipeline or entered by a human —
    # which made every synced lead read back as "manual" in the UI.
    organization_id: int | None = None
    source_system: str | None = None
    external_id: str | None = None


class OpportunityCreate(BaseModel):
    lead_id: int
    stage: str = "new"
    assigned_rep: str | None = None
    partnership_type: str | None = None
    estimated_annual_value: float = Field(default=0, ge=0)
    next_follow_up_at: datetime | None = None
    meeting_at: datetime | None = None
    notes: str | None = None


class OpportunityUpdate(BaseModel):
    stage: str | None = None
    assigned_rep: str | None = None
    partnership_type: str | None = None
    estimated_annual_value: float | None = Field(default=None, ge=0)
    last_contact_at: datetime | None = None
    next_follow_up_at: datetime | None = None
    meeting_at: datetime | None = None
    proposal_sent_at: datetime | None = None
    closed_at: datetime | None = None
    loss_reason: str | None = None
    notes: str | None = None


class OpportunityRead(OpportunityCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    last_contact_at: datetime | None = None
    proposal_sent_at: datetime | None = None
    closed_at: datetime | None = None
    loss_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class PipelineCard(BaseModel):
    opportunity_id: int
    lead_id: int
    company_name: str
    owner_name: str | None
    public_phone: str | None
    public_email: str | None
    category: str
    city: str | None
    state: str | None
    score: int
    stage: str
    assigned_rep: str | None
    partnership_type: str | None
    estimated_annual_value: float
    next_follow_up_at: datetime | None
    last_contact_at: datetime | None
