# Portfolio claims and their evidence

Every statement used in the README, case study, video, LinkedIn posts or freelance listings must
appear here with the evidence behind it. If a claim is not in this table, do not make it.

**Ground truth:** Replyline is a self-developed portfolio project. It has no customers, no revenue
and no production track record. All data is fictional. It has not been deployed to a public
server yet (the deployment is prepared and rehearsed locally).

## Product claims

| Claim | Evidence |
|---|---|
| Leads arrive from a public web form, manual entry and CSV import | `backend/app/api/v1/public.py`, `leads.py`, `data.py` (CSV); `frontend/e2e/crm-journey.spec.ts`; screenshot `portfolio/final/10-public-form.png` |
| The form has consent, a honeypot and a rate limit | `frontend/src/app/f/[slug]/public-form.tsx`; `backend/tests/test_walking_skeleton.py`; `test_security_matrix.py` |
| Exact and fuzzy duplicates are detected; merging is human-only | `backend/app/services/duplicates.py`; W7 `n8n/workflows/rl-w7-duplicate-scan.json`; screenshot `p8-03-merge-preview.png` |
| Every AI-extracted fact must quote the customer's words, otherwise it is dropped | `backend/app/ai/grounding.py`; `backend/tests/test_ai_core.py`, `test_analysis_pipeline.py`; eval report "grounding rejection rate" |
| Prompt-injection text is flagged for review and never raises a score | `backend/app/ai/guard.py`; red-team corpus `evals/datasets/redteam.jsonl` (16 techniques) run by `backend/tests/test_redteam.py`; screenshot `p5-04-prompt-injection-flagged-for-review.png` |
| The score is computed by deterministic, configurable rules (7 factors); the AI never sets a number | `backend/app/scoring/engine.py`; `backend/tests/test_ai_core.py`, `test_analysis_pipeline.py`; screenshots `final/04-score-breakdown.png`, `p5-06-scoring-settings.png` |
| Each score has a plain-language explanation per factor | `frontend/src/app/(app)/leads/[id]/ai-panels.tsx`; screenshot `final/04-score-breakdown.png` |
| When the AI is unavailable the lead still gets a provisional score and is retried | `backend/app/services/analysis.py`; `requeue`/retry sweeper W9b; screenshot `p5-07-ai-unavailable-provisional-fallback.png` |
| Reply drafts are checked automatically (prices from the service list, no promised dates or discounts, link allow-list, opt-out line added by code) | `backend/app/ai/draft_checks.py`; `backend/tests/test_drafting.py`; screenshot `final/05-approvals-draft.png` |
| Nothing is sent until a person approves it, and an approved draft is sent exactly once | Atomic claim-send in `backend/app/services/approvals.py`; `backend/tests/test_approvals.py`; `scripts/failure-injection.ps1` (13/13 at P6) |
| Contact rules and a suppression list guard every send path | `backend/app/services/followups.py` (`contact_check`); `backend/tests/test_followups.py` |
| Follow-ups, lost-lead check-ins, a daily summary and source-performance reports run on schedules in n8n | W5, W6, W8, W10 in `n8n/workflows/`; `docs/AUTOMATION_WORKFLOWS.md` |
| Report text written by the AI is checked number by number against SQL, otherwise a template is used | `backend/app/services/reports.py`; `backend/tests/test_reports.py` |
| Failed workflows email an alert (throttled); stalled deliveries are retried every 10 minutes | W9, W9b; `scripts/failure-injection.ps1` |
| Leads are not lost or duplicated when n8n or the backend stops mid-flow | Transactional outbox + idempotency keys (`backend/app/services/outbox.py`); `scripts/journey.ps1` (kills the backend mid-flow, 3/3 runs); `scripts/failure-injection.ps1` |
| 130 concurrent submissions (100 unique + 30 repeats) produced exactly 100 leads, all processed within 30 s | `scripts/load-smoke.ps1`; `docs/PERFORMANCE.md`; development log 2026-11-24 (P10). Local machine, one run |
| Multi-tenant: one organization never sees another's data | `backend/tests/test_security_matrix.py` (32 endpoints × 4 roles, 21 isolation checks) |
| One n8n instance serves every organization; normal keys stay scoped to one | `app/api/deps.py` (`internal:any-org`); `backend/tests/test_any_org_service_key.py` |
| Services and price ranges are edited in the app | `frontend/src/app/(app)/settings/services/page.tsx`; covered by `frontend/e2e/ui-audit.spec.ts` and `a11y.spec.ts` |
| Roles: owner, admin, member; invitations | `backend/app/services/invitations.py`; `backend/tests/test_invitations.py`; screenshot `p9-04-team-invite.png` |
| Analytics: funnel, source performance, reply time | `frontend/src/app/(app)/analytics/`; screenshots `final/09-analytics-sources.png`, `p9-02-analytics-funnel.png` |
| Accessible: axe finds no critical issues on 18 pages; keyboard paths tested | `frontend/e2e/a11y.spec.ts`; `docs/audits/`. A screen-reader (NVDA) pass is **not** done yet (backlog #40) |
| Security headers, CSRF protection, rate-limited login, secrets never logged | `docs/SECURITY.md`; `backend/tests/test_security_matrix.py` |
| Backups restore with identical row counts | `scripts/restore-drill.ps1` (27 tables, P10) |
| Production setup: Docker images, HTTPS proxy, deploy script and runbook | `infra/compose.prod.yml`, `scripts/deploy.sh`, `docs/DEPLOYMENT.md`; local rehearsal 2026-11-24 (6/6 checks, journey reached a sent email). **Not deployed publicly** |

## Numbers

| Number | Source | Caveat to state with it |
|---|---|---|
| 361 automated backend tests | `pytest --co` on 2026-11-24 | Count of tests, not a quality measure |
| 4 Playwright suites (CRM journey, MVP journey, UI audit, accessibility) | `frontend/e2e/` | |
| 9 n8n workflows (W1, W4b, W5, W6, W7, W8, W9, W9b, W10) | `n8n/workflows/` | W2/W3/W4 run inline inside W1 (backlog #36) |
| Gemini priority-band agreement 93%, service and budget extraction 100%, 1 of 62 claims rejected by grounding, 0 schema-invalid outputs | `evals/reports/2026-11-23-gemini-sample15.md` | **14 scored cases** from a 15-case stratified sample of 40 fictional inquiries; expected labels are one person's judgment; one case moves a percentage by about 7 points |
| Gemini mean latency 10.2 s, p95 13.7 s | same report | Free tier, one day |
| Offline provider: band agreement 72%, band within one step 100% (40 cases) | `evals/reports/2026-11-23-fake.md` | The offline provider is a rules-based stand-in used for tests and demos |

## Claims we do **not** make

- No customer, revenue, conversion-rate, time-saved or "more sales" claims.
- No testimonials.
- No accuracy claim beyond the evaluation reports above, always with the sample size.
- No "production-proven" or uptime claims: it has not run on a public server.
- Telegram alerts are **optional and only partly demonstrated**: W1 has a Telegram variant
  (`n8n/workflows/variants/`), used when a bot token and chat id are configured, and the bot is
  connected (screenshot 08 shows its connection test message). A real High-lead alert through W1
  has not been captured yet, because Telegram is blocked on the dev network without a system-wide
  VPN; the email fallback for that case is verified. Do not claim "Telegram alerts" without
  saying this.

## Screenshots

All screenshots use fictional organizations and people (`@example.com` addresses), taken from
the running app. The final set and the demo GIF were captured on 2026-11-24 with the **offline AI
provider** (the lead page says "offline AI"), because the day's Gemini budget was spent. To
recapture with Gemini after the budget resets (08:00 UTC): create a temporary owner with
`app.cli create-owner`, run `node scripts/final-shots.mjs <email> <pw-file> ../docs/portfolio/final`
from `frontend`, then delete the temporary owner. Gemini output appears in
`p5-02-lead-ai-analysis-and-score.png`. Final set: `docs/portfolio/final/` (1440×900, PNG + WebP). Earlier per-phase
shots: `docs/portfolio/p*.png`. Shot 7 (n8n canvas) is to be captured by the developer; shot 8
is the Telegram bot's connection test, cropped from a desktop screenshot (see `docs/DEMO_VIDEO_SCRIPT.md`).
