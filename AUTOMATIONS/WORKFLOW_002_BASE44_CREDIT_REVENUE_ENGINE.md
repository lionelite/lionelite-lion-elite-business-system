# Workflow 002 — Base44 Credit Revenue Engine

## Objective

Use the monthly Base44 message and integration credits on revenue-producing Lion Elite workflows instead of consuming them on disconnected app experiments.

This workflow supports the existing Lion Elite business system and the personal-trainer growth offer already defined in `sales/personal-trainer-client-growth-outreach.md`.

## Primary Revenue Loop

Lead enters pipeline → AI qualifies lead → personalized outreach is generated → approved outreach is sent → reply is captured → follow-up is scheduled → call is booked → opportunity advances → result is logged.

## What Message Credits Should Be Used For

Use message credits for tasks that require AI reasoning or generation:

1. Lead qualification and fit scoring.
2. Short prospect research summaries.
3. Personalized outreach drafts.
4. Follow-up message generation.
5. Reply classification: interested, objection, not now, not interested.
6. Suggested next action.
7. Call preparation briefs.
8. Post-call summaries and next-step drafts.
9. Weekly pipeline analysis.
10. Content repurposing from successful sales conversations.

Do not use message credits for static UI changes, duplicate summaries, or low-value internal chatter.

## What Integration Credits Should Be Used For

Use integration credits for actions that move data or communicate across systems:

1. Gmail — send approved outreach and read replies.
2. Google Calendar — create booked discovery calls and reminders.
3. Google Sheets — optional export/backup of active pipeline.
4. Google Drive — attach proposals, agreements, or supporting documents.
5. GitHub — keep operating logic, prompts, and playbooks versioned.
6. Slack or other internal notifications only when there is a real sales event worth surfacing.

## Core Pipeline

- New Lead
- Qualified
- Outreach Ready
- Contacted
- Replied
- Follow-Up
- Call Booked
- Proposal
- Won
- Lost
- Do Not Contact

## Lead Record

Each lead should contain:

- Business or prospect name
- Contact name
- Email
- Phone when legitimately provided
- Website or public profile
- Source
- Offer fit
- Lead score
- Pain point
- Outreach angle
- Last contact date
- Next follow-up date
- Pipeline stage
- Notes
- Do-not-contact flag

## Daily Automation

### Morning
- Pull new leads into the pipeline.
- Score and rank them.
- Generate outreach only for leads above the qualification threshold.

### During the day
- Send only approved messages.
- Log every outbound message.
- Detect replies and classify them.
- Create the next recommended action.

### End of day
- Surface:
  - new qualified leads
  - messages sent
  - replies
  - positive replies
  - calls booked
  - proposals outstanding
  - leads requiring follow-up tomorrow

## Follow-Up Logic

Suggested cadence:

- Day 0 — initial outreach
- Day 2 — follow-up 1
- Day 5 — follow-up 2
- Day 10 — follow-up 3
- Day 21 — final light-touch follow-up

Stop follow-up immediately on:
- explicit opt-out
- do-not-contact request
- hard no
- invalid contact information

## Personalization Rules

Every first-touch message should reference at least one real, public, prospect-specific signal such as:

- service offered
- location
- recent post
- stated growth goal
- public client transformation
- business positioning

Never fabricate a personal detail.

## Performance Dashboard

Track:

- leads added
- qualified leads
- outreach sent
- reply rate
- positive reply rate
- calls booked
- proposals sent
- closes
- revenue won
- average touches before reply
- credits used per booked call
- credits used per closed client

## Credit Efficiency Rule

The system should optimize for:

**Booked Calls / Credits Used**

and then:

**Revenue Won / Credits Used**

If a workflow consumes credits but does not improve one of those outcomes, reduce or remove it.

## First Deployment Target

Start with the existing Lion Elite Beauty personal-trainer client-growth offer.

Use the current playbook in:

`sales/personal-trainer-client-growth-outreach.md`

The first deployment should connect prospecting, outreach, follow-up, and call booking into one measurable pipeline.

## Phase Two

After the first loop is working, reuse the same engine for additional Lion Elite offers without rebuilding the infrastructure.

The operating principle is:

**One acquisition engine, multiple offers.**
