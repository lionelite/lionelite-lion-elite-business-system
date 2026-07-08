# n8n Render Deployment Checklist

## Objective
Deploy n8n on Render so Lion Elite has a real automation engine running outside ChatGPT.

## Step 1: Create Render Services

Create:
- Web Service: n8n
- Database: Postgres
- Optional Cron Job: health check / fallback brief trigger

## Step 2: Configure n8n Web Service

Recommended settings:
- Service type: Web Service
- Runtime: Docker
- Image: official n8n image
- Instance: paid always-on instance for production
- Health check path: /
- Auto deploy: enabled from GitHub once config is confirmed

## Step 3: Add Environment Variables

Required:
- N8N_ENCRYPTION_KEY
- N8N_BASIC_AUTH_ACTIVE=true
- N8N_BASIC_AUTH_USER
- N8N_BASIC_AUTH_PASSWORD
- N8N_HOST
- N8N_PROTOCOL=https
- WEBHOOK_URL
- DB_TYPE=postgresdb
- DB_POSTGRESDB_DATABASE
- DB_POSTGRESDB_HOST
- DB_POSTGRESDB_PORT
- DB_POSTGRESDB_USER
- DB_POSTGRESDB_PASSWORD

Business integrations:
- OPENAI_API_KEY
- GITHUB_TOKEN
- GOOGLE_CLIENT_ID
- GOOGLE_CLIENT_SECRET

## Step 4: Secure The Service

- Turn on basic auth
- Use a strong password
- Keep credentials out of GitHub
- Restrict access when possible
- Rotate API keys if exposed

## Step 5: Create First Workflow

Workflow name: Daily CEO Brief

Trigger:
- Every day at 7 AM

Actions:
1. Read relevant Gmail reports
2. Read Calendar events
3. Read GitHub tasks
4. Send data to OpenAI prompt
5. Generate CEO brief
6. Email the brief to Alexander
7. Create GitHub issues for high-priority tasks

## Step 6: Create Failure Alerts

If workflow fails:
- Send Gmail alert
- Create GitHub issue labeled automation-failure

## Step 7: Daily Optimization Loop

Every workflow should end with:
- What was completed?
- What got blocked?
- What should be automated next?
- What task should be created in GitHub?

## First Success Milestone

The first real AI workforce milestone is complete when Alexander receives one automated CEO Brief without manually opening ChatGPT.