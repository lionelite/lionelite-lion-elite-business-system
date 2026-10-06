"""Reply classification, and the effect it has on the record.

The rule that matters here is one line of the brief: never continue an automated
sequence after an explicit opt-out. Everything below exists because there is a
plausible implementation that breaks it and still looks like it works.

The ordering cases are the ones worth having. A friendly opt-out classified on
sentiment first reads as a buying signal. An unclassifiable reply defaulted to
"neutral" keeps the cadence running — which is precisely what the classifier
this replaces did, and what `worker.process_replies` then acted on by scheduling
a follow-up a day later.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

_DB_FILE = Path(tempfile.mkdtemp()) / "sdr_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE}"
os.environ["LEI_ADMIN_API_KEY"] = "test-admin-key"

from fastapi.testclient import TestClient  # noqa: E402

from app.activities import LeadActivity  # noqa: E402
from app.automation_rules import classify_reply as legacy_classify_reply  # noqa: E402
from app.campaigns import LION_ELITE_CLINICAL_ICP  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Lead  # noqa: E402
from app.replies import apply_reply_to_lead  # noqa: E402
from app.saas import Organization  # noqa: E402
from app.sdr import classify_reply, qualification_summary, recommended_next_action  # noqa: E402

AUTH = {"X-LEI-Admin-Key": "test-admin-key"}


def reset(org_count: int = 1) -> list[int]:
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


def seed_lead(org_id: int, name: str = "Glow Hormone Clinic", **kwargs) -> int:
    with SessionLocal() as db:
        lead = Lead(
            organization_id=org_id,
            company_name=name,
            category=kwargs.pop("category", "hormone clinic"),
            public_email=kwargs.pop("public_email", "info@glow.example"),
            state=kwargs.pop("state", "FL"),
            score=kwargs.pop("score", 60),
            status=kwargs.pop("status", "contacted"),
            **kwargs,
        )
        db.add(lead)
        db.commit()
        return lead.id


@pytest.fixture
def client():
    return TestClient(app)


# --- the ordering rules -------------------------------------------------


def test_a_friendly_opt_out_is_an_opt_out():
    # The case that makes ordering load-bearing. This message is polite, it
    # thanks us, and it contains a buying-adjacent word ("pricing") — and it is
    # a withdrawal of consent. Scored on sentiment first it reads positive.
    result = classify_reply(
        "Thanks so much, the pricing looks great, but please take me off the list."
    )
    assert result["intent"] == "opt_out"
    assert result["stop_sequence"] is True
    assert result["sentiment"] != "positive"


def test_an_unclassifiable_reply_stops_rather_than_continues():
    # The old classifier returned "neutral" here and the worker scheduled
    # another email. Ambiguity costs one prospect; the alternative costs a
    # complaint from someone who was trying to say no.
    result = classify_reply("hm. i'd have to think about whether that's for us")
    assert result["stop_sequence"] is True
    assert result["requires_human"] is True


def test_an_auto_reply_neither_stops_the_sequence_nor_counts_as_engagement():
    # Both wrong readings are damaging in opposite directions: as a positive it
    # halts follow-up on someone who never read the message, as a negative it
    # disqualifies them.
    result = classify_reply("Automatic reply: I am out of the office until Monday.")
    assert result["intent"] == "auto_reply"
    assert result["stop_sequence"] is False
    assert result["sentiment"] == "neutral"
    assert result["requires_human"] is False


def test_an_empty_body_fails_closed():
    # More likely a parsing failure than a genuinely empty reply, and a parsing
    # failure must not read as permission to keep sending.
    for body in (None, "", "   "):
        result = classify_reply(body)
        assert result["stop_sequence"] is True, f"{body!r} must not continue the sequence"
        assert result["requires_human"] is True


def test_a_legal_demand_is_not_filed_as_an_ordinary_opt_out():
    # A suppression entry and a closed ticket is the wrong response to "my
    # attorney will be in touch" — someone has to read it today.
    result = classify_reply("This is unsolicited. My attorney will be in touch regarding CAN-SPAM.")
    assert result["intent"] == "legal_escalation"
    assert result["requires_human"] is True
    assert result["stop_sequence"] is True


def test_an_opt_out_inside_a_rejection_is_still_an_opt_out():
    # Two signals present. The opt-out has to win, because the other reading
    # ("not interested") leaves the address contactable.
    result = classify_reply("Not interested, and please remove me from your list.")
    assert result["intent"] == "opt_out"


# --- short replies -------------------------------------------------------


def test_a_one_word_stop_is_an_opt_out():
    # The legacy classifier matched a bare "stop" anywhere in the text. Dropping
    # that behaviour outright would have stopped honouring the single most
    # common opt-out reply there is.
    for body in ("STOP", "stop.", "Remove", "please remove me", "No thanks - unsubscribe"):
        assert classify_reply(body)["stop_sequence"] is True, body
    assert classify_reply("STOP")["intent"] == "opt_out"


def test_the_same_word_inside_a_sentence_is_not_an_opt_out():
    # "stop by the clinic" and "remove it from the order" are not withdrawals of
    # consent, and the legacy substring match read both as one — quietly
    # suppressing prospects who were engaging.
    result = classify_reply(
        "Happy to chat - stop by the clinic any time next week and remove us from the "
        "cold list, we are already talking"
    )
    assert result["intent"] != "opt_out"


# --- the legacy adapter --------------------------------------------------


def test_the_legacy_three_value_answer_still_works():
    # `worker` and anything else importing automation_rules.classify_reply keeps
    # its contract; there is just no second word list behind it any more.
    assert legacy_classify_reply("unsubscribe") == "opt_out"
    assert legacy_classify_reply("Interested, tell me more") == "interested"
    assert legacy_classify_reply("who is this") in {"neutral", "opt_out", "interested"}


def test_a_legal_demand_maps_to_the_stopping_legacy_value():
    # "neutral" is the only other option and it continues the sequence, so the
    # conservative mapping is the correct one even though it loses the nuance.
    assert legacy_classify_reply("my lawyer will contact you") == "opt_out"


# --- applying the classification to the record --------------------------


def test_an_opt_out_suppresses_the_lead_in_the_database(client):
    # The classification has to be binding, not advisory. Suppression lives on
    # the lead so a sender that has never heard of this module still cannot
    # email them.
    (org,) = reset()
    lead_id = seed_lead(org)

    body = client.post(f"/sdr/leads/{lead_id}/replies", json={"text": "Please unsubscribe me."}).json()

    assert body["suppressed"] is True
    assert body["sequence_stopped"] is True
    assert body["stage"] == "do_not_contact"

    with SessionLocal() as db:
        lead = db.get(Lead, lead_id)
        assert lead.do_not_contact is True
        assert lead.status == "do_not_contact"


def test_suppression_is_one_way(client):
    # A later positive reply from the same address does not reinstate consent.
    # Someone who asked to be left alone and then answered a forwarded thread
    # has not re-subscribed.
    (org,) = reset()
    lead_id = seed_lead(org)

    client.post(f"/sdr/leads/{lead_id}/replies", json={"text": "unsubscribe"})
    second = client.post(
        f"/sdr/leads/{lead_id}/replies", json={"text": "Actually yes, very interested - send pricing"}
    ).json()

    assert second["classification"]["intent"] == "interested", "the reply is still read for what it is"
    assert second["suppressed"] is True, "and the suppression stands"
    assert second["suppressed_by_this_reply"] is False
    assert second["stage"] == "do_not_contact"
    assert second["sequence_stopped"] is True

    with SessionLocal() as db:
        assert db.get(Lead, lead_id).do_not_contact is True


def test_recording_the_same_opt_out_twice_is_harmless(client):
    # Two identical messages are two real events, so both are recorded — but the
    # second finds the lead already suppressed and changes nothing.
    (org,) = reset()
    lead_id = seed_lead(org)

    first = client.post(f"/sdr/leads/{lead_id}/replies", json={"text": "remove me"}).json()
    second = client.post(f"/sdr/leads/{lead_id}/replies", json={"text": "remove me"}).json()

    assert first["suppressed_by_this_reply"] is True
    assert second["suppressed_by_this_reply"] is False
    assert second["suppressed"] is True

    with SessionLocal() as db:
        replies = db.query(LeadActivity).filter(LeadActivity.lead_id == lead_id).all()
        assert len(replies) == 2, "both events are in the timeline"


def test_an_auto_reply_leaves_the_stage_alone_and_schedules_another_touch(client):
    (org,) = reset()
    lead_id = seed_lead(org, status="contacted")

    body = client.post(
        f"/sdr/leads/{lead_id}/replies", json={"text": "I am on annual leave until the 14th."}
    ).json()

    assert body["stage"] == "contacted", "an out-of-office is not progress"
    assert body["stage_changed"] is None
    assert body["suppressed"] is False
    assert body["sequence_stopped"] is False

    with SessionLocal() as db:
        activity = db.query(LeadActivity).filter(LeadActivity.lead_id == lead_id).one()
        assert activity.next_follow_up_at is not None
        assert activity.activity_type == "reply", "recorded as a reply, not as an email we sent"


def test_an_unreadable_reply_is_recorded_without_scheduling_anything(client):
    (org,) = reset()
    lead_id = seed_lead(org, status="contacted")

    body = client.post(f"/sdr/leads/{lead_id}/replies", json={"text": "???"}).json()

    assert body["sequence_stopped"] is True
    assert body["next_action"]["requires_human"] is True
    with SessionLocal() as db:
        assert db.query(LeadActivity).filter(LeadActivity.lead_id == lead_id).one().next_follow_up_at is None


def test_the_follow_up_queue_never_offers_a_suppressed_lead(client):
    # The end-to-end guarantee. The queue is what a rep or a sender works
    # through, so an opted-out contact being absent from it is the thing that
    # actually stops the next message.
    (org,) = reset()
    kept = seed_lead(org, "Still Talking Clinic", public_email="a@b.example")
    dropped = seed_lead(org, "Opted Out Clinic", public_email="c@d.example")

    client.post(f"/sdr/leads/{kept}/replies", json={"text": "out of office until Monday"})
    client.post(f"/sdr/leads/{dropped}/replies", json={"text": "out of office until Monday"})
    client.post(f"/sdr/leads/{dropped}/replies", json={"text": "please stop emailing me"})

    queue = client.get("/activities/follow-ups?due_before=2099-01-01T00:00:00").json()
    companies = {row["company"] for row in queue}
    assert "Still Talking Clinic" in companies
    assert "Opted Out Clinic" not in companies


def test_the_stage_moves_on_a_real_reply(client):
    (org,) = reset()
    lead_id = seed_lead(org, status="contacted")

    body = client.post(
        f"/sdr/leads/{lead_id}/replies", json={"text": "Interested - what times work this week?"}
    ).json()

    assert body["stage"] == "replied"
    assert body["suppressed"] is False
    assert body["next_action"]["requires_human"] is True


def test_apply_is_separable_from_the_http_layer():
    # The decision and its effect are separate functions so the effect can be
    # tested against a bare object, which is how `worker.process_replies` uses
    # it — no request, no session scope.
    lead = Lead(company_name="X", category="clinic", status="contacted", do_not_contact=False)
    changed = apply_reply_to_lead(lead, classify_reply("unsubscribe"))
    assert lead.do_not_contact is True
    assert changed["suppressed"] is True


# --- previewing ----------------------------------------------------------


def test_classify_only_writes_nothing(client):
    # A preview endpoint that suppressed a contact as a side effect would be a
    # trap, so it is a separate route that touches no record.
    (org,) = reset()
    lead_id = seed_lead(org)

    body = client.post("/sdr/classify", json={"text": "take me off the list"}).json()
    assert body["classification"]["intent"] == "opt_out"
    assert body["applied"] is False

    with SessionLocal() as db:
        assert db.get(Lead, lead_id).do_not_contact is False


# --- tenancy -------------------------------------------------------------


def test_a_reply_cannot_be_recorded_against_another_tenants_lead(client):
    first, second = reset(2)
    other = seed_lead(second, "Second Tenant Clinic")

    response = client.post(
        f"/sdr/leads/{other}/replies?organization_id={first}", json={"text": "unsubscribe"}
    )
    assert response.status_code == 404

    with SessionLocal() as db:
        assert db.get(Lead, other).do_not_contact is False, "the record is untouched"


def test_the_brief_is_scoped(client):
    first, second = reset(2)
    other = seed_lead(second, "Second Tenant Clinic")
    assert client.get(f"/sdr/leads/{other}/brief?organization_id={first}").status_code == 404


def test_the_activity_timeline_is_scoped(client):
    # `/activities` read a lead by id with no tenant filter at all, so one
    # customer could read another's call notes.
    first, second = reset(2)
    other = seed_lead(second, "Second Tenant Clinic")
    assert client.get(f"/activities/leads/{other}?organization_id={first}").status_code == 404


def test_the_follow_up_queue_does_not_cross_tenants(client):
    # It returns phone numbers and email addresses, so unscoped it was an export
    # of every tenant's contact list wearing a work-queue label.
    first, second = reset(2)
    mine = seed_lead(first, "My Clinic")
    theirs = seed_lead(second, "Their Clinic")
    for lead_id in (mine, theirs):
        client.post(
            f"/sdr/leads/{lead_id}/replies?organization_id={first if lead_id == mine else second}",
            json={"text": "out of office"},
        )

    queue = client.get(f"/activities/follow-ups?organization_id={first}&due_before=2099-01-01T00:00:00").json()
    assert {row["company"] for row in queue} == {"My Clinic"}


# --- the brief -----------------------------------------------------------


def test_the_brief_explains_the_score_against_a_campaign(client):
    (org,) = reset()
    lead_id = seed_lead(org)
    campaign = client.post(
        "/campaigns",
        json={"name": "Clinical", "slug": "clinical", "icp": LION_ELITE_CLINICAL_ICP},
        headers=AUTH,
    ).json()

    body = client.get(f"/sdr/leads/{lead_id}/brief?campaign_id={campaign['id']}").json()

    assert body["qualification"]["qualified"] is True
    assert "Glow Hormone Clinic" in body["qualification"]["summary"]
    assert body["qualification_unavailable"] is None
    assert body["contactable"] is True


def test_the_brief_says_so_rather_than_inventing_a_score(client):
    # Fit is per campaign. Scoring against a default and presenting the number
    # as this prospect's fit would be a fabricated qualification.
    (org,) = reset()
    lead_id = seed_lead(org)

    body = client.get(f"/sdr/leads/{lead_id}/brief").json()
    assert body["qualification"] is None
    assert "campaign" in body["qualification_unavailable"]


def test_the_brief_carries_the_last_reply_and_the_next_action(client):
    (org,) = reset()
    lead_id = seed_lead(org)
    client.post(f"/sdr/leads/{lead_id}/replies", json={"text": "What does this cost? Too expensive probably."})

    body = client.get(f"/sdr/leads/{lead_id}/brief").json()
    assert body["last_reply"]["classification"]["intent"] in {"interested", "objection"}
    assert "price" in body["last_reply"]["classification"]["objections"]
    assert body["next_action"]["requires_human"] is True


def test_the_brief_of_a_suppressed_lead_says_do_not_contact(client):
    (org,) = reset()
    lead_id = seed_lead(org)
    client.post(f"/sdr/leads/{lead_id}/replies", json={"text": "unsubscribe"})

    body = client.get(f"/sdr/leads/{lead_id}/brief").json()
    assert body["contactable"] is False
    assert body["next_action"]["requires_human"] is False
    # Not "suppress the contact" — that already happened. An action naming work
    # that is already done reads as an outstanding task on a queue.
    assert body["next_action"]["action"] == "No action; contact is suppressed."


def test_a_legal_demand_still_asks_for_a_person_after_suppression(client):
    # The one reply that outranks the suppression short-circuit. Filing it and
    # closing the ticket is not a response to a legal demand.
    (org,) = reset()
    lead_id = seed_lead(org)
    client.post(f"/sdr/leads/{lead_id}/replies", json={"text": "unsubscribe"})
    client.post(
        f"/sdr/leads/{lead_id}/replies",
        json={"text": "I already asked. My attorney will be in touch."},
    )

    body = client.get(f"/sdr/leads/{lead_id}/brief").json()
    assert body["next_action"]["requires_human"] is True
    assert "Escalate" in body["next_action"]["action"]


# --- prose ---------------------------------------------------------------


def test_the_qualification_summary_names_what_is_missing():
    # The actionable half. "Scores 60" is not something a person can act on;
    # "no owner named" is — they can go and find one.
    from app.campaigns import evaluate_icp

    lead = {"company_name": "Glow Hormone Clinic", "category": "hormone clinic", "state": "FL",
            "public_email": "a@b.com"}
    summary = qualification_summary(evaluate_icp(lead, LION_ELITE_CLINICAL_ICP), lead)

    assert "Glow Hormone Clinic" in summary
    assert "qualified" in summary
    assert "Missing" in summary


def test_an_excluded_prospect_reads_as_refused_not_as_a_low_score():
    from app.campaigns import evaluate_icp

    lead = {"company_name": "Community Pregnancy Clinics", "category": "clinic"}
    summary = qualification_summary(evaluate_icp(lead, LION_ELITE_CLINICAL_ICP), lead)
    assert "must not be contacted" in summary


def test_the_next_action_distinguishes_what_needs_a_person():
    # The whole product claim. A system that cannot say which of its next steps
    # need a human will eventually take the wrong one unattended.
    assert recommended_next_action("new")["requires_human"] is False
    assert recommended_next_action("outreach_ready")["requires_human"] is True
    assert recommended_next_action("do_not_contact")["requires_human"] is False
    assert recommended_next_action("something-nobody-defined")["requires_human"] is True
