# Lion Elite Intelligence

Working MVP for storing, scoring, filtering, and exporting public B2B prospect data.

## Current Features

- Sales dashboard at `/`
- Developer Delivery Control dashboard at `/delivery`
- Peer-governed AI Agent Community dashboard at `/agents`
- Persistent tasks, conversations, commitments, shared memory, peer reviews, approval gates, and audit events
- Celery/Valkey always-on agent routing and one-minute accountability heartbeat
- Track contractors, client contract value, fulfillment costs, forecast profit, and gross margin
- Assign projects and manage milestone acceptance through `/delivery/api/*`
- Health check at `/health`
- Create one lead with `POST /leads`
- Bulk-create leads with `POST /leads/bulk`
- Filter leads with `GET /leads`
- View one lead with `GET /leads/{id}`
- Update status, notes, and do-not-contact with `PATCH /leads/{id}`
- Delete a lead with `DELETE /leads/{id}`
- View CRM stats with `GET /stats`
- Export a rep-ready CSV with `GET /exports/leads.csv`
- Automatic lead scoring
- Duplicate prevention by public email or website

## Run Locally

```bash
cd LION_ELITE_INTELLIGENCE
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:

- Dashboard: `http://127.0.0.1:8000/`
- API docs: `http://127.0.0.1:8000/docs`

## Add One Lead

```bash
curl -X POST http://127.0.0.1:8000/leads \
  -H "Content-Type: application/json" \
  -d @sample_leads.json
```

For a single lead, use one object instead of the full array.

## Bulk Add Leads

```bash
curl -X POST http://127.0.0.1:8000/leads/bulk \
  -H "Content-Type: application/json" \
  -d @sample_leads.json
```

## Filter Leads

```bash
curl "http://127.0.0.1:8000/leads?state=FL&min_score=80&status=new"
```

## Export Leads For A Rep

```bash
curl -o lion_elite_leads.csv \
  "http://127.0.0.1:8000/exports/leads.csv?min_score=60&status=new"
```

## Deploy On Render

Use `render.yaml` in this folder to create:

- the FastAPI web service
- the Postgres database
- the database connection environment variable

The service uses `/health` for Render health checks.

## Data Rules

Only store verified public business information or data from properly licensed sources. Respect opt-outs and set `do_not_contact=true` when requested.


## Developer Delivery Control

Open `/delivery` to add vetted developers, create sold client projects, monitor cash collected, protect fulfillment margins, and identify overdue work. The API also supports milestone acceptance so contractor payouts can be tied to verified deliverables. See `docs/delivery/DEVELOPER_DELIVERY_OS.md` for the operating rules.


## AI Agent Community

Open `/agents` to create and observe work across equal-standing AI agents. Every task receives an owner and a different accountability partner, remains visible in a shared thread, and requires independent peer review. High-risk actions stop for human approval. See `docs/ai-control-plane/PLATFORM_STACK.md` for infrastructure, secrets, governance, and launch instructions.
