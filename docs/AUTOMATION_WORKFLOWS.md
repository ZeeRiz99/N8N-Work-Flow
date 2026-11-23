# Automation workflows (n8n)

n8n sequences and delivers; the Replyline backend decides (D10). Workflow files live in
`n8n/workflows/` and hold no secrets. `n8n/build_p6_workflows.py` and `build_p8_workflows.py` build the wiring as code;
`scripts/import-workflows.ps1 -Activate` fills the placeholders from `.env`, imports and
activates them.

## Live workflows

| ID | Name | Trigger | Steps | Safety |
|---|---|---|---|---|
| W1 | Lead Intake & Orchestration | webhook `rl/lead-created` (header `X-Webhook-Secret`) | analyze → if High and first delivery: alert summary → email the team → log alert → write reply draft → log run | Idempotency keys `{event_id}:analyze` and `{event_id}:draft`; a redelivered event is logged `skipped` and creates nothing |
| W4b | Send Approved Draft | webhook `rl/draft-approved` | claim send → if 200: SMTP send → mark sent (message id) or mark failed (error output) → log run | Only an `approved` draft can be claimed, atomically (`approved → sending`); a second claim gets 409 and the run is `skipped` |
| W9 | Error Monitor | n8n Error Trigger (error workflow of W1 and W4b) | log error → if `should_alert`: email the admin | The backend throttles to one alert per workflow per 10 minutes; n8n keeps no state |
| W5 | Follow-Up Scheduler | every hour | due follow-ups (only organizations inside their own business hours, Mon–Fri 09:00–17:00 local) → for each: prepare (backend checks the contact rules, skips with a reason or writes a follow-up draft) → email the team if drafts wait → log run | Never sends; drafts go to Approvals |
| W6 | Lost-Lead Recovery | weekly (Monday 10:00) + manual webhook `rl/manual/W6` | recovery candidates (open, quiet 14+ days, contactable, not recovered in 30 days) → check-in draft each (reason from stored records only) → email the team → log run | Never sends |
| W7 | Duplicate Scan | daily 08:00 | scan → email the team only when new pairs are found → log run | Never merges; a person reviews every pair (with a merge preview) |
| W9b | Retry Sweeper | every 10 minutes | redispatch the outbox (requeue failed events, deliver stalled ones) → retry AI (re-send leads stuck by a crash, retry failed analyses) → log run | Capped and idempotent |

Not yet split out: W2 (analysis), W3 (alert) and W4 (draft) run inline inside W1 (backlog #36).
Telegram: `python n8n/build_p6_workflows.py --telegram` adds a Telegram branch to W1 (error
output → failure log + email fallback) once the bot credential `RL Telegram Bot` exists
(backlog #17). Until then alerts go by email.

## Events (backend → n8n)

Envelope: `{event, event_id, occurred_at, organization_id, request_id, data}`, delivered from the
transactional outbox with retries and backoff. Fixtures: `contracts/internal-api/`.

| Event | Webhook | `data` |
|---|---|---|
| `lead.created` | `/webhook/rl/lead-created` | `lead_id`, `inquiry_id`, `new_lead` |
| `draft.approved` | `/webhook/rl/draft-approved` | `draft_id`, `lead_id` |

## Internal API used by the workflows (service key)

| Call | Used by | Returns |
|---|---|---|
| `POST /internal/leads/{id}/analyze` | W1 | `{ai_status, score, band, summary, first_delivery}` |
| `GET /internal/leads/{id}/alert-summary` | W1 | facts-only `{title, text, link}` (link in the text) |
| `POST /internal/notifications/log` | W1 | `{should_alert}` (true only for a failed alert) |
| `POST /internal/leads/{id}/drafts/generate` | W1 | `{first_delivery, draft_id}` or `{skipped}` (spam, job seeker, no email) |
| `POST /internal/drafts/{id}/claim-send` | W4b | `{to, subject, body}` or 409 |
| `POST /internal/drafts/{id}/mark-sent` / `mark-failed` | W4b | `{status}`; sent schedules a follow-up in 3 days |
| `POST /internal/workflow-runs` | W1, W4b | upsert by `(workflow_key, n8n_execution_id)` |
| `POST /internal/workflow-errors` | W9 | `{should_alert, subject, text}` |
| `GET /internal/follow-ups/due` · `POST /internal/follow-ups/{id}/prepare` | W5 | due items · `{status, draft_id}` or `{status: skipped, reason}` |
| `GET /internal/leads/recovery-candidates` · `POST /internal/leads/{id}/recovery-suggestion` | W6 | candidates with reasons · `{draft_id, reason}` |
| `POST /internal/duplicates/scan` | W7 | `{added, notify, subject, text}` |
| `POST /internal/outbox/redispatch` · `POST /internal/leads/retry-ai` | W9b | `{requeued, dispatched}` · `{requeued_stuck, recovered}` |

## Testing

- `scripts/smoke.ps1`: 17 checks, from form submission to the email in Mailpit, including
  redelivery of both events (no duplicate lead, draft, alert or send).
- `scripts/failure-injection.ps1`: n8n stopped (outbox keeps and recovers the lead) and SMTP
  refusing (draft `failed`, no second attempt).
- `pytest`: the atomic send claim, "no send unless approved" (behavioural and static), alert
  throttling, Telegram failure leaves the lead untouched, Gemini faults.
