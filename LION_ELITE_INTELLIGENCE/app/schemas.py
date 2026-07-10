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
    status: str | None = None
    notes: str | None = None
    do_not_contact: bool | None = None


class LeadRead(LeadCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    score: int
    status: str
    do_not_contact: bool
    created_at: datetime
    updated_at: datetime


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
