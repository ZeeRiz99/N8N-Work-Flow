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
| 26 | ~~No automatic retry of failed analyses~~ **Fixed in P5:** retry worker with backoff (ADR 011) | `services/analysis.py` | Done |
| 27 | ~~Free-tier quota exhausted in a day~~ **Fixed in P5:** shared daily Gemini budget (18, under the quota; `app/ai/budget.py`), daily-quota 429 not retried | `app/ai` | Done |
| 28 | ~~p5-04 showed the fallback view~~ **Fixed:** re-shot with a live Gemini analysis | `docs/portfolio` | Done |
| 29 | Re-score exists (P5), but there is no live preview of how leads would move before saving new weights | `/settings/scoring` | "Preview on recent leads" before saving |
| 30 | Re-analyze runs synchronously in the request (Gemini took 1 to 20 s); a slow provider holds the button | `api/v1/ai.py` | Queue through the outbox and poll, as new leads do |
| 31 | Reply drafts are previews only: not saved, no approval, no send | `services/drafting.py` | P6: `communication_drafts`, Approvals screen, send via W4b (ADR 011) |
| 32 | Follow-up eligibility cannot see customer replies (no inbound tracking yet) | `services/assistant.py` | P6/P8: communication logs feed the "no reply" rule |
| 33 | The playground shows "None found" when the AI is unavailable (no facts without the model) | `/assistant` | Optionally show the offline keyword view, clearly labelled |
| 34 | Sample-data names use simple combinations; a twin's typo is "a" doubled, which looks odd ("Hinaa") | `services/sample_data.py` | Use a small typo list (swap, drop a letter) |
| 35 | Live Gemini eval covers 14 of 40 cases (budget-limited); the rest resume from the cache on later days | `evals/` | Run `run_eval.py --provider gemini` (no sample) over the next days until complete |

## From Phase 6

| # | Limit | Where | Fix later |
|---|---|---|---|
| 36 | W1 runs analyze, alert and draft inline instead of calling W2/W3/W4 sub-workflows (§9.3) | `n8n/workflows/rl-w1-lead-intake.json` | Split into Execute-Workflow sub-workflows once n8n workflow ids are pinned in the import script |
| 37 | The smoke test approves through the service layer (no browser login in the script) | `scripts/smoke.ps1` | Approve through the API with a smoke user, or via Playwright |
| 38 | n8n holds one service key, scoped to one organization; approved drafts in other organizations are never claimed for sending (claim-send is org-scoped) | `api/deps.py`, n8n credentials | Platform service key (scope `internal:any-org`) that resolves the org from the draft or lead id; or one n8n credential per org |
