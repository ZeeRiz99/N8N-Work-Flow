# Backlog of known limits

Each phase logs its known limits here. They are fixed together after the last build phase, unless one blocks a gate.

## From Phase 1

| # | Limit | Where | Fix later |
|---|---|---|---|
| 1 | `inspect-env.ps1` flags disks under 20 GB, but the master prompt wants D: flagged under 30 GB | `scripts/inspect-env.ps1` | Align the threshold |
| 2 | Network check is TCP-only; it cannot tell DNS failures from blocking | `scripts/inspect-env.ps1` | Add a DNS lookup step |
| 3 | The audit does not check `git config core.longpaths`; Windows long paths are disabled | `scripts/inspect-env.ps1` | Add the check; consider enabling long paths (system setting, ask first) |
| 4 | Follow-ups, AI Assistant, Analytics and Integrations screens are not drawn | `docs/design/` | Draw before P8–P9 or design in code from the tokens |
| 5 | Mockups have no loading, empty or error states | `docs/design/` | Built in code (master prompt §10.5) |
| 6 | Mermaid diagrams in the docs are not rendered or checked | `docs/ARCHITECTURE.md`, `docs/DATABASE_SCHEMA.md` | Render after P2 and fix any syntax errors |
| 7 | Gemini key and billing status unknown | §8.8 | Ask in P2; synthetic data only until billing is confirmed |
| 8 | Telegram needs a system-wide VPN on the dev network | ADR 005 | None needed for production; document for demos |

## From Phase 2

| # | Limit | Where | Fix later |
|---|---|---|---|
| 9 | Starlette warns that `TestClient` with `httpx` is deprecated and suggests `httpx2` | `backend/tests` | Switch the dev dependency once `httpx2` is stable for FastAPI's test client |
| 10 | `npm audit`: 4 moderate findings, all one chain inside the shadcn CLI (shadcn → ts-morph → minimatch glob DoS); dev tooling only, not served code. Only fix offered is a forced breaking upgrade | `frontend/package.json` | Re-check in P10 dependency triage; upgrade shadcn when a non-breaking fix exists |
| 11 | ESLint 9.39 is reported as no longer supported by create-next-app's template | `frontend` | Move to the ESLint version `eslint-config-next` supports when it does |
| 13 | Gemini free tier: newest Flash models (3.8, 3.7) returned 503; `gemini-3.6-flash` answered in 61 s, above the 30 s AI timeout | `scripts/ai_smoke.py`, P5 provider | P5: measure again, choose `GEMINI_MODEL` and `GEMINI_MODEL_FALLBACK` from real latency, keep the provisional-score path for timeouts |
| 12 | Docker's disk image stays on C: (`%LOCALAPPDATA%\Docker\wsl`), not `D:\docker` as planned | Docker Desktop settings | Move it with Settings → Resources → Advanced → Disk image location if C: drops below ~15 GB free |

## From Phase 3

| # | Limit | Where | Fix later |
|---|---|---|---|
| 14 | Public-form rate limit is in memory, per process; restarts reset it and several workers would not share it | `app/api/deps.py` | P10: move to PostgreSQL or Redis-backed limits behind the reverse proxy |
| 15 | ~~Dashboard reads use temporary dev access~~ **Fixed in P4** (login, cookies, roles; dev path deleted) | — | — |
| 16 | W1 does analyze, alert and logging inline; W0 (Log Run) and W3 (alert) are not separate sub-workflows yet | `n8n/workflows/rl-w1-lead-intake.json` | P6: split into W0, W2, W3, W4 sub-workflows as in master prompt §9.3 |
| 17 | Alerts go by email only; Telegram waits for the bot token and a system-wide VPN | W1 | P3 follow-up as soon as the bot exists (ADR 005) |
| 18 | After a cold backend start, the first outbox delivery can take a few seconds longer than the 1.2 s warm path | outbox worker | Measure in P7 demo rehearsal; pre-warm the backend before demos |
| 19 | Frontend API client is hand-written | `frontend/src/lib/api.ts` | Partly fixed in P4: types generated from OpenAPI (`npm run gen:api`) for auth and settings; see #20 |

## From Phase 4

| # | Limit | Where | Fix later |
|---|---|---|---|
| 20 | Lead, notes, timeline, import and duplicate endpoints return plain dicts, so their OpenAPI types are empty and the frontend types for them are hand-written | `app/api/v1/leads.py`, `data.py` | Add Pydantic response models, regenerate `api-schema.d.ts` |
| 21 | Next.js 16 keeps the previous page mounted but hidden (React Activity); the hidden Leads table keeps polling every 15 s | `leads-table.tsx` | Pause polling while hidden (`document.visibilityState` / Activity-aware effect) |
| 22 | The Playwright journey needs the full local stack, so it is not in CI yet | `frontend/e2e` | P10/P11: run it in CI against compose services |
| 23 | E2E runs leave "E2E Test" organizations in the dev database (cleaned by hand after runs) | dev DB | Add a cleanup step or a dedicated e2e database |
| 24 | No invite flow yet: new team members can only be added by sign-up or the CLI | `app/api/v1/org.py` | P9: member invites (master prompt §13 P9) |
| 25 | Running backend processes do not reload code; after pulling changes, restart the backend (the e2e run hit this) | dev workflow | Document in README; use `--reload` while developing |

## From Phase 5

| # | Limit | Where | Fix later |
|---|---|---|---|
| 26 | A lead whose analysis failed (outage, quota) keeps a provisional score until someone clicks Re-analyze or a new message arrives; nothing retries it automatically | `services/analysis.py` | Scheduled retry of `ai_status=failed` leads with backoff (P6 scheduler / P11) |
| 27 | The Gemini free tier has a small daily request quota (used up on 2026-11-23 after ~30 dev, smoke and seed calls); `AI_DAILY_CALL_CAP` defaults to 500, far above it | `.env`, `core/config.py` | Document the free-tier quota; lower the default cap; surface "AI quota reached" in the UI |
| 28 | Portfolio shot `p5-04` (prompt injection) shows the fallback view because the quota ran out before that lead was analyzed | `docs/portfolio` | Re-run `seed-portfolio` + `portfolio-shots.mjs` after the quota resets |
| 29 | Changing scoring weights affects only new and re-analyzed leads; there is no preview of how existing leads would move, and no bulk re-score | `/settings/scoring` | "Preview on recent leads" and an admin bulk re-score (no AI call needed) |
| 30 | Re-analyze runs synchronously in the request (Gemini took 1 to 20 s); a slow provider holds the button | `api/v1/ai.py` | Queue through the outbox and poll, as new leads do |
