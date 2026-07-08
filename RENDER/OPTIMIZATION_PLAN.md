# Render Optimization Plan

Purpose: make Render the execution layer for Lion Elite OS.

## Render Role
Render is the always-on infrastructure layer. It should run the automation engine, scheduled jobs, webhooks, and any internal dashboards needed for Lion Elite.

## Highest Priority Services

### 1. n8n Automation Server
Use n8n as the orchestration engine for the AI workforce.

Responsibilities:
- Run scheduled workflows
- Receive webhooks
- Connect Gmail, Calendar, Drive, GitHub, analytics reports, and business tools
- Trigger AI agent prompts
- Create GitHub tasks
- Draft emails and documents

### 2. Postgres Database
Use Postgres as the persistent database for n8n and future Lion Elite OS memory.

Responsibilities:
- Store workflow data
- Store execution logs
- Store agent memory records
- Store daily KPI snapshots

### 3. Daily Worker / Cron Jobs
Use Render cron jobs or n8n schedules for recurring business operations.

Core schedules:
- 7:00 AM Daily CEO Brief
- 12:00 PM Content Production Check
- 4:00 PM Sales and Follow-Up Check
- Friday Weekly Analytics Review

## Optimization Rules

1. Avoid free-tier sleeping for production automations.
2. Use persistent storage or database-backed state.
3. Keep secrets in Render environment variables, never in GitHub.
4. Separate public website services from internal automation services.
5. Add health checks for all important services.
6. Log failures and send alert emails when workflows fail.
7. Keep all workflow documentation in GitHub.

## Environment Variables To Prepare

OPENAI_API_KEY=
GITHUB_TOKEN=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
N8N_ENCRYPTION_KEY=
N8N_BASIC_AUTH_USER=
N8N_BASIC_AUTH_PASSWORD=
N8N_HOST=
N8N_PROTOCOL=https
WEBHOOK_URL=
DATABASE_URL=

## First Deployment Goal

Deploy n8n on Render with Postgres and secure login. Then build the first workflow:

Daily CEO Brief:
1. Trigger at 7 AM
2. Pull Gmail reports
3. Pull Google Calendar agenda
4. Pull GitHub open tasks
5. Generate daily priority brief
6. Create GitHub issues for needed tasks
7. Email the brief to Alexander

## Success Criteria

- n8n is live on Render
- Login is secured
- Postgres is connected
- Daily workflow runs on schedule
- Failed executions create alerts
- GitHub receives new tasks automatically