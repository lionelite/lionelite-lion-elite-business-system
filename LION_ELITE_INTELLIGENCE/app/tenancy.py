"""Tenant resolution for CRM reads.

`organization_id` was added to `leads` and `opportunities`, but the read
endpoints did not filter on it — so writes were scoped and reads were not.
Scoped writes with unscoped reads is not partial tenancy, it is no tenancy: the
moment a second organization exists, `GET /leads` hands every one of its
prospects to the first customer who asks.

The leak is latent today because exactly one organization exists, which is why
this closes it now rather than after a second signup makes it urgent.

The hard part is doing it without breaking the six dashboards already in
production, none of which pass an organization. So resolution is:

* An explicit `organization_id` is validated and used.
* Omitted, with exactly one organization in the database — the situation today —
  resolves to that one. Existing callers keep working unchanged.
* Omitted, with more than one organization, is a **400**. It does not pick one
  and it does not return everything. An ambiguous tenant is the case where
  guessing leaks data across customers, so it fails closed, and the error names
  the parameter the caller has to start sending.
* Omitted with no organizations at all resolves to `None`, which callers treat
  as "match nothing" rather than "match everything" — an empty database should
  read as empty, not as unrestricted.

That last distinction is the one worth keeping straight. Everywhere below,
`None` means no tenant could be resolved, and a query filtered on it must return
nothing. Treating it as "skip the filter" is exactly the bug this module exists
to prevent.
"""

from __future__ import annotations

from fastapi import HTTPException, Query
from sqlalchemy import false, func, select
from sqlalchemy.orm import Session

from .models import Lead
from .saas import Organization


def organization_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Organization)) or 0


def resolve_organization_id(db: Session, requested: int | None) -> int | None:
    """Return the organization a request should be scoped to.

    Raises 400 when the tenant is ambiguous, and 404 when an explicitly
    requested organization does not exist — a caller naming a tenant that is not
    there has a bug worth surfacing, not an empty result worth hiding.
    """
    if requested is not None:
        exists = db.scalar(select(Organization.id).where(Organization.id == requested))
        if exists is None:
            raise HTTPException(status_code=404, detail=f"Unknown organization_id: {requested}")
        return int(exists)

    count = organization_count(db)
    if count == 0:
        return None
    if count == 1:
        return int(db.scalar(select(func.min(Organization.id))))

    raise HTTPException(
        status_code=400,
        detail=(
            "More than one organization exists, so organization_id is required. "
            "Omitting it would return another customer's records."
        ),
    )


def OrganizationScope(  # noqa: N802 - used as a FastAPI dependency, named like one
    organization_id: int | None = Query(
        default=None,
        description="Tenant to scope results to. Required once more than one organization exists.",
    ),
) -> int | None:
    """Carry the requested organization through as a dependency.

    Deliberately does not touch the database: resolution needs a session, and
    taking one here would open a second connection per request. Endpoints call
    `resolve_organization_id` with their own session.
    """
    return organization_id


def scoped(stmt, model, organization_id: int | None):
    """Apply the tenant filter to a select statement.

    When `organization_id` is None no tenant was resolved, so this matches
    nothing. The alternative — returning the statement unfiltered — is the
    data-leak path, and it is the one a reader expects, which is why this is a
    named helper rather than an inline `if`.
    """
    if organization_id is None:
        return stmt.where(false())
    return stmt.where(model.organization_id == organization_id)


def lead_in_scope(db: Session, lead_id: int, organization_id: int | None) -> Lead:
    """Fetch a lead, treating another tenant's record as absent.

    404 rather than 403 on purpose: a 403 confirms the id exists, which lets one
    customer enumerate another's record ids by walking the range.

    Lives here rather than in `main` so every router scopes single-record access
    the same way. It was in `main` while `main` was the only module doing it,
    and `activities` — which reads a lead's notes and its owner's phone number —
    did not do it at all.
    """
    lead = db.get(Lead, lead_id)
    org = resolve_organization_id(db, organization_id)
    if not lead or lead.organization_id != org:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead
