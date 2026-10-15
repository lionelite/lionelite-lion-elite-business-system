"""SDR reasoning: reply classification, qualification prose, next action.

Deterministic and offline — no model call, no network, no secrets. That is a
deliberate choice, not a placeholder. The decision this module exists to make is
"does the sequence stop", and that decision must be reproducible, auditable, and
identical on every deploy. A model that is right 97% of the time keeps emailing
3% of the people who asked it to stop, and no amount of prompt work makes that
acceptable when the fix is a word list.

Model generation belongs on top of this, not underneath it: a model can draft
prose, but `stop_sequence` is computed here.

This replaces `automation_rules.classify_reply`, which is now a shim over it
rather than a second implementation. The old one returned a bare string from
three word sets and had two fail-open edges: an unclassified human reply came
back `"neutral"`, and `worker.process_replies` schedules a follow-up a day later
on `"neutral"` — so "I'd rather you didn't" kept the cadence running. And there
was no bucket for a legal demand, so "my attorney will be in touch" was also
`"neutral"`, also followed up. Both are why `stop_sequence` is returned
explicitly instead of being inferred from a sentiment label.

The ordering of checks is the whole design:

1. **Opt-out first and unconditionally.** Checked before sentiment, before
   objections, before anything. A message can be cheerful and still be a
   withdrawal of consent ("thanks, but please take me off the list") — reading
   that as a positive reply is the worst available outcome.
2. **Ambiguity stops the sequence.** Where it is unclear whether someone wants
   out, the sequence stops. The cost of stopping a sequence that could have
   continued is one lost prospect. The cost of continuing one that should have
   stopped is a complaint, a damaged sending domain, and a person contacted
   against their stated wish.
3. **Auto-replies are not opinions.** An out-of-office carries no intent, so it
   must neither stop the sequence nor count as engagement. Treated as a positive
   reply it would stop follow-up on a prospect who never saw the message;
   treated as a negative it would disqualify them.
"""

from __future__ import annotations

import re

# Explicit withdrawals of consent. Matched as whole phrases against normalised
# text, so "unsubscribe" inside a footer URL does not fire on every reply that
# quotes the original message.
OPT_OUT_PHRASES: tuple[str, ...] = (
    "unsubscribe", "opt out", "opt-out", "take me off", "remove me",
    "stop emailing", "stop contacting", "stop sending", "do not contact",
    "don't contact", "dont contact", "do not email", "don't email",
    "no longer wish", "no longer want", "not interested in receiving",
    "leave me alone", "cease all", "delete my", "erase my",
    "no more emails", "no more email", "no further contact", "stop all",
)

# Single words that are an opt-out on their own and nothing in particular inside
# a sentence. "Stop" alone is unambiguous; "stop by the clinic any time" and
# "remove the vial from the fridge" are not, and the legacy classifier matched
# both as bare substrings. So these fire only on a terse reply — see
# `_SHORT_REPLY_WORDS`.
SHORT_OPT_OUT_WORDS: tuple[str, ...] = ("stop", "remove", "unsubscribed", "no")

# A reply this short carrying one of the words above is read as an opt-out. Six
# covers "stop", "please remove me", "stop - not interested" and the like
# without reaching into a real sentence.
_SHORT_REPLY_WORDS = 6

# Legal demands. A separate bucket from opt-out because these need a human
# today, not a suppression entry and a closed ticket.
ESCALATION_PHRASES: tuple[str, ...] = (
    "gdpr", "ccpa", "can-spam", "canspam", "attorney", "lawyer", "legal action",
    "报告", "report you", "reporting you", "spam complaint", "cease and desist",
)

# Out-of-office and other machine replies. No intent either way.
AUTOREPLY_PHRASES: tuple[str, ...] = (
    "out of office", "out of the office", "automatic reply", "auto-reply",
    "autoreply", "on annual leave", "on vacation", "maternity leave",
    "paternity leave", "i am away", "i'm away", "currently away",
    "no longer with", "has left the company", "undeliverable",
    "delivery status notification", "mail delivery failed",
)

POSITIVE_PHRASES: tuple[str, ...] = (
    "interested", "sounds good", "happy to", "let's talk", "lets talk",
    "send me", "send over", "tell me more", "more information", "more info",
    "book a", "schedule a", "set up a call", "set up a time", "what times",
    "available", "worth a conversation", "forward this to", "who handles",
    "pricing", "quote", "coa", "certificate of analysis", "catalogue", "catalog",
)

NEGATIVE_PHRASES: tuple[str, ...] = (
    "not interested", "no thanks", "no thank you", "we're all set", "were all set",
    "already have", "we have a supplier", "happy with our current",
    "not a fit", "not the right", "pass on this", "no need",
)

# Objections worth answering, with the shape of the answer. Identified rather
# than answered here: the reply is a human's or a model's to write, and this
# names which objection it is so the right material is reached for.
OBJECTIONS: dict[str, tuple[str, ...]] = {
    "price": ("too expensive", "too much", "cost", "price is", "budget", "cheaper"),
    "existing_supplier": ("we have a supplier", "already have a supplier", "current supplier", "already work with"),
    "timing": ("not right now", "next quarter", "next year", "circle back", "too busy", "revisit"),
    "authority": ("not my decision", "not the decision", "speak to", "forward you to", "my colleague", "our director"),
    "trust": ("who are you", "never heard of", "how did you get", "where did you get", "is this legitimate", "verify"),
    "compliance": ("research use", "ruo", "fda", "regulated", "licence", "license", "certification", "coa"),
}


