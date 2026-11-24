# Replyline

**Turn incoming leads into organized business opportunities.**
Replyline captures every inquiry, understands it with AI, scores it with transparent rules, alerts
the team, drafts the reply for human approval, and makes sure nobody is forgotten. n8n runs the
automation; the backend makes every decision; a person approves every outbound message.

> **Project status and honesty.** A self-developed portfolio project, MVP complete
> (`v0.1.0-mvp`, phase 7 of 12). All data is fictional. No customers, revenue or time-saving
> claims. AI accuracy numbers come only from committed evaluation reports, with the sample size
> stated.

![Lead detail with AI analysis and score explanation](docs/portfolio/p5-02-lead-ai-analysis-and-score.png)

## What it does (shipped)

- **Capture:** public web form (consent, honeypot, rate limit), manual entry, CSV import with
  preview; exact and fuzzy duplicate detection with human-only merge.
- **Understand:** Gemini extracts facts, and **every fact must quote the customer's own words**
  (grounding); unquoted claims are dropped. Prompt-injection text is flagged and never raises a
  score.
- **Score:** deterministic, configurable 7-factor rules (versioned per organization) with a
  plain-language explanation and factor bars. The AI never sets a number.
- **Act:** high-priority alerts, reply drafts with automatic checks (prices from your service
  list, no promised dates or discounts, link allow-list, opt-out line added by code), an
  **Approvals queue**, and sending only after a person approves (exactly once).
- **Keep going:** follow-up scheduled after each sent email, Lead Q&A grounded in that lead's
  records, an AI Assistant playground, Overview dashboard, Automation Center, Integrations.
- **Reliable:** transactional outbox, idempotency keys, retries with backoff, circuit breaker,
  provisional scores when the AI is down, automatic recovery of leads stuck by a crash.

## How it works

```
Form / CSV / manual ─► FastAPI backend ──outbox──► n8n W1 ─► backend: analyze (Gemini + grounding + rules)
                         ▲   decides everything        │      ├─ High? alert the team
                         │                             │      └─ write reply draft ─► Approvals queue
                         └──── internal API ◄──────────┘                                 │ a person approves
                                                         n8n W4b ◄── draft.approved ◄────┘
                                                           └─► claim once ─► SMTP ─► sent + follow-up
```

Tech: FastAPI (Python 3.14, SQLAlchemy 2, Alembic) · Next.js 16, React 19, TypeScript, Tailwind 4 ·
PostgreSQL 18 · n8n 2 · Gemini (`gemini-3.6-flash`) · Mailpit · Docker Compose · GitHub Actions.

## Evaluation (real numbers only)

[`evals/reports/2026-11-23-gemini-sample15.md`](evals/reports/2026-11-23-gemini-sample15.md):
live Gemini run on a 15-case stratified sample of a 40-inquiry fictional dataset (14 scored
within the daily budget). Priority band agreement 93%, service and budget extraction 100%,
grounding rejected 1 of 62 claims, no schema-invalid output. A small sample: one case moves a
percentage by about 7 points. A red-team corpus of 16 prompt-injection techniques runs in the
test suite.

## Screenshots

| | |
|---|---|
| ![Leads sorted by AI score](docs/portfolio/p5-01-leads-sorted-by-ai-score.png) | ![Approvals queue](docs/portfolio/p6-01-approvals-queue.png) |
| ![Prompt injection flagged](docs/portfolio/p5-04-prompt-injection-flagged-for-review.png) | ![Automation Center](docs/portfolio/p6-02-automation-center.png) |
| ![Overview dashboard](docs/portfolio/p7-01-overview.png) | ![Scoring settings](docs/portfolio/p5-06-scoring-settings.png) |

## Quick start (Windows, PowerShell)

Prerequisites: Git, Docker Desktop (WSL 2), Python 3.14, Node.js 24. The path contains a space,
so **quote every path**.

```powershell
cd "D:\Projects\N8N Work Flow"
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\new-env.ps1   # .env with random secrets
.\scripts\set-secret.ps1 GEMINI_API_KEY        # optional: paste from the clipboard, never printed
.\scripts\dev.ps1 up                           # PostgreSQL, n8n, Mailpit

cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\alembic upgrade head
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --timeout-keep-alive 65
# in a second terminal, still in backend:
.\.venv\Scripts\python -m app.cli seed-demo
.\.venv\Scripts\python -m app.cli set-demo-owner          # your login (password typed hidden)
cd ..
.\scripts\seed.ps1                             # ~150 fictional leads over 60 days
.\scripts\n8n-credentials.ps1
.\scripts\import-workflows.ps1 -Activate       # W1, W4b, W9

cd frontend; npm ci; npm run build; npm run start
```

Without a Gemini key, set `AI_PROVIDER=fake` in `.env`: the offline provider runs the same
pipeline. On the free tier a daily budget (`GEMINI_DAILY_BUDGET`, default 18) keeps usage under
Google's quota; past it, leads get a provisional score and are retried later.

| Service | URL |
|---|---|
| Dashboard | http://localhost:3000 (public form: `/f/harbor-web`) |
| API docs | http://localhost:8000/docs |
| n8n editor | http://localhost:5678 |
| Mailpit inbox | http://localhost:8025 |

## Testing

| Command | What it proves |
|---|---|
| `backend\.venv\Scripts\python -m pytest` | 266 tests: auth, tenant isolation, scoring, grounding, red team, AI faults, "no send unless approved" |
| `.\scripts\journey.ps1` | The 16-step MVP journey, 3 runs, each from a clean database (incl. killing the backend mid-flow) |
| `.\scripts\smoke.ps1` | Form → n8n → score → alert → draft → approve → email, no duplicates on redelivery |
| `.\scripts\failure-injection.ps1` | n8n stopped and SMTP refusing: nothing lost, nothing sent twice |
| `.\scripts\ui-audit.ps1` | Every page and control, no console or server errors |
| `backend\.venv\Scripts\python ..\evals\run_eval.py --provider fake` | Evaluation harness (CI uses the offline provider) |

## Documentation

[Master prompt](docs/MASTER_PROMPT.md) · [Architecture](docs/ARCHITECTURE.md) ·
[Database](docs/DATABASE_SCHEMA.md) · [API](docs/API_DOCUMENTATION.md) ·
[Automation workflows](docs/AUTOMATION_WORKFLOWS.md) · [Security](docs/SECURITY.md) ·
[UI action audit](docs/UI_ACTION_AUDIT.md) · [Performance](docs/PERFORMANCE.md) ·
[Demo script](docs/DEMO_SCRIPT.md) · [Decisions](docs/adr/) · [Backlog](docs/BACKLOG.md) ·
[Development log](docs/DEVELOPMENT_LOG.md)

## License

All rights reserved until the licence is decided (master prompt §16.7).
