# Replyline

**Turn incoming leads into organized business opportunities.**
Replyline captures every inquiry, understands it with AI, scores it with transparent rules, alerts the team, drafts the reply for human approval, and makes sure nobody is forgotten. n8n runs the automation; the backend makes every decision; a person approves every outbound message.

> **Project status:** self-developed portfolio project, in active development (Phase 2 of 12: foundation). Demo data is synthetic. No customers, revenue or performance claims.

## Stack

FastAPI (Python 3.14) · Next.js 16 + TypeScript + Tailwind 4 + shadcn/ui · PostgreSQL 18 · n8n 2.x · Mailpit (dev email) · Gemini (first AI provider) · Docker Compose · GitHub Actions

## Quick start (Windows, PowerShell)

Prerequisites: Git, Docker Desktop (WSL 2 backend), Python 3.14, Node.js 24. The project path contains a space, so **quote every path**.

```powershell
cd "D:\Projects\N8N Work Flow"

# 1. Secrets: creates .env with random values (never printed). Add your AI key to .env yourself.
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\new-env.ps1

# 2. Infrastructure: PostgreSQL, n8n, Mailpit
.\scripts\dev.ps1 up
.\scripts\dev.ps1 status

# 3. Backend
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

# 4. Frontend (new terminal; on a low-RAM machine stop Docker first if you only need the UI)
cd frontend
npm ci
npm run dev
```

| Service | URL |
|---|---|
| Dashboard | http://localhost:3000 |
| API docs | http://localhost:8000/docs |
| Health / readiness | http://localhost:8000/health · http://localhost:8000/ready |
| n8n editor | http://localhost:5678 |
| Mailpit inbox | http://localhost:8025 |

Optional checks:

```powershell
backend\.venv\Scripts\python scripts\ai_smoke.py     # Gemini key present + one structured call (never prints the key)
backend\.venv\Scripts\pre-commit install            # secret scan, Ruff, line endings on every commit
```

## Documentation

- [Master build prompt](docs/MASTER_PROMPT.md): the full specification
- [Architecture](docs/ARCHITECTURE.md) · [Database schema](docs/DATABASE_SCHEMA.md) · [API](docs/API_DOCUMENTATION.md) · [Security](docs/SECURITY.md)
- [Design reference and mockups](docs/design/DESIGN_REFERENCE.md)
- [Decisions (ADRs)](docs/adr/) · [Project plan](docs/PROJECT_PLAN.md) · [Development log](docs/DEVELOPMENT_LOG.md) · [Backlog](docs/BACKLOG.md)

## License

All rights reserved until the licence is decided (see master prompt §16.7).
