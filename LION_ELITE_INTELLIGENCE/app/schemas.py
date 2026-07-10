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
