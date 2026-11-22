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
| 15 | Dashboard reads use temporary dev access (development + 127.0.0.1 + demo org) | `require_dev_access` | P4: replace with login, cookies and RBAC; delete the dev path |
| 16 | W1 does analyze, alert and logging inline; W0 (Log Run) and W3 (alert) are not separate sub-workflows yet | `n8n/workflows/rl-w1-lead-intake.json` | P6: split into W0, W2, W3, W4 sub-workflows as in master prompt §9.3 |
| 17 | Alerts go by email only; Telegram waits for the bot token and a system-wide VPN | W1 | P3 follow-up as soon as the bot exists (ADR 005) |
| 18 | After a cold backend start, the first outbox delivery can take a few seconds longer than the 1.2 s warm path | outbox worker | Measure in P7 demo rehearsal; pre-warm the backend before demos |
| 19 | Frontend API client is hand-written | `frontend/src/lib/api.ts` | P4: generate from FastAPI's OpenAPI (`openapi-typescript`, D6) |