def _normalise(text: str | None) -> str:
    """Lowercase and collapse whitespace and punctuation runs.

    Quoted history is kept rather than stripped: a reply that says only
    "unsubscribe" above the quoted thread must still match, and guessing where
    the quote starts across mail clients drops real replies.
    """
    lowered = (text or "").lower()
    lowered = re.sub(r"[‘’]", "'", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _matches(haystack: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase in haystack]


def _short_reply_opt_out(body: str) -> str | None:
    """Match a one-word opt-out that only reads as one in a terse reply.

    Checked as whole words, so "stopped by yesterday" does not fire, and only on
    a short body, so "we'll remove that from the order" does not either.
    """
    words = re.findall(r"[a-z']+", body)
    if len(words) > _SHORT_REPLY_WORDS:
        return None
    for word in SHORT_OPT_OUT_WORDS:
        if word in words:
            return word
    return None


def classify_reply(text: str | None) -> dict:
    """Classify an inbound reply.

    Returns `intent`, `sentiment`, `stop_sequence`, `requires_human`,
    `objections` and `reasons`. `stop_sequence` is the operative field and is
    never inferred downstream from the other values — a caller reading
    `sentiment` to decide whether to keep sending would eventually get it wrong.
    """
    body = _normalise(text)

    if not body:
        # An empty body is not consent to continue. It is more likely a parsing
        # failure than a genuinely empty reply, so it asks for a human.
        return {
            "intent": "unknown",
            "sentiment": "neutral",
            "stop_sequence": True,
            "requires_human": True,
            "objections": [],
            "reasons": ["empty reply body; cannot classify, so holding the sequence"],
        }

    escalations = _matches(body, ESCALATION_PHRASES)
    if escalations:
        return {
            "intent": "legal_escalation",
            "sentiment": "negative",
            "stop_sequence": True,
            "requires_human": True,
            "objections": [],
            "reasons": [f"legal or regulatory language: {escalations[0]!r}"],
        }

    opt_outs = _matches(body, OPT_OUT_PHRASES)
    short_word = None if opt_outs else _short_reply_opt_out(body)
    if short_word:
        opt_outs = [short_word]
    if opt_outs:
        # Checked before sentiment on purpose. "Thanks, this looks great, but
        # please take me off the list" is friendly and is still a withdrawal of
        # consent; scoring it as positive is the worst available error.
        return {
            "intent": "opt_out",
            "sentiment": "negative",
            "stop_sequence": True,
            "requires_human": False,
            "objections": [],
            "reasons": [f"explicit opt-out: {opt_outs[0]!r}"],
        }

    autoreplies = _matches(body, AUTOREPLY_PHRASES)
    if autoreplies:
        # Carries no intent, so it must not stop the sequence and must not count
        # as engagement. Either reading corrupts the funnel.
        return {
            "intent": "auto_reply",
            "sentiment": "neutral",
            "stop_sequence": False,
            "requires_human": False,
            "objections": [],
            "reasons": [f"automated reply: {autoreplies[0]!r}; no intent expressed"],
        }

    objections = [name for name, phrases in OBJECTIONS.items() if _matches(body, phrases)]
    positives = _matches(body, POSITIVE_PHRASES)
    negatives = _matches(body, NEGATIVE_PHRASES)

    reasons: list[str] = []
    if positives:
        reasons.append(f"buying signal: {positives[0]!r}")
    if negatives:
        reasons.append(f"rejection signal: {negatives[0]!r}")
    if objections:
        reasons.append(f"objections: {', '.join(objections)}")

    if negatives and not positives:
        return {
            "intent": "not_interested",
            "sentiment": "negative",
            # A clear no stops the sequence. Continuing to follow up on someone
            # who said no is how a cold campaign earns complaints, and the
            # objection is recorded so a human can judge whether to re-approach
            # later by hand.
            "stop_sequence": True,
            "requires_human": False,
            "objections": objections,
            "reasons": reasons,
        }

    if positives:
        return {
            "intent": "interested",
            "sentiment": "positive",
            # Stops the automated cadence: once someone engages, further
            # scheduled touches talk over a live conversation.
            "stop_sequence": True,
            "requires_human": True,
            "objections": objections,
            "reasons": reasons,
        }

    if objections:
        return {
            "intent": "objection",
            "sentiment": "neutral",
            "stop_sequence": True,
            "requires_human": True,
            "objections": objections,
            "reasons": reasons,
        }

    # A human replied and nothing matched. Unclassified, so it stops and asks
    # for a person — the fail-closed direction.
    return {
        "intent": "unclear",
        "sentiment": "neutral",
        "stop_sequence": True,
        "requires_human": True,
        "objections": [],
        "reasons": ["a human replied but no signal matched; holding for review"],
    }


def qualification_summary(evaluation: dict, lead: dict | None = None) -> str:
    """Turn ICP scoring reasons into one line a person can act on.

    Built from the reasons `evaluate_icp` already produces rather than
    re-deriving them, so the prose and the number cannot disagree.
    """
    lead = lead or {}
    name = lead.get("company_name") or "This prospect"

    # Permission is reported before fit. "Scores 75 and is qualified" read
    # alongside a do-not-contact badge is an invitation to act on the fit and
    # ignore the permission, and the fit is the part that does not matter here.
    if lead.get("do_not_contact"):
        score = evaluation.get("score", 0)
        return (
            f"{name} opted out and must not be contacted. "
            f"(Fit against the current ICP would be {score}; it is not actionable.)"
        )

    if evaluation.get("excluded"):
        why = (evaluation.get("reasons") or ["excluded"])[0]
        return f"{name} must not be contacted for this campaign — {why}."

    score = evaluation.get("score", 0)
    earned = [r for r in evaluation.get("reasons") or [] if not r.endswith("+0")]
    missing = [r for r in evaluation.get("reasons") or [] if r.endswith("+0")]

    verdict = "qualified" if evaluation.get("qualified") else "below the qualification floor"
    line = f"{name} scores {score} and is {verdict}."
    if earned:
        line += " Strengths: " + ", ".join(r.rsplit(" +", 1)[0] for r in earned[:3]) + "."
    if missing:
        # Naming what is absent is the actionable half: a missing phone is
        # something a person can go and find.
        line += " Missing: " + ", ".join(r[3:].rsplit(" +", 1)[0] for r in missing[:3]) + "."
    return line


def recommended_next_action(stage: str | None, reply: dict | None = None) -> dict:
    """What to do next, and whether a human has to do it.

    `requires_human` is returned separately from the action text because the
    distinction is the product: an automated system that cannot say which of its
    next steps need a person is one that will take the wrong one unattended.
    """
    current = (stage or "new").strip().lower().replace(" ", "_")

    if reply:
        intent = reply.get("intent")
        # Ahead of the suppression short-circuit below: a legal demand needs a
        # person to read it today whether or not the address is already
        # suppressed. Suppressing and closing the ticket is not a response to
        # "my attorney will be in touch".
        if intent == "legal_escalation":
            return {"action": "Escalate to a human today; do not reply automatically.", "requires_human": True}
        # The lead is already suppressed, so the reply-driven actions below
        # would name work that has already happened. "Suppress the contact" on
        # an already-suppressed lead reads as an outstanding task, and an
        # operator working a list of those will eventually act on one.
        if current == "do_not_contact":
            return {"action": "No action; contact is suppressed.", "requires_human": False}
        if intent == "opt_out":
            return {"action": "Suppress the contact and stop all sequences.", "requires_human": False}
        if intent == "interested":
            objections = reply.get("objections") or []
            if objections:
                return {
                    "action": f"Reply addressing {objections[0]}, then offer two concrete times.",
                    "requires_human": True,
                }
            return {"action": "Reply with two concrete times and book the call.", "requires_human": True}
        if intent == "objection":
            return {
                "action": f"Answer the {(reply.get('objections') or ['stated'])[0]} objection with documentation.",
                "requires_human": True,
            }
        if intent == "not_interested":
            return {"action": "Mark closed-lost and stop the sequence.", "requires_human": False}
        if intent == "auto_reply":
            return {"action": "No action; the cadence continues on schedule.", "requires_human": False}
        return {"action": "Read the reply and classify it by hand.", "requires_human": True}

    by_stage = {
        "new": ("Score against the campaign ICP.", False),
        "qualified": ("Draft the first-touch message for review.", True),
        "outreach_ready": ("Approve and send the first touch.", True),
        "contacted": ("Wait for the next cadence step.", False),
        "replied": ("Classify the reply and respond.", True),
        "follow_up": ("Send the next cadence step.", False),
        "call_booked": ("Prepare the pre-call brief.", True),
        "proposal": ("Follow up on the proposal.", True),
        "won": ("Hand over to fulfilment.", True),
        "lost": ("No action.", False),
        "do_not_contact": ("No action; contact is suppressed.", False),
    }
    action, requires_human = by_stage.get(current, ("Review by hand; stage is unrecognised.", True))
    return {"action": action, "requires_human": requires_human}


# --- legacy adapter ------------------------------------------------------

# `automation_rules.classify_reply` returned one of these three strings and
# `worker.process_replies` branches on them. The mapping is deliberately
# conservative: a legal demand reports as `opt_out` because the one thing it
# must certainly do is stop the sending, and `opt_out` is the only legacy value
# that does. Callers that need the distinction read `classify_reply` directly —
# which `worker.process_replies` now does, so it can honour `stop_sequence`
# instead of scheduling a follow-up on anything it failed to classify.
_LEGACY_INTENTS = {
    "opt_out": "opt_out",
    "legal_escalation": "opt_out",
    "interested": "interested",
}


def legacy_classification(text: str | None) -> str:
    """The old three-value answer, derived from the real classification."""
    return _LEGACY_INTENTS.get(classify_reply(text)["intent"], "neutral")
