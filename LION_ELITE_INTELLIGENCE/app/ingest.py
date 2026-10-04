"""BuildPipeline → CRM ingest.

The CRM is the system of record. BuildPipeline is top-of-funnel: it sources and
qualifies, then hands records over. This is the one seam between them.

Deliberately a separate endpoint rather than a change to `POST /leads`:

* `/leads` raises 409 on a duplicate, which is correct for a human entering a
  record by hand — it stops a second copy being created by accident. It is wrong
  for a sync, where seeing the same prospect twice is normal and the second
  sighting usually carries *more* information than the first. A sync that 409s
  cannot re-run, so a transient failure becomes a permanent gap.
* `/leads` has no authentication. Changing that in place would break whatever
  already calls it. This endpoint requires the admin key from the start.

Three rules carry the merge, and each exists because the naive version loses
data:

1. **Never overwrite with nothing.** BuildPipeline's view of a prospect is
   partial — it may know an email and not a phone. A plain field copy would
   write null over a phone number a human researched. Only empty CRM fields are
   filled.
2. **Dedup on email first, then domain, then name+state.** Email is the only
   key that identifies a person; a domain identifies a company, which is the
   right fallback but will merge two contacts at one clinic, so it is second.
   Name+state is last and matches only when there is nothing better.
3. **`do_not_contact` is one-way.** A lead marked DNC stays DNC. An import can
   enrich it but can never clear the flag, because the flag records a person's
   decision and the import does not know about it.
"""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Lead
from .saas import Organization
from .scoring import calculate_score
from .security import require_admin_key

router = APIRouter(prefix="/ingest", tags=["ingest"])

SOURCE_SYSTEM = "buildpipeline"

# Fields an import may fill when the CRM's copy is empty. `status`,
# `do_not_contact` and `score` are excluded on purpose: those are CRM state,
# owned by the people and processes working the record, not by whatever sourced
# it.
MERGEABLE_FIELDS = (
    "owner_name",
    "city",
    "state",
    "website",
    "public_phone",
    "public_email",
    "linkedin_url",
    "instagram_url",
    "source_url",
    "partnership_angle",
)


class ProspectIn(BaseModel):
    """A BuildPipeline prospect, in CRM field names.

    Translation happens on the BuildPipeline side so the CRM's vocabulary stays
    canonical — if both ends translated, neither would be authoritative.
    """

    organization_id: int
    company_name: str = Field(min_length=2, max_length=255)
    category: str = Field(min_length=2, max_length=100)
    external_id: str | None = Field(default=None, max_length=255)
    owner_name: str | None = None
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


def normalise_domain(value: str | None) -> str | None:
    """Reduce a website to a bare domain for comparison.

    `https://www.Example.com/book?ref=x` and `example.com` are the same company
    and must dedupe against each other.
    """
    if not value:
        return None
    raw = str(value).strip().lower()
    if not raw:
        return None
    if "//" not in raw:
        raw = f"//{raw}"
    host = urlparse(raw).netloc or ""
    host = host.split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host or None


