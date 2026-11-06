# BuildPipeline CRM connection

BuildPipeline uses Lion Elite Intelligence as its system of record.

## Required server-side configuration

- `CRM_API_BASE`: CRM service base URL, without credentials, query or fragment.
- `CRM_ADMIN_KEY`: existing CRM admin credential, sent as `X-LEI-Admin-Key`. Keep it in Render secret configuration, never source control or client code.
- `CRM_ORGANIZATION_ID`: positive integer identifying the intended existing CRM organization.

The old `CRM_API_KEY` setting is not read by the current adapter. Do not replace or rotate credentials just to diagnose a connection.

## Safe configuration check

`GET /api/crm` returns only `configured`, `missing`, `invalid`, and an explicit `connectionVerified: false`. It reads local configuration only: no CRM request, prospect data, credential values or configured URLs are returned. The response is not cached.

Configured does not mean connected. Authentication, organization existence, CRM availability and persistence still need separate verification. After configuration is corrected, verify a clearly labelled user-authorized test lead and its notes survive a reload. A CRM stage alone does not create or verify a calendar booking.

## Data flow

Prospects are upserted through `POST /ingest/leads`, read using organization-scoped `GET /leads`, and updated using organization-scoped `PATCH /leads/{id}`. BuildPipeline maps its contact fields to the CRM vocabulary in `lib/crm.js`.

## Optional outward event mirror

`POST /api/crm` is a separate event mirror configured with `CRM_SYNC_URL` and optional `CRM_SYNC_KEY` and `CRM_WORKSPACE`. It does not configure the system-of-record connection or prove a record was saved there.
