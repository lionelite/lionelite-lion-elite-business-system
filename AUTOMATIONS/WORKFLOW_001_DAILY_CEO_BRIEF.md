# Workflow 001: Daily CEO Brief

## Purpose
Create the first real AI workforce workflow for Lion Elite.

This workflow turns Render + n8n into a daily operating engine that gathers business information and creates a priority brief automatically.

## Trigger
Every day at 7:00 AM.

## Inputs
- Gmail: GA4 reports, Clarity reports, Stripe reports, Meta reports, client/prospect emails
- Google Calendar: today's schedule
- GitHub: open issues, recent commits, AI agent files, site tasks
- Google Drive: content vault updates

## AI Processing Prompt
You are the Lion Elite CEO Agent. Review the supplied business data and create a daily executive brief.

Return:
1. Yesterday's wins
2. Current risks
3. Website conversion status
4. Highest-value content task
5. Highest-value sales task
6. Highest-value automation task
7. GitHub tasks to create
8. One revenue opportunity for today
9. One system improvement for today

Rules:
- Prioritize actions that increase revenue or reduce Alexander's workload.
- Lion Elite Wellness stays research-education-only.
- Lion Elite Beauty focuses on coaching and aesthetics.
- AlexTheLionLifts focuses on lifestyle, credibility, business, faith, and fitness.
- Output tasks clearly enough that another agent can execute them.

## Outputs
- Email brief to Alexander
- Create GitHub issues for tasks
- Save daily brief to Google Drive
- Log KPI summary to database

## GitHub Issue Template
Title: [Agent] Task Name

Body:
- Department:
- Business goal:
- Problem:
- Recommended action:
- Acceptance criteria:
- Priority:

## Failure Handling
If workflow fails:
1. Email Alexander with the error
2. Create GitHub issue labeled automation-failure
3. Log failed step in n8n execution history

## Success Criteria
The workflow is successful when Alexander receives a daily executive brief automatically and GitHub receives at least one useful task without manual prompting.