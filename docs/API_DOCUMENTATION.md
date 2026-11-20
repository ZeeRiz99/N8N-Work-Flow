# Replyline API (skeleton)

Status: Phase 1 skeleton. FastAPI generates the full OpenAPI at `http://localhost:8000/docs`; this file is the curated guide and grows with each phase. Full endpoint list: `docs/MASTER_PROMPT.md` §7.

## Conventions

- Base path `/api/v1`. JSON. ISO-8601 UTC timestamps.
- Errors: `{"error": {"code", "message", "details", "request_id"}}`.
- Lists: `{items, total, page, page_size}`; filters and sort as query params.
- Status codes: 201 create, 204 no body, 401, 403, 404, 409 (conflict / already handled), 422, 429.
- Every request may carry `X-Request-ID`; the response echoes it. Mutating internal calls require `Idempotency-Key`.

## Endpoint groups

| Group | Auth | Phase | Examples |
|---|---|---|---|
| Health | None | P2 | `GET /health`, `GET /ready` |
| Public capture | Organization public key, honeypot, rate limit | P3 | `POST /public/leads`, `GET /public/forms/{org_slug}` |
| Internal (n8n only) | Service API key; blocked at the proxy | P3+ | `POST /internal/leads/{id}/analyze`, `POST /internal/workflow-runs`, `POST /internal/drafts/{id}/claim-send` |
| Auth and organization | Cookies (access + rotating refresh) | P4 | `POST /auth/login`, `GET /auth/me`, `GET /org/members` |
| Leads | User session, RBAC | P4 | `GET /leads`, `POST /leads/{id}/stage`, `POST /leads/import` |
| AI | User session | P5 | `POST /leads/{id}/analyze`, `POST /ai/analyze-text` |
| Drafts and approvals | User session, approve permission | P6 | `GET /drafts?status=pending_approval`, `POST /drafts/{id}/approve` |
| Automation | Admin | P6 | `GET /automation/executions`, `POST /automation/workflows/{key}/run` |
| Follow-ups, duplicates | User session | P8 | `GET /follow-ups`, `POST /duplicates/{id}/merge` |
| Analytics, settings | User session / admin | P9 | `GET /analytics/overview`, `PUT /settings/scoring` |

## Outbound events (backend → n8n)

| Event | Webhook | Phase |
|---|---|---|
| `lead.created` | `/webhook/rl/lead-created` | P3 |
| `draft.approved` | `/webhook/rl/draft-approved` | P6 |
| `workflow.run-requested` | `/webhook/rl/manual/{key}` | P6 |

Envelope: `{event, event_id, occurred_at, organization_id, request_id, data}`.
