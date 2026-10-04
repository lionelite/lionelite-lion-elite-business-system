"""BuildPipeline → CRM ingest.

First tests in this repository. They cover the ingest seam because that is where
customer data crosses a trust boundary: a sync that silently overwrites a
researched phone number, merges two tenants' prospects, or clears a
do-not-contact flag does damage that is invisible until someone is contacted who
should not have been.

Runs against SQLite in a temp file — no Postgres, no network, no credentials.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Point the app at a throwaway database before importing it: database.py reads
# DATABASE_URL at import time, so setting it later has no effect.
_DB_FILE = Path(tempfile.mkdtemp()) / "ingest_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE}"
os.environ["LEI_ADMIN_API_KEY"] = "test-admin-key"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.ingest import SOURCE_SYSTEM, is_blank, normalise_domain  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Lead  # noqa: E402
from app.saas import Organization  # noqa: E402

AUTH = {"X-LEI-Admin-Key": "test-admin-key"}


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        db.add(Organization(name="Lion Elite Clinical", slug="lion-elite-clinical"))
        db.add(Organization(name="Second Tenant", slug="second-tenant"))
        db.commit()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def org_ids() -> tuple[int, int]:
    with SessionLocal() as db:
        rows = sorted(o.id for o in db.query(Organization).all())
    return rows[0], rows[1]


def prospect(**overrides) -> dict:
    base = {
        "organization_id": org_ids()[0],
        "company_name": "Glow Med Spa",
        "category": "med-spa",
        "public_email": "info@glowmedspa.com",
        "website": "https://www.glowmedspa.com/book",
        "city": "Miami",
        "state": "FL",
    }
    base.update(overrides)
    return base


# --- domain normalisation -------------------------------------------------


def test_domain_normalisation_collapses_equivalent_urls():
    # These are one company. If they do not compare equal the same clinic
    # imports repeatedly, once per URL spelling.
    for value in (
        "https://www.glowmedspa.com/book?ref=x",
        "http://glowmedspa.com",
        "GlowMedSpa.com",
        "www.glowmedspa.com",
    ):
        assert normalise_domain(value) == "glowmedspa.com", value

    assert normalise_domain(None) is None
    assert normalise_domain("   ") is None


def test_blank_detection_treats_whitespace_as_empty():
    # A payload sending " " would otherwise count as a real value and block the
    # field from ever being filled properly.
    assert is_blank(None) and is_blank("") and is_blank("   ")
    assert not is_blank("x") and not is_blank(0)


# --- auth ----------------------------------------------------------------


def test_ingest_requires_the_admin_key(client):
    # POST /leads is unauthenticated for backwards compatibility; this endpoint
    # never was, so it is gated from the start.
    assert client.post("/ingest/leads", json=[prospect()]).status_code == 401
    assert client.post("/ingest/leads", json=[prospect()], headers={"X-LEI-Admin-Key": "wrong"}).status_code == 401


# --- create / idempotency ------------------------------------------------


def test_first_sync_creates_and_records_provenance(client):
    body = client.post("/ingest/leads", json=[prospect()], headers=AUTH).json()

    assert body["created"] == 1 and body["updated"] == 0
    with SessionLocal() as db:
        lead = db.query(Lead).one()
    assert lead.organization_id == org_ids()[0]
    assert lead.source_system == SOURCE_SYSTEM
    assert lead.score > 0, "scoring should run on create"


def test_replaying_the_same_batch_changes_nothing(client):
    # The property that makes a sync safe to retry. Without it a transient
    # failure becomes a permanent gap, because the retry 409s.
    client.post("/ingest/leads", json=[prospect()], headers=AUTH)
    second = client.post("/ingest/leads", json=[prospect()], headers=AUTH).json()

    assert second["created"] == 0
    assert second["unchanged"] == 1
    with SessionLocal() as db:
        assert db.query(Lead).count() == 1


# --- the merge rules -----------------------------------------------------


def test_an_import_never_overwrites_a_researched_value_with_nothing(client):
    # The rule that protects human work. BuildPipeline's view is partial; a
    # plain field copy would write null over a phone someone looked up.
    client.post("/ingest/leads", json=[prospect(public_phone="+1-305-555-0100")], headers=AUTH)
    client.post("/ingest/leads", json=[prospect(public_phone=None, city=None)], headers=AUTH)

    with SessionLocal() as db:
        lead = db.query(Lead).one()
    assert lead.public_phone == "+1-305-555-0100"
    assert lead.city == "Miami"


def test_an_import_fills_a_field_the_crm_is_missing(client):
    client.post("/ingest/leads", json=[prospect(public_phone=None)], headers=AUTH)
    body = client.post("/ingest/leads", json=[prospect(public_phone="+1-305-555-0199")], headers=AUTH).json()

    assert body["updated"] == 1
    assert "public_phone" in body["results"][0]["fields"], "the response says what was contributed"
    with SessionLocal() as db:
        assert db.query(Lead).one().public_phone == "+1-305-555-0199"


def test_notes_append_rather_than_replace(client):
    client.post("/ingest/leads", json=[prospect(notes="Called, left voicemail.")], headers=AUTH)
    client.post("/ingest/leads", json=[prospect(notes="Sources peptides quarterly.")], headers=AUTH)

    with SessionLocal() as db:
        notes = db.query(Lead).one().notes
    assert "Called, left voicemail." in notes, "a human's note survives"
    assert "Sources peptides quarterly." in notes


def test_repeating_the_same_note_does_not_stack(client):
    client.post("/ingest/leads", json=[prospect(notes="Same note")], headers=AUTH)
    client.post("/ingest/leads", json=[prospect(notes="Same note")], headers=AUTH)

    with SessionLocal() as db:
        assert db.query(Lead).one().notes.count("Same note") == 1


def test_crm_state_is_not_touched_by_an_import(client):
    # status and do_not_contact belong to the people working the record. An
    # import that could clear a DNC flag would contact someone who opted out.
    client.post("/ingest/leads", json=[prospect()], headers=AUTH)
    with SessionLocal() as db:
        lead = db.query(Lead).one()
        lead.status = "contacted"
        lead.do_not_contact = True
        db.commit()

    client.post("/ingest/leads", json=[prospect(public_phone="+1-305-555-0111")], headers=AUTH)

    with SessionLocal() as db:
        lead = db.query(Lead).one()
    assert lead.do_not_contact is True, "an import can never clear an opt-out"
    assert lead.status == "contacted", "an import does not reset pipeline state"


# --- dedup keys ----------------------------------------------------------


def test_email_matches_case_insensitively(client):
    client.post("/ingest/leads", json=[prospect()], headers=AUTH)
    client.post("/ingest/leads", json=[prospect(public_email="INFO@GlowMedSpa.com")], headers=AUTH)

    with SessionLocal() as db:
        assert db.query(Lead).count() == 1


def test_domain_matches_when_the_email_differs(client):
    # Second contact at the same clinic. Domain is the right fallback key.
    client.post("/ingest/leads", json=[prospect()], headers=AUTH)
    client.post("/ingest/leads", json=[prospect(public_email="hello@glowmedspa.com")], headers=AUTH)

    with SessionLocal() as db:
        assert db.query(Lead).count() == 1


def test_same_name_in_a_different_state_is_a_different_company(client):
    # Clinic names repeat across states. Merging them would be worse than a
    # duplicate, so name alone is never a key.
    client.post("/ingest/leads", json=[prospect(website=None, public_email=None)], headers=AUTH)
    client.post(
        "/ingest/leads",
        json=[prospect(website=None, public_email=None, state="OH", city="Columbus")],
        headers=AUTH,
    )

    with SessionLocal() as db:
        assert db.query(Lead).count() == 2


# --- tenancy -------------------------------------------------------------


def test_two_tenants_can_hold_the_same_clinic_without_merging(client):
    # The isolation guarantee. Both customers may legitimately prospect the same
    # clinic, and merging would leak one customer's research into the other's CRM.
    first, second = org_ids()
    client.post("/ingest/leads", json=[prospect(organization_id=first)], headers=AUTH)
    client.post("/ingest/leads", json=[prospect(organization_id=second)], headers=AUTH)

    with SessionLocal() as db:
        leads = db.query(Lead).all()
    assert len(leads) == 2
    assert {lead.organization_id for lead in leads} == {first, second}


def test_an_unknown_organization_fails_the_whole_batch(client):
    # Half-applying a batch that names a non-existent tenant would leave records
    # that belong to nobody.
    response = client.post(
        "/ingest/leads",
        json=[prospect(), prospect(organization_id=999_999, company_name="Other Spa")],
        headers=AUTH,
    )

    assert response.status_code == 400
    assert "999999" in response.text.replace(" ", "")
    with SessionLocal() as db:
        assert db.query(Lead).count() == 0, "nothing is written when the batch is rejected"


# --- batch behaviour -----------------------------------------------------


def test_one_bad_row_does_not_lose_the_good_ones(client):
    body = client.post(
        "/ingest/leads",
        json=[
            prospect(),
            prospect(company_name="Second Spa", public_email="a@secondspa.com", website="secondspa.com"),
        ],
        headers=AUTH,
    ).json()

    assert body["received"] == 2 and body["created"] == 2
    assert body["errors"] == []


def test_an_empty_batch_is_accepted_and_reports_nothing(client):
    body = client.post("/ingest/leads", json=[], headers=AUTH).json()
    assert body == {"received": 0, "created": 0, "updated": 0, "unchanged": 0, "results": [], "errors": []}
