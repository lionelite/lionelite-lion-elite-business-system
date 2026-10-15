"""Tenant isolation on CRM reads.

`organization_id` was added to the tables and the write path, but the read
endpoints did not filter on it. Scoped writes with unscoped reads is not partial
tenancy, it is no tenancy — so these tests assert the reads, which is where the
leak actually was.

The behaviour that needs pinning is the ambiguous case. With one organization
the endpoints resolve it implicitly, which is what keeps the six existing
dashboards working. With two, omitting `organization_id` must be an error rather
than a guess, because guessing is what hands one customer another's prospects.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

_DB_FILE = Path(tempfile.mkdtemp()) / "tenancy_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE}"
os.environ["LEI_ADMIN_API_KEY"] = "test-admin-key"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Lead  # noqa: E402
from app.saas import Organization  # noqa: E402

AUTH = {"X-LEI-Admin-Key": "test-admin-key"}


def reset(org_count: int) -> list[int]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    ids: list[int] = []
    with SessionLocal() as db:
        for index in range(org_count):
            org = Organization(name=f"Tenant {index}", slug=f"tenant-{index}")
            db.add(org)
            db.flush()
            ids.append(org.id)
        db.commit()
    return ids


def seed_lead(org_id: int, name: str, score: int = 90, status: str = "new") -> int:
    with SessionLocal() as db:
        lead = Lead(
            organization_id=org_id, company_name=name, category="med-spa",
            public_email=f"{name.lower().replace(' ', '')}@example.com",
            score=score, status=status,
        )
        db.add(lead)
        db.commit()
        return lead.id


@pytest.fixture
def client():
    return TestClient(app)


# --- single tenant: existing callers keep working ------------------------


def test_one_organization_resolves_implicitly(client):
    # The six dashboards in production pass no organization_id. They must keep
    # working, which is the whole reason resolution is implicit at count == 1.
    (org,) = reset(1)
    seed_lead(org, "Glow Med Spa")

    leads = client.get("/leads").json()
    stats = client.get("/stats").json()

    assert len(leads) == 1
    assert stats["total_leads"] == 1
    assert stats["organization_id"] == org, "the response says which tenant it answered for"


# --- two tenants: the isolation guarantee -------------------------------


def test_each_tenant_sees_only_its_own_leads(client):
    first, second = reset(2)
    seed_lead(first, "First Tenant Spa")
    seed_lead(second, "Second Tenant Spa")

    first_names = {lead["company_name"] for lead in client.get(f"/leads?organization_id={first}").json()}
    second_names = {lead["company_name"] for lead in client.get(f"/leads?organization_id={second}").json()}

    assert first_names == {"First Tenant Spa"}
    assert second_names == {"Second Tenant Spa"}


def test_omitting_the_tenant_is_refused_once_there_are_two(client):
    # Fails closed. The alternative — returning everything — is the leak, and it
    # would look like a working endpoint.
    first, second = reset(2)
    seed_lead(first, "First Tenant Spa")
    seed_lead(second, "Second Tenant Spa")

    for path in ("/leads", "/stats", "/exports/leads.csv"):
        response = client.get(path)
        assert response.status_code == 400, f"{path} must refuse an ambiguous tenant"
        assert "organization_id is required" in response.text


def test_aggregates_do_not_count_another_tenants_rows(client):
    # A wrong count leaks as a number rather than as a record, which is why it
    # survives review more easily than a wrong list.
    first, second = reset(2)
    seed_lead(first, "First A")
    seed_lead(second, "Second A")
    seed_lead(second, "Second B")

    assert client.get(f"/stats?organization_id={first}").json()["total_leads"] == 1
    assert client.get(f"/stats?organization_id={second}").json()["total_leads"] == 2


def test_csv_export_is_scoped(client):
    # One request would otherwise walk out with every customer's contact list.
    first, second = reset(2)
    seed_lead(first, "First Tenant Spa")
    seed_lead(second, "Second Tenant Spa")

    body = client.get(f"/exports/leads.csv?organization_id={first}").text
    assert "First Tenant Spa" in body
    assert "Second Tenant Spa" not in body


# --- single-record access ------------------------------------------------


def test_another_tenants_lead_reads_as_absent_not_forbidden(client):
    # 404 rather than 403: a 403 confirms the id exists, which lets one customer
    # enumerate another's record ids.
    first, second = reset(2)
    other_lead = seed_lead(second, "Second Tenant Spa")

    response = client.get(f"/leads/{other_lead}?organization_id={first}")
    assert response.status_code == 404
    assert "Lead not found" in response.text


def test_a_tenant_cannot_patch_another_tenants_lead(client):
    first, second = reset(2)
    other_lead = seed_lead(second, "Second Tenant Spa")

    response = client.patch(
        f"/leads/{other_lead}?organization_id={first}", json={"do_not_contact": True}
    )
    assert response.status_code == 404

    with SessionLocal() as db:
        assert db.get(Lead, other_lead).do_not_contact is False, "the record is untouched"


def test_a_tenant_can_patch_its_own_lead(client):
    (org,) = reset(1)
    lead_id = seed_lead(org, "Glow Med Spa")

    response = client.patch(f"/leads/{lead_id}", json={"status": "contacted"})
    assert response.status_code == 200
    assert response.json()["status"] == "contacted"


def test_an_unknown_organization_is_a_404_not_an_empty_list(client):
    # A caller naming a tenant that is not there has a bug worth surfacing, not
    # an empty result worth hiding.
    reset(2)
    assert client.get("/leads?organization_id=999999").status_code == 404


# --- the empty-database edge --------------------------------------------


def test_no_organizations_reads_as_empty_not_unrestricted(client):
    # With no tenant resolvable, `scoped()` matches nothing. Treating that as
    # "skip the filter" is the bug the helper exists to prevent, so an ownerless
    # row stays invisible.
    reset(0)
    with SessionLocal() as db:
        db.add(Lead(organization_id=None, company_name="Orphan Spa", category="med-spa", score=90))
        db.commit()

    assert client.get("/leads").json() == []
    assert client.get("/stats").json()["total_leads"] == 0
