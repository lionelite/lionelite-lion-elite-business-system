# Lion Elite Intelligence

Working MVP for storing, scoring, filtering, and exporting public B2B prospect data.

## Current Features

- Sales dashboard at `/`
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