def is_blank(value: object) -> bool:
    """Treat whitespace-only strings as empty.

    An import that sends `" "` would otherwise count as a real value and block
    the field from ever being filled properly.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def find_existing(db: Session, payload: ProspectIn) -> Lead | None:
    """Locate the CRM's copy of this prospect, within its organization.

    Matching is scoped to the organization. Two tenants may legitimately both
    hold the same clinic as a prospect, and merging those records would leak one
    customer's research into another's CRM.
    """
    org_filter = Lead.organization_id == payload.organization_id

    # External id: the strongest key, because it is BuildPipeline's own handle
    # on the record and survives a company renaming itself.
    if payload.external_id:
        found = db.scalar(
            select(Lead).where(
                org_filter,
                Lead.source_system == SOURCE_SYSTEM,
                Lead.external_id == str(payload.external_id),
            )
        )
        if found:
            return found

    # Email identifies a person.
    if payload.public_email:
        found = db.scalar(
            select(Lead).where(
                org_filter,
                func.lower(Lead.public_email) == str(payload.public_email).lower(),
            )
        )
        if found:
            return found

    # Domain identifies a company. Compared normalised on both sides, so stored
    # values with a scheme or `www.` still match.
    domain = normalise_domain(payload.website)
    if domain:
        candidates = db.scalars(select(Lead).where(org_filter, Lead.website.is_not(None))).all()
        for candidate in candidates:
            if normalise_domain(candidate.website) == domain:
                return candidate

    # Name plus state, last. Name alone is too weak — clinic names repeat across
    # states and merging them would be worse than a duplicate.
    if payload.state:
        return db.scalar(
            select(Lead).where(
                org_filter,
                func.lower(Lead.company_name) == payload.company_name.lower(),
                func.lower(Lead.state) == str(payload.state).lower(),
            )
        )

    return None


def merge_into(existing: Lead, payload: ProspectIn) -> list[str]:
    """Fill empty CRM fields from the import. Returns the fields filled.

    Returning the field list rather than a boolean makes a sync auditable: the
    response says what the import actually contributed, so an import that
    "updated" 200 records while adding nothing is visible as such.
    """
    filled: list[str] = []
    incoming = payload.model_dump()

    for field in MERGEABLE_FIELDS:
        new_value = incoming.get(field)
        if is_blank(new_value):
            continue
        if not is_blank(getattr(existing, field, None)):
            continue
        setattr(existing, field, str(new_value))
        filled.append(field)

    # Notes append rather than replace: both sides write prose here, and a
    # replace would discard a human's note in favour of a generated one.
    if not is_blank(payload.notes):
        note = str(payload.notes).strip()
        if is_blank(existing.notes):
            existing.notes = note
            filled.append("notes")
        elif note not in existing.notes:
            existing.notes = f"{existing.notes}\n\n[buildpipeline] {note}"
            filled.append("notes")

    # Claim provenance only if the record had none, so an import never
    # relabels a lead a human entered.
    if is_blank(existing.source_system):
        existing.source_system = SOURCE_SYSTEM
        filled.append("source_system")
    if payload.external_id and is_blank(existing.external_id):
        existing.external_id = str(payload.external_id)
        filled.append("external_id")

    if filled:
        existing.score = calculate_score(
            {
                "category": existing.category,
                "public_email": existing.public_email,
                "public_phone": existing.public_phone,
                "website": existing.website,
                "city": existing.city,
                "state": existing.state,
            }
        )

    return filled


@router.post("/leads", dependencies=[Depends(require_admin_key)])
def ingest_leads(payload: list[ProspectIn], db: Session = Depends(get_db)) -> dict:
    """Idempotent upsert of BuildPipeline prospects into the CRM.

    Safe to replay: a second run of the same batch reports `updated` with no
    fields filled rather than creating duplicates or failing.
    """
    if not payload:
        return {"received": 0, "created": 0, "updated": 0, "unchanged": 0, "results": [], "errors": []}

    # Validate every organization referenced before writing anything, so a batch
    # naming a non-existent tenant fails whole rather than half-applying.
    org_ids = {item.organization_id for item in payload}
    known = set(db.scalars(select(Organization.id).where(Organization.id.in_(org_ids))).all())
    missing = sorted(org_ids - known)
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown organization_id(s): {missing}")

    created = updated = unchanged = 0
    results: list[dict] = []
    errors: list[dict] = []

    for index, item in enumerate(payload):
        try:
            existing = find_existing(db, item)
            if existing is None:
                data = item.model_dump()
                data["public_email"] = str(data["public_email"]) if data.get("public_email") else None
                data["source_system"] = SOURCE_SYSTEM
                data["score"] = calculate_score(data)
                lead = Lead(**data)
                db.add(lead)
                db.flush()
                created += 1
                results.append({"index": index, "action": "created", "lead_id": lead.id})
                continue

            filled = merge_into(existing, item)
            if filled:
                updated += 1
                results.append(
                    {"index": index, "action": "updated", "lead_id": existing.id, "fields": filled}
                )
            else:
                unchanged += 1
                results.append({"index": index, "action": "unchanged", "lead_id": existing.id})
        except Exception as exc:  # noqa: BLE001 - one bad row must not fail the batch
            errors.append({"index": index, "company_name": item.company_name, "error": str(exc)})

    db.commit()

    return {
        "received": len(payload),
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "results": results,
        "errors": errors,
    }
