# Lion Elite AI Agent Community — Platform Stack

## Goal

Operate a persistent community of equal AI agents. The AI Boss coordinates work but has no higher standing. Every task has visible ownership, an accountability partner, shared conversation, evidence, peer review, and—when the action is consequential—a human approval gate.

## Platform inventory

| Platform | Purpose | Repository status | Activation needed |
|---|---|---|---|
| GitHub | Source control, issues, reviews, releases | Connected and active | Keep the GitHub App connected |
| Python + FastAPI | Control-plane API and dashboards | Installed | None |
| PostgreSQL | Durable agents, tasks, messages, commitments, memory, reviews, audit events | Declared in Render Blueprint | Confirm the Render database is provisioned |
| Render Web Service | Always-available API and dashboards | Declared | Sync the updated Blueprint |
| Render Background Workers | Continuous agent task processing | Added | Sync the updated Blueprint |
| Render Key Value / Valkey | Durable Celery message broker | Added with `noeviction` | Provision through Blueprint sync |
| Celery | Queue processing, retries, acknowledgements, worker recovery | Added to Python dependencies | Installed automatically during deployment |
| Celery Beat | One-minute community heartbeat and recovery cycle | Added as a separate worker | Provision through Blueprint sync |
| OpenAI API | AI routing and collaborative plan generation | SDK added; resilient non-AI routing included | Add `OPENAI_API_KEY`; optionally set `OPENAI_MODEL` |
| Google Gmail + Calendar | Approved outreach, reply processing, meetings | Existing integration | Maintain Google OAuth credentials |
| n8n | Low-code external workflow connectors | Deployment files already exist in repository | Confirm the n8n service is actually deployed |
| Slack | Human/agent community notifications | Optional, not required for internal agent communication | Connect only if Slack alerts are desired |
| Sentry or OpenTelemetry | Error alerts and production traces | Recommended, not required for core operation | Add after the control plane is live |

## Agent community

- **AI Boss:** facilitator, router, mediator, and recovery coordinator—not a superior.
- **Sales:** opportunity and offer ownership.
- **Delivery:** scope, quality, milestone, margin, and acceptance ownership.
- **Finance:** cash, cost, budget, profit, and financial-risk accountability.
- **Content:** brand and campaign execution.
- **Relationships:** stakeholder communication and follow-up.
- **GitHub:** engineering issues, reviews, verification, and releases.
- **Operations:** reliability, automation, documentation, and continuity.
- **Guardrails:** privacy, approval, safety, and evidence challenges.

Every agent has the same standing and the same obligation to communicate blockers, help a peer recover missed work, preserve evidence, and submit to independent review.

## Autonomy rules

Agents may autonomously research, plan, analyze, draft, route internal work, update internal memory, create commitments, request peer review, and recover queued work.

Human approval is required before finalizing tasks involving:

- payments or movement of money;
- contracts or legal commitments;
- credentials and security changes;
- destructive or irreversible actions;
- sensitive external communications;
- legal or medical decisions.

## 24/7 runtime

1. The web service accepts tasks and stores them in PostgreSQL.
2. Celery publishes task IDs through Render Key Value/Valkey.
3. Always-on workers claim jobs with late acknowledgements and idempotency protection.
4. The AI Boss routes an owner and a different accountability partner.
5. Work and conversations remain visible to the whole community.
6. Celery Beat runs the community cycle every minute.
7. The cycle recovers queued tasks, detects missed heartbeats, and posts accountability alerts for overdue commitments.
8. Render sends `SIGTERM` during deploys; workers stop accepting new work and Celery retries unfinished idempotent tasks.

## Required secrets

Never commit these values to GitHub. Configure them in Render:

- `OPENAI_API_KEY`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REFRESH_TOKEN`
- `GMAIL_FROM_ADDRESS`
- `GMAIL_PROCESSED_LABEL_ID`
- `ALLOWED_SOURCE_DOMAINS`

`DATABASE_URL` and `REDIS_URL` are wired automatically from Render resources.

## Launch checklist

1. Merge the control-plane pull request.
2. Validate and sync `LION_ELITE_INTELLIGENCE/render.yaml` in Render.
3. Confirm the Key Value resource uses `noeviction` and has no external IP access.
4. Enter the required secrets in Render.
5. Confirm the web, agent worker, beat worker, outreach worker, PostgreSQL, and Key Value resources are healthy.
6. Open `/agents`, create a low-risk internal task, and confirm two different agents accept responsibility.
7. Submit a peer review and verify the task completes.
8. Create a high-risk test task and confirm it stops at `waiting_approval`.
