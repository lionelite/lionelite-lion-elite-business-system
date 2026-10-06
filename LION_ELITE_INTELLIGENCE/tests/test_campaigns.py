"""Campaigns and editable ICP scoring.

The point of these is that fit is data, not code. `scoring.calculate_score`
weights personal trainers at 30 and gyms at 25 — the coaching audience — so
under it a TRT clinic lands on the unknown-category default of 10 while a gym
scores 25. For Lion Elite Clinical the weights are not slightly off, they are
inverted, and no edit to a Python dict fixes that for two workspaces at once.

The cases worth pinning are the ones where a plausible implementation is
quietly wrong: a partial ICP edit dropping the exclusion list, "medical spa"
being scored by a looser "spa" entry, and an excluded practice being
indistinguishable from one that merely scored badly.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

_DB_FILE = Path(tempfile.mkdtemp()) / "campaigns_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE}"
os.environ["LEI_ADMIN_API_KEY"] = "test-admin-key"

from fastapi.testclient import TestClient  # noqa: E402

from app.campaigns import (  # noqa: E402
    LION_ELITE_CLINICAL_ICP,
    evaluate_icp,
    merged_icp,
    seed_lion_elite_clinical,
)
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.saas import Organization  # noqa: E402
from app.scoring import calculate_score  # noqa: E402

AUTH = {"X-LEI-Admin-Key": "test-admin-key"}


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        db.add(Organization(name="Lion Elite Clinical", slug="lion-elite-clinical"))
        db.commit()
    yield


@pytest.fixture
def client():
    return TestClient(app)


# --- the problem this module exists to solve ----------------------------


def test_the_legacy_scorer_is_inverted_for_this_campaign():
    # Not a complaint about scoring.py — it is correct for the coaching
    # audience. It is the evidence that one hardcoded scorer cannot serve two
    # workspaces, which is the whole argument for ICP-as-data.
    trt = {"category": "trt clinic", "public_email": "a@b.com"}
    gym = {"category": "gym", "public_email": "a@b.com"}

    assert calculate_score(trt) < calculate_score(gym), "legacy scorer favours the gym"

    icp = LION_ELITE_CLINICAL_ICP
    assert evaluate_icp(trt, icp)["score"] > evaluate_icp(gym, icp)["score"], (
        "the clinical ICP must favour the TRT clinic"
    )


# --- scoring behaviour ---------------------------------------------------


def test_scoring_explains_itself():
    # A bare number tells an operator nothing about whether to trust it. The
    # reasons are also what Phase 6's qualification explanations are built from.
    result = evaluate_icp(
        {"category": "hormone clinic", "state": "FL", "public_email": "info@x.com"},
        LION_ELITE_CLINICAL_ICP,
    )

    joined = " ".join(result["reasons"])
    assert "category 'hormone clinic' +35" in joined
    assert "has public_email +15" in joined
    assert "in target geography (FL) +10" in joined
    assert "no public_phone +0" in joined, "absent signals are reported, not omitted"
    assert result["qualified"] is True


def test_the_longest_category_match_wins():
    # "medical spa" must not be scored by a looser entry that happens to be
    # checked first. Dict order is not a scoring policy.
    icp = {**LION_ELITE_CLINICAL_ICP, "category_weights": {"spa": 5, "medical spa": 25}}
    result = evaluate_icp({"category": "medical spa"}, icp)
    assert "category 'medical spa' +25" in " ".join(result["reasons"])


def test_an_unknown_category_scores_low_rather_than_mid():
    # Treating unknowns as mid-fit is how a list fills with rows nobody
    # converts, which then makes every downstream rate look worse than it is.
    result = evaluate_icp({"category": "llama grooming"}, LION_ELITE_CLINICAL_ICP)
    assert result["score"] <= 10
    assert result["qualified"] is False


def test_exclusion_is_distinct_from_a_low_score():
    # "scored badly" and "must not be contacted" need different handling
    # downstream, and collapsing them loses the distinction where it matters
    # most. A pregnancy clinic is the live example that exposed this.
    excluded = evaluate_icp(
        {"company_name": "Community Pregnancy Clinics", "category": "clinic"},
        LION_ELITE_CLINICAL_ICP,
    )
    assert excluded["excluded"] is True
    assert excluded["qualified"] is False
    assert "pregnancy" in " ".join(excluded["reasons"])

    low = evaluate_icp({"category": "llama grooming"}, LION_ELITE_CLINICAL_ICP)
    assert low["excluded"] is False, "a bad score is not an exclusion"


def test_exclusion_beats_an_otherwise_perfect_score():
    # Every signal present, in a target state, in a weighted category — and
    # still refused, because the exclusion is not a weight.
    result = evaluate_icp(
        {
            "company_name": "Sunrise Pediatric Wellness Clinic",
            "category": "wellness clinic",
            "state": "FL",
            "public_email": "a@b.com",
            "public_phone": "+1",
            "owner_name": "Dr X",
            "website": "x.com",
        },
        LION_ELITE_CLINICAL_ICP,
    )
    assert result["excluded"] is True and result["score"] == 0


def test_geography_absent_is_not_geography_failed():
    # An empty target_states list means geography is not a criterion. Scoring it
    # as a miss would penalise every prospect in a campaign that does not care.
    no_geo = {**LION_ELITE_CLINICAL_ICP, "target_states": []}
    result = evaluate_icp({"category": "med spa", "state": "ZZ"}, no_geo)
    assert not any("geography" in reason for reason in result["reasons"])


# --- partial edits -------------------------------------------------------


def test_a_partial_icp_keeps_the_exclusion_list():
    # The dangerous edit. Sending only a weight must not drop exclude_terms and
    # start admitting paediatric practices.
    merged = merged_icp({"category_weights": {"med spa": 99}})
    assert merged["category_weights"] == {"med spa": 99}
    assert merged["signal_weights"]["public_email"] == 15, "signal weights fall back"
    assert "exclude_terms" in merged


def test_patching_one_weight_preserves_the_rest(client):
    created = client.post(
        "/campaigns",
        json={"name": "Clinical", "slug": "clinical", "icp": LION_ELITE_CLINICAL_ICP},
        headers=AUTH,
    ).json()

    patched = client.patch(
        f"/campaigns/{created['id']}",
        json={"icp": {"qualified_at": 50}},
        headers=AUTH,
    ).json()

    assert patched["icp"]["qualified_at"] == 50
    assert "pregnancy" in patched["icp"]["exclude_terms"], "exclusions survive a partial edit"
    assert patched["icp"]["category_weights"]["trt clinic"] == 35, "weights survive"


# --- API ----------------------------------------------------------------


def test_creating_a_campaign_requires_the_admin_key(client):
    assert client.post("/campaigns", json={"name": "X", "slug": "x"}).status_code == 401


def test_scoring_through_the_api_matches_the_library(client):
    created = client.post(
        "/campaigns",
        json={"name": "Clinical", "slug": "clinical", "icp": LION_ELITE_CLINICAL_ICP},
        headers=AUTH,
    ).json()

    lead = {"category": "trt clinic", "state": "FL", "public_email": "a@b.com"}
    api = client.post(f"/campaigns/{created['id']}/score", json=lead).json()
    assert api["score"] == evaluate_icp(lead, LION_ELITE_CLINICAL_ICP)["score"]


def test_a_duplicate_slug_is_refused(client):
    body = {"name": "Clinical", "slug": "clinical"}
    assert client.post("/campaigns", json=body, headers=AUTH).status_code == 201
    assert client.post("/campaigns", json=body, headers=AUTH).status_code == 409


def test_default_cadence_is_applied_and_editable(client):
    created = client.post(
        "/campaigns", json={"name": "Clinical", "slug": "clinical"}, headers=AUTH
    ).json()
    assert created["sequence_days"] == [0, 2, 5, 10, 21]

    patched = client.patch(
        f"/campaigns/{created['id']}", json={"sequence_days": [0, 3, 7]}, headers=AUTH
    ).json()
    assert patched["sequence_days"] == [0, 3, 7]


# --- seeding ------------------------------------------------------------


def test_seeding_is_idempotent_and_targets_the_right_workspace():
    with SessionLocal() as db:
        first = seed_lion_elite_clinical(db)
        second = seed_lion_elite_clinical(db)

    assert first is not None
    assert first.id == second.id, "re-seeding must not create a duplicate campaign"
    assert first.slug == "clinical-research-supply"
    assert first.icp["category_weights"]["trt clinic"] == 35


def test_seeding_does_nothing_without_the_named_workspace():
    # Scoped by slug, not by "whichever organization is first", so it cannot
    # attach Lion Elite's campaign to someone else's workspace.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        db.add(Organization(name="Someone Else", slug="someone-else"))
        db.commit()
        assert seed_lion_elite_clinical(db) is None


def test_a_reachable_clinic_in_geography_qualifies():
    # Pins the calibration rather than the number. A top-category clinic, in a
    # target state, with one contact point is the realistic shape of a
    # publicly-sourced prospect — if that does not qualify, the qualified list
    # comes back empty and the fault looks like sourcing.
    result = evaluate_icp(
        {"category": "hormone clinic", "state": "FL", "public_email": "info@x.com"},
        LION_ELITE_CLINICAL_ICP,
    )
    assert result["qualified"] is True, f"score {result['score']} should clear the floor"


def test_missing_any_of_the_three_drops_below_the_floor():
    icp = LION_ELITE_CLINICAL_ICP
    # Right category and reachable, wrong geography.
    assert evaluate_icp({"category": "hormone clinic", "state": "ZZ", "public_email": "a@b.com"}, icp)["qualified"] is False
    # Right category and geography, unreachable.
    assert evaluate_icp({"category": "hormone clinic", "state": "FL"}, icp)["qualified"] is False
