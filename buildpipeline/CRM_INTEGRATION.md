# Lion Elite Clinical CRM Integration

BuildPipeline is the top-of-funnel SDR layer. Lion Elite Clinical CRM is the system of record.

## Data flow
BuildPipeline lead sourcing -> qualification -> outreach -> reply -> meeting -> CRM opportunity.

Every BuildPipeline lead should carry:
- external_id
- workspace_id
- source = buildpipeline
- company
- contact
- email
- phone
- website
- location
- services
- ICP score
- pipeline stage
- last touch
- next action
- meeting time
- campaign
- notes

## Sync rules
1. New qualified prospect -> upsert CRM lead.
2. Outbound message -> append CRM activity.
3. Reply -> update lead status and append inbound activity.
4. Meeting booked -> create/update CRM opportunity and meeting.
5. Proposal/won/lost -> CRM remains canonical and BuildPipeline mirrors the status.
6. Email is the preferred dedupe key; website/domain is secondary.
7. Never overwrite CRM notes or manually edited fields with blank BuildPipeline values.

## Environment
CRM_API_BASE=
CRM_API_KEY=

The BuildPipeline endpoint is POST /api/crm. It is intentionally adapter-based so the CRM can be attached without rebuilding the SDR UI once the CRM's live API/database endpoint is identified.
