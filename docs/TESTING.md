# Testing

What is tested, how to run it, and what each check proves. All tests use fictional data. Tests
that need AI use the offline provider (`AI_PROVIDER=fake`), so they never spend the Gemini quota.

## Automated (CI on every pull request)

| Suite | Command | What it covers |
|---|---|---|
| Backend unit and API tests (361) | `cd backend; .\.venv\Scripts\python -m pytest` | Auth and sessions, roles, tenant isolation matrix (32 endpoints × 4 roles), CSRF, rate limits, CRM, CSV import, duplicates, AI pipeline (guard, grounding, scoring), red-team corpus, AI faults (timeouts, 429, invalid JSON, breaker), drafting and checks, approvals and claim-send, follow-ups and contact rules, reports, analytics reconciliation |
| Lint and format | `ruff check .`, `ruff format --check .`; `npm run lint`, `npm run typecheck` | Style, types |
| Frontend build | `npm run build` | The app compiles with Cache Components |
| Evaluation harness | `.\.venv\Scripts\python ..\evals\run_eval.py --provider fake` | The scoring pipeline end to end against 40 hand-labelled inquiries |
| Secret scan | gitleaks over the full history | No keys or passwords committed |

## End-to-end (local, needs the dev stack)

| Script | What it proves |
|---|---|
| `.\scripts\journey.ps1` | The 16-step MVP journey, 3 runs, each on a fresh `replyline_e2e` database, including killing the backend mid-flow (nothing lost) |
| `.\scripts\smoke.ps1` | Form → n8n → analysis → alert → draft → approve → email in Mailpit; redelivery creates no duplicates |
| `.\scripts\failure-injection.ps1` | n8n stopped, SMTP refusing, the backend restarted: leads wait and recover, nothing is sent twice |
| `.\scripts\load-smoke.ps1` | 130 concurrent submissions (100 unique + 30 repeats) → exactly 100 leads, all processed |
| `.\scripts\ui-audit.ps1` | Playwright clicks every page and control as a temporary owner; no console or server errors; axe accessibility scan of 18 pages |
| `.\scripts\restore-drill.ps1` | A fresh backup restores with identical row counts in every table |
| `bash scripts/deploy.sh --check` | On the production stack: HTTPS, internal API blocked, docs hidden, n8n and PostgreSQL not public |

## Live AI evaluation (manual, uses the Gemini quota)

`.\.venv\Scripts\python ..\evals\run_eval.py --provider gemini --sample 15` runs a stratified
sample and writes a report to `evals/reports/`. It stops cleanly at the daily budget
(`GEMINI_DAILY_BUDGET`) and resumes from `evals/cache/`. Latest:
[`2026-11-23-gemini-sample15.md`](../evals/reports/2026-11-23-gemini-sample15.md) (14 cases).

## Not covered yet

- A screen-reader (NVDA) walk-through (backlog #40).
- The full 40-case live Gemini evaluation (backlog #35).
- A run on a real public server (backlog #41).
