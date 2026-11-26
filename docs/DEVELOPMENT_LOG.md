# Development log

Newest first. Every new dependency gets a one-line justification here (contract rule C13).

## 2026-11-27: Backlog #39 decided (ADR 012)

- **Nonce CSP:** Next.js 16's bundled guide says nonces need dynamic rendering and are incompatible with Partial Prerendering (Cache Components).
- **Hash CSP via `experimental.sri`, tested:** the build passes, but `script-src 'self'` blocks Next.js's inline payload scripts (5 violations on `/f/harbor-web`) and the form never renders. Reverted.
- **Decision:** keep `'unsafe-inline'` for scripts and styles while Cache Components is on; mitigations listed in ADR 012 (React escaping, no inline scripts of our own, same-origin everything else, httpOnly cookies, CSRF). SECURITY.md updated (also the #38 note).

## 2026-11-26: Backlog fix pass, slice 2a (#38, #45)

- **#38 One n8n key for every organization:** API keys with the `internal:any-org` scope resolve the organization from the lead, draft or follow-up in the path (or the lead in a run/alert log body); sweeps (due follow-ups, check-in candidates, duplicate scan) cover every organization. Normal keys stay scoped (another organization's draft is never claimed). `seed-demo` gives the platform key the scope; the dev key was upgraded. Daily and source reports stay with the home organization. 4 tests.
- **#45 Settings → Services:** list, add and edit services (name, price range in whole currency units, keywords, offered or not); admins only. Added to the UI audit (add + edit + save) and the axe scan: 2/2 passed.
- **Note:** the UI audit's "Ask about this lead" step waited on Gemini (overloaded today) and timed out; audits now run with the offline provider (documented in TESTING.md).
- **Left for after the weekly reset:** #39 nonce-based CSP.

## 2026-11-26: Backlog fix pass, slice 1

- **#43 Gemini budget in PostgreSQL:** `usage_counters` with a guarded upsert (`app/core/counters.py`), so the count is shared by every worker and process and survives container restarts; the JSON file is only a fallback when the database is unreachable. Today's count was carried over from the file.
- **#42 Shared rate limits:** sliding window in `rate_limit_hits`, serialized per key with a transaction advisory lock; falls back to the per-process window if the database is down. Production runs 2 workers again. Tests: 30 parallel takes → exactly 18; 25 parallel hits → exactly 10.
- **#17 Telegram:** bot @reply_line_bot connected, chat id saved in `.env` (never printed). W1 Telegram variant in `n8n/workflows/variants/`, chosen by `import-workflows.ps1` and `deploy.sh` only when the token and chat id are set. On this network Telegram is reachable only with a system-wide VPN; without it W1 falls back to email (verified: `alert_failed` telegram → `alert_sent` email). Screenshot 08 (bot connection test) cropped from the developer's desktop screenshot, the original moved out of the repo.
- **#37, #46:** the smoke test approves through the API as a temporary approver and erases its lead afterwards (17/17); it now waits for W1's run log (the Telegram timeout adds about 20 s when Telegram is unreachable). `ui-audit.ps1` runs in a throwaway organization (`create-test-org`, `delete-org`; dev only, refuses the demo orgs; tests added): 2/2 passed.
- **Screenshots:** recapture with Gemini attempted; Gemini returned 503 on both models and then 429, so the set was recaptured with the offline provider again (labelled). Retry when Gemini is healthy.
- **Also:** `test_integrations_list…` no longer depends on the developer's `.env` (a real bot token is set now).

## 2026-11-24: Phase 12 (portfolio and freelance packaging): v1.0.0

- **README** rewritten in the §16.1 order (pitch, demo GIF, problem, status and honesty, architecture, stack, shipped features, screenshots, quick start, configuration, API, workflows, testing, deployment, roadmap, licence) with a CI badge.
- **New docs:** `PORTFOLIO_CLAIMS.md` (every claim → evidence; numbers with caveats; claims we do not make), `CASE_STUDY.md`, `DEMO_VIDEO_SCRIPT.md` (90 s and 3–5 min cuts), `FREELANCE_OFFERS.md` (Fiverr/Upwork drafts with sourced price research, LinkedIn series), `CLIENT_DELIVERY_KIT.md`, `TESTING.md`.
- **Screenshots:** `frontend/scripts/final-shots.mjs` drives a fictional lead through the real stack and saves 8 shots (1440×900, PNG + WebP) and an animated GIF, encoded inside headless Chromium (canvas + a small GIF encoder), so no image library was installed. Captured with the offline AI provider (the Gemini budget was spent; see below). Shots 07 (n8n canvas) and 08 (Telegram) are for the developer.
- **Bug found and fixed (from the screenshot run):** the stuck-lead sweeper requeued leads still in "processing" after 45 s, while one analysis can take about 4 minutes on Gemini timeouts (2 models × 3 attempts × 30 s). The duplicate runs spent the whole daily budget in 8 minutes. Now "processing" waits 5 minutes (test added); `journey.ps1` step 16 waits up to 400 s.
- **Also fixed:** draft topics keep acronyms ("AI chatbot", not "ai chatbot"; test added); Approvals labels check-in drafts "Check-in" instead of "First reply"; the UI-audit spec restores the draft text it edits (5 runs had left "Thanks again." ×5 in a demo draft; cleaned); 9 leftover smoke/test leads erased from the demo org.
- **Temporary screenshot owner** created in harbor-web and deleted afterwards (with its sessions); its password file deleted.
- **Not done (developer):** pin the repo, record the video, n8n and Telegram shots, decide the licence and prices, publish the case study/LinkedIn posts.

## 2026-11-24: Phase 11 (deployment, prepared, not live)

- **Production stack:** `infra/compose.prod.yml` (PostgreSQL, n8n, backend, frontend, Caddy). Only Caddy is public; n8n is bound to the server's 127.0.0.1 (SSH tunnel for the editor); PostgreSQL is never published. The backend gets an explicit environment list (no superuser or n8n secrets).
- **Images:** `backend/Dockerfile` (python:3.14-slim, non-root, healthcheck, migrations on start, 1 worker so the in-memory rate limits stay exact) and `frontend/Dockerfile` (Next.js standalone, node:24-alpine, non-root). Inspected: no `.env` and no secret values inside the images.
- **HTTPS proxy:** Caddy 2.10 with automatic Let's Encrypt, HSTS, compression; `/api/v1/internal/*` and the API docs return 404 from outside.
- **Code changes:** `TRUSTED_PROXIES` CIDR setting so the client IP comes from X-Forwarded-For only behind a configured proxy (test added); `AI_USAGE_FILE` override for the Gemini daily budget file (the container root is read-only for the app user).
- **Scripts:** `scripts/deploy.sh` (refuses REPLACE_ME values, builds, waits for health, seeds the demo org, imports n8n credentials with output hidden, imports and activates the 9 workflows, runs the checks; `--check` runs only the checks), `backup-prod.sh` (nightly, 14 days), `reset-demo.sh` (public demo reset).
- **Runbook:** `docs/DEPLOYMENT.md`: server choice with sourced prices, DNS, SPF/DKIM/DMARC, server hardening, first deploy, checks, backups and restore, updates and rollback, monitoring, public demo.
- **Verified locally (production rehearsal, `TLS_MODE=internal`, ports 8080/8443):** all 5 containers up; all 6 checks pass; journey on the production stack: form 201 → AI done (high) → draft → approve → sent → email in Mailpit; W1 and W4b successful. Stack torn down with `down -v`, the local `.env.production` deleted.
- **Not done (needs the developer):** buying a server and a domain, DNS records, a real SMTP service. No purchase was made.
- **Fixed on the way:** image pulls failed with "short read" (retried); Caddy can't nest env defaults (moved into compose); Git Bash rewrote `/tmp` paths (`MSYS_NO_PATHCONV`, repo-relative temp dir); the public-address n8n probe gave a false failure on localhost (replaced with port-binding checks).

## 2026-11-24: Phase 10 (security, QA and reliability hardening): v0.2.0

- **Authorization and isolation:** `test_security_matrix.py`: 32 endpoints × anonymous/member/admin/owner and 21 isolation checks across every resource type; CSRF; headers.
- **Headers:** API CSP `default-src 'none'`, frame DENY, nosniff, no-referrer, no-store, HSTS over HTTPS; frontend same-origin CSP (unsafe-inline for Next.js, documented), frame DENY, no X-Powered-By.
- **Audits:** pip-audit clean; npm production deps clean (shadcn CLI moved to devDependencies, 4 moderate dev-only findings accepted); gitleaks scans the full history in CI.
- **Load smoke:** 130 concurrent requests (100 unique + 30 duplicates) → exactly 100 leads, all processed by n8n within 30 s, nothing duplicated (`scripts/load-smoke.ps1`).
- **Accessibility:** axe over 18 pages, no critical issues; one serious (colour-only links) fixed.
- **Backup and restore drill:** `scripts/backup.ps1` + `restore-drill.ps1`: 27 tables restored with identical counts.
- **PII review:** logs contain metadata only; n8n executions pruned after 14 days.
- **Found by the final UI audit:** an intermittent 500 when the Next.js proxy reused a keep-alive connection uvicorn had just closed (5 s default). The backend now runs with `--timeout-keep-alive 65` (scripts and README).
- `docs/SECURITY.md` final.

## 2026-11-24: Phase 9 (analytics, reports, settings, team)

- **Analytics:** `/analytics/sources`, `/funnel`, `/team`, `/export` and the Analytics page (Sources, Funnel, Team, Reports; 30/90/365 days; CSV). **Gate:** a test seeds 40 fictional leads and checks every Overview card, the trend, sources, funnel and team figures against independent raw SQL.
- **Reports (W8 daily, W10 weekly sources):** SQL metrics saved as `report_snapshots`; once per period, in each organization's own 08:30–09:29 window. AI prose is kept only if every number in it is one of the metrics; otherwise a template is used (validator tests, incl. invented and derived numbers). Fixed on the way: the template's own "Last 7 days" was rejected until the period became a metric.
- **Team:** invitations (hashed token, 7 days, one open per address, member or admin), accept page that creates or verifies the account and logs in, revoke, audit rows, invitation email via SMTP; role changes and removal in Settings · Team.
- **Settings:** scoring preview on recent leads (nothing saved), pipeline editor, notification preferences, follow-up limits, data retention with erasure of old archived leads.
- **Verified:** 302 backend tests; UI audit extended to every new page (no console or server errors); journey 1/1; live browser invite → accept.

## 2026-11-24: Phase 8 (follow-ups, duplicates, recovery)

- **Contact rules in one place** (`services/followups.contact_check`): open stage, no reply logged, not do-not-contact, not on the suppression list, has an email, fewer than 3 emails, 3-day cooldown (attempts and cooldown configurable per org). Used by follow-up preparation, recovery, approval and the send claim; an address suppressed after approval cancels the send.
- **Suppression and replies:** `suppressions` table; "Customer replied" logs an inbound message and stops follow-ups; "Opt out" suppresses the address, sets do-not-contact and cancels open drafts and follow-ups.
- **Follow-ups:** every sent email closes its follow-up and schedules the next while the rules allow; manual scheduling, skip with reason, prepare now. W5 prepares due follow-ups hourly, only inside each organization's business hours in its own timezone (tested for Karachi and Los Angeles, weekends excluded). Never sends.
- **Recovery (W6):** open leads quiet 14+ days, contactable, not recovered in 30 days → check-in draft; reasons come from stored records ("reason unknown" otherwise). Idempotent.
- **Duplicates (W7):** daily scan that never merges; merge preview (field by field, records that move) before a person confirms; merges were already audited.
- **Sweeper (W9b):** requeues failed outbox events and delivers stalled ones itself, re-sends leads stuck by a crash, retries failed analyses.
- **UI:** Follow-ups page, lead "Contact & follow-ups" panel, merge preview; timeline labels for every new event.
- **Fixed by the live run:** the Gemini budget lock crashed under concurrent requests (stat on a just-released lock; on Windows a delete-pending lock raises PermissionError), which turned W6 calls into 500s and retries into extra drafts. Lock fixed (40-thread test), recovery made idempotent.
- Tests: 284 backend (14 P8 gate tests).

## 2026-11-23: Phase 7 (MVP gate and demo readiness): v0.1.0-mvp

- **Gate:** the 16-step journey passed **3 of 3 runs, each from a freshly created database** (`scripts/journey.ps1`: Playwright steps 1-15, then the backend is killed mid-flow and restarted). UI action audit: every row passes (`docs/UI_ACTION_AUDIT.md`, `scripts/ui-audit.ps1` with zero console or server errors). CI green. Pending: the developer's live demo rehearsal (`docs/DEMO_SCRIPT.md`).
- **Found by the gate and fixed:** a lead stayed "pending" forever when n8n called back while the backend was down. The backend now re-sends the intake event for stuck leads (max 3) at startup and every 30 s.
- **Overview dashboard:** stat cards (new leads with change, high priority, waiting for approval, median time to first reply vs target), new-leads-per-day chart (validated colour, hover, table view), priority mix, pipeline, latest leads with next step, automation strip; `/analytics/overview` and `/analytics/trends` (numbers reconciled with SQL in tests).
- **Demo data:** `scripts/seed.ps1` (152 fictional leads over 60 days, reply history, 2 near-duplicates); `create-owner` dev command.
- **Bug bash:** on phones the sidebar stacked above every page; it is now a drawer (Menu button, Escape, closes on navigation). Chart edge labels were clipped; fixed.
- **Performance:** API p95 under 60 ms on 163 leads (Automation overview 104 ms with its live n8n check); pages under ~1 s at phone width (`docs/PERFORMANCE.md`).
- README v1, demo script, P7 screenshots. Tests: 266 backend.

## 2026-11-23: Phase 6 (automation, approvals, sending)

- **Draft lifecycle:** `communication_drafts`, `communication_logs`, `follow_ups`. Drafts are saved as `pending_approval` (one open draft per lead and kind); edits rerun the checks; approval reruns checks and contactability, writes an audit row and emits `draft.approved`; rejection needs a reason. The send path is a single atomic claim (`approved → sending`), proven by behavioural tests and a static guard ("no code path sends unless approved").
- **n8n:** W1 now writes a reply draft after analysis and logs its alerts; W4b claims, sends by SMTP (Mailpit), and reports sent (message id, follow-up in 3 days) or failed; W9 logs failures and emails the admin when the backend says `should_alert` (one per workflow per 10 minutes). Telegram branch ready behind `build_p6_workflows.py --telegram` (bot pending).
- **UI:** Approvals screen (queue by score, lead context, read-only recipient, locked opt-out footer, live checks, reject with reason, Ctrl+Enter, J/K), lead drafts go to the queue, Automation Center v1 (journey, workflow cards, outbox health, runs in plain words), Integrations v1 with Test connection.
- **Verified:** `smoke.ps1` 17/17 (form to Mailpit, redelivery of both events creates nothing new); `failure-injection.ps1` 13/13 (n8n stopped: lead kept and processed after recovery; SMTP down: draft failed, never re-sent); 262 backend tests; Playwright journey.
- **Fixed on the way:** `.env` `AI_PROVIDER` held its comment (no space before `#`), so exact checks failed; the setting now keeps only the first word.
- **Deviations / limits:** W2/W3/W4 run inline in W1 (backlog #36); one org-scoped n8n service key (#38); smoke approves through the service layer (#37).

## 2026-11-23: Phase 5 (AI intelligence), build complete; first live eval report committed

- **Pipeline:** guard (NFKC, invisible characters, 4,000-char cut, injection tripwires) → prompt `analysis-v1` (customer text as a tagged data block) → Gemini structured output → grounding (every fact needs a real quote; budgets re-parsed by code) → deterministic 7-factor scoring with per-org versioned weights → `lead_analyses` + `lead_scores` history. Cache by input hash and provider.
- **Reliability:** timeout, retries with backoff and Retry-After, fallback model, circuit breaker, per-org daily cap, provisional score on any failure, automatic retry worker; fault-injection tests for 429, 5xx, timeout, malformed JSON and unknown fields.
- **Drafts (preview):** prompt `draft-v1`, code checks (catalog services, catalog prices, link allow-list, no promised dates/meetings/discounts/attachments, length, opt-out line added by code, do-not-contact, language warning), template fallback, no drafts for spam or job seekers, follow-up drafts after code-decided eligibility.
- **Assistant:** Lead Q&A grounded in that lead's records with validated citations; text playground (nothing saved); AI settings (default style, daily cap); re-score action without AI calls.
- **Evaluation:** 40-case dataset (11 categories incl. Urdu, Roman Urdu, PKR), resumable runner, report with field accuracy, band agreement, rejection rate, latency and tokens. **First live Gemini report** (`evals/reports/2026-11-23-gemini-sample15.md`): 14 of a 15-case stratified sample scored inside the daily budget; band agreement 93%, service and budget 100%, grounding rejection 1.6%, no schema-invalid output, mean latency 10.2 s.
- **Quota budget:** shared daily Gemini budget (18 calls, under the free-tier quota), counted across processes; daily-quota 429s close the day instead of retrying.
- **Red team:** 16 techniques in the test suite (no score boost, no leakage, schema-valid); the guard flags or truncates all 16 and flags none of the 38 honest inquiries.
- **UI:** AI analysis panel (facts with quotes), "Why this score" factor bars, reply draft panel with live checks, Ask panel, AI Assistant page, Settings (Lead scoring, AI), sample-data buttons.
- **Fixed on the way:** money parser (European `4.000`, lakh as rupees, word boundaries, decimals, small numbers hiding budgets); `created_at` used Postgres `now()` (transaction start) so "latest" picks were random within a transaction, now a strictly increasing Python default; Gemini typed schema rejected `additionalProperties` (switched to JSON Schema).
- **Quota:** the free-tier daily quota ran out after about 30 calls; the n8n W1 analyze timeout is now 60 s.
- Decisions: ADR 011. Tests: 243 backend, Playwright journey passes.

## 2026-11-23: Phase 4 (auth, organizations, CRM core)

- **Auth (D7):** argon2id passwords; 15-minute access JWT and rotating refresh token, both httpOnly cookies (refresh scoped to `/api/v1/auth`); reuse of a rotated refresh token revokes the whole login family; membership and role re-checked on every request; CSRF = custom header + origin check; login rate limit; temporary P3 dev access removed. `app.cli set-demo-owner` creates the developer's login with a hidden password prompt.
- **Same-origin proxy:** Next.js forwards `/api/*` to FastAPI so session cookies are first-party; the backend trusts `X-Forwarded-For` only from the local proxy.
- **Organization:** default pipeline stages and sources for every organization (data migration for existing ones), service catalog with price ranges, team roles (last owner protected; only owners grant ownership), business profile; tenant scoping helpers (`scoped`, `get_owned`) so a foreign id looks missing (404).
- **CRM:** create / edit / search (trigram + `word_similarity` for typos) / filters / sort / pages; stage changes; assignment; notes; activity timeline (per-row Python timestamps, since `now()` ties within a transaction); archive and restore; admin-only erasure with an anonymous audit row; audit log for role changes, removals, imports, exports, merges.
- **Data:** CSV import with preview, column guessing, per-row errors, 2 MB / 5,000-row limits and exact-match merging; admin-only export with formula-injection protection; fuzzy duplicate scan with human-only merge or dismiss.
- **Frontend:** app shell and sidebar from the mockups (unbuilt screens marked "Soon"), Leads list with filters and New-lead dialog, Lead detail (stage, assignee, contact edit, messages, notes, timeline, archive, erase), CSV import, duplicate review, login and sign-up; types generated from OpenAPI.
- **Bug found by the browser test:** the New-lead modal stayed open in the hidden previous page after navigating, making the next page unclickable. Fixed by closing it before navigating and on cleanup.
- **Gate Verified:** 90 backend tests (authz, isolation matrices, CSV, duplicates); Playwright journey register → new lead → stage → note → CSV import → search → export passes 3 of 3 runs (7.1 s, 5.9 s, 5.5 s); frontend lint, typecheck and build pass; `npm run gen:api` regenerates without errors; smoke 8 of 8.
- **Dependencies added (C13):** `argon2-cffi` (password hashing), `pyjwt` (access tokens), `phonenumbers` (E.164 normalization), `openapi-typescript` (typed client), `@playwright/test` and Chromium (end-to-end tests).

## 2026-11-22: Phase 3 (walking skeleton)

- **Schema:** first Alembic migration with the 8 P3 tables (all tenant tables carry `organization_id`); up, down and up again Verified. A separate `replyline_test` database for integration tests.
- **Fixed:** every database connection waited for an IPv6 attempt because `localhost` resolves to `::1` first on Windows while Docker publishes on 127.0.0.1 only; Alembic went from minutes to 3.2 s after switching to 127.0.0.1. The same fix applies to backend → n8n webhooks.
- **Backend:** public intake (form key, honeypot, per-IP rate limit, normalized email, dedupe as a new inquiry, idempotency key, outbox row in the same transaction); outbox dispatcher (SKIP LOCKED, backoff 15 s doubling to 10 min, max 8 attempts, redispatch); internal API behind a hashed service key; FakeAIProvider (labelled "fake"); delivery-once claims on `Idempotency-Key`.
- **n8n:** W1 Lead Intake imported from JSON with placeholders filled from `.env` and activated by `scripts/import-workflows.ps1`. Webhook refuses calls without `X-Webhook-Secret` (403 Verified).
- **Frontend:** `/leads` (real rows, polls while AI works, loading / empty / error states) and `/f/[slug]` (public form inside `Suspense`, as Next.js 16 requires for `useParams` with Cache Components).
- **Gate Verified:** form → lead row → n8n execution → fake score 95 (high) → Mailpit alert → `workflow_executions` row with the caller's request id, in 1.2 s. Same event delivered twice → one alert, repeat logged as `skipped`, still one lead and one inquiry. n8n stopped and backend killed mid-delivery → event delivered 41 s after restart, nothing lost. `scripts/smoke.ps1` repeats the checks (8 of 8 pass).
- **Tests:** 21 backend tests pass against the real test database (intake, dedupe, idempotency, honeypot, validation envelope, rate limit, service-key auth, cross-org 404, fake analysis, run upsert, outbox delivery, retry, failure, backoff).
- **Dependencies added (C13):** `httpx` moved to runtime (outbox HTTP client).
- **Deviation:** W1 does the alert and logging inline instead of calling W0/W3 sub-workflows (backlog #16). Telegram still pending the bot (backlog #17).

## 2026-11-22: Phase 2 gate passed

- GitHub: private repo `ZeeRiz99/N8N-Work-Flow` created; `main` and `phase/02-foundation` pushed; PR #1 opened.
- CI green on GitHub: backend (24 s), frontend (40 s), secret scan of the full history (8 s, no leaks).
- **Deviation:** the gitleaks GitHub Action failed on the pull request without a finding; CI now runs the gitleaks CLI v8.30.0 directly. Actions moved to their Node 24 versions.
- Gate items Verified: infra starts from the spaced path; `/ready` green; frontend loads; n8n workflow reaches the backend; AI smoke (Gemini) OK; CI green; secret scan clean; fresh clone works. **Deferred:** Telegram test message (ADR 005; email fallback Verified).
- n8n owner account created by the developer.

## 2026-11-22: Phase 2 (foundation) progress

- **Installed:** Docker Desktop 4.99.0 (engine 29.9.3) via winget. WSL capped at 3 GB (`.wslconfig.bak` kept). Disk image left on C: (backlog #12).
- **Images (pinned):** `postgres:18.7`, `n8nio/n8n:2.47.4`, `axllent/mailpit:v1.34.0`; 2.69 GB on disk. Runner image only behind the `code-nodes` profile.
- **Measured RAM:** n8n 383 MB, PostgreSQL 154 MB, Mailpit 27 MB (about 565 MB for the stack).
- **Verified:** two databases and roles; each role is refused on the other database; `citext` and `pg_trgm` present; n8n created 178 tables in its own database.
- **Verified:** backend `/ready` = 200 with `database: ok`; from inside the n8n container `host.docker.internal:8000/health` = 200 with the request id echoed; an imported n8n workflow (`RL | Util | P2 backend ping`) ran with status `success`.
- **Verified:** SMTP to Mailpit delivered; n8n reaches `mailpit:1025`.
- **Verified:** credentials RL Backend Service Key, RL Webhook Secret, RL SMTP imported from `.env` and stored encrypted; no secret printed, no temp files left.
- **Dependencies added (C13):** `google-genai` 3.6 (Gemini provider), `openai` 3.57 (OpenAI provider; developer's choice), `pre-commit` (secret scan and lint hooks), Prettier 3.10 (frontend formatting), shadcn/ui CLI and `cn` (shadcn's own class-merge helper, replaces clsx + tailwind-merge).
- **AI:** developer chose OpenAI for the smoke test. Key verified (HTTP 200 on the free model list, 8 small models). The test call was refused with `credit_balance_exhausted`: the OpenAI account needs prepaid credit. No Gemini key yet.
- **AI smoke Verified (Gemini, free tier):** key accepted (new `AQ.` format, 53 chars), 12 Flash models listed; `gemini-3.8-flash` and `gemini-3.7-flash` returned 503, `gemini-3.6-flash` returned valid structured JSON in 61 s. The smoke test now skips preview/image/lite models and falls back to the next one.
- **Fresh clone Verified:** clone → `new-env.ps1` → compose config → backend install and 5 tests → frontend `npm ci`, lint, typecheck, build. It found one bug (typecheck needed `next typegen` on a clean checkout), fixed.
- **Fixed on the way:** gitleaks hook download reset once (retry worked); PowerShell 5.1 adds a BOM to piped text (stripped in the container); n8n's import error echoes its input, so credential import output is now hidden; a leftover log from the first failed attempt was deleted from the container.

## 2026-11-21: Phase 1 gate passed

- Developer approved the installation plan, the architecture and ADRs 001–010, and the draft schema ("ok to go").
- **Deviation:** merged `phase/01-discovery` into `main` locally (no GitHub remote yet, no CI yet). From P2 on, phases merge through pull requests once the repo exists.

## 2026-11-21: Phase 1 (discovery and architecture)

- Master prompt v2 reviewed top to bottom; v3 written (42 exact-text edits, all matched). Backup of v2 kept outside the repo.
- Product named **Replyline** after a web search of candidates (ADR 007).
- Design canvas updated: 4 screens fixed, 4 added (ADR 009). Static copies in `docs/design/mockups/` with working links.
- Git: branch renamed to `main` before the first commit; global `init.defaultBranch=main`.
- **Installed:** GitHub CLI 2.105.0 via winget (needed for the PR-per-phase workflow; approved by the developer).
- **Deviation:** `.gitattributes` (`* text=auto eol=lf`) added in P1 instead of P2, because Git for Windows was about to convert files to CRLF on the first commit.
- Docs added: installation plan, ADRs 001–010, architecture, draft schema, API skeleton, security stub, project plan, backlog, draft `CLAUDE.md` and settings.
- Not verified: the Mermaid diagrams have not been rendered yet (no renderer installed); check them on GitHub or in VS Code after P2.

## 2026-11-20: Environment audit

- `scripts/inspect-env.ps1` run (read-only). Key findings: 7.8 GB RAM; Docker not installed; Python 3.14.6 only; Node 24; ports free; api.telegram.org blocked (DNS resolves, TCP times out).
