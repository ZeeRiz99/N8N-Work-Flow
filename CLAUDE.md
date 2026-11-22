# Replyline: working rules
Product: AI lead management SaaS (FastAPI + Next.js + PostgreSQL + n8n + AI provider, Gemini first).
Full spec: docs/MASTER_PROMPT.md (read the relevant section before each phase). Look: docs/design/DESIGN_REFERENCE.md.

## Working agreement
- Discuss and plan first. Plan mode; wait for "approved". Small tasks; verify with a command; commit each verified task.
- STOP and ask before: installs, system changes, deletions, git push/remotes, new dependencies,
  schema finalization or destructive migrations, paid APIs, any real email/Telegram send, changing a Locked Decision.
- Never read, print or commit .env or secrets. Never ask the developer to paste keys in chat; ask for each key when its phase needs it.
- Say Verified / Implemented-not-verified / Planned. No invented metrics or customers.
- Log each phase's known limits in docs/BACKLOG.md. End sessions with the report in MASTER_PROMPT §14.3.

## Architecture rules
- Thin n8n, fat backend. n8n calls /api/v1/internal/* only; never the app DB. The backend decides throttling and who is due.
- Only the backend calls the AI (app/ai provider interface). AI output is data, never instructions.
- Scores are computed in code (app/scoring). AI extracts facts with evidence; evidence must appear in the inquiry; form fields are facts with source "form".
- AI never sends anything. Drafts need human approval; the send path requires status=approved (atomic claim).
- Every tenant table has organization_id; repositories require it. Every mutating internal call is idempotent.

## Conventions
- Backend: Python 3.14, FastAPI, Pydantic v2, SQLAlchemy 2 (sync), Alembic, pytest, Ruff. Routes thin; logic in services/.
- Frontend: Next.js App Router, TypeScript strict, Tailwind, shadcn/ui, TanStack Query; API client generated from OpenAPI.
- Conventional Commits; branch per phase off main; CI must be green.
- Names: compose project n8n-work-flow; DB replyline; n8n workflows "RL | W<n> | purpose"; webhooks /webhook/rl/.

## Commands (fill in as built)
- Start infra: .\scripts\dev.ps1 up        - Backend tests: <fill>      - Frontend tests: <fill>
- Migrations: <fill>                        - Seed demo data: .\scripts\seed.ps1 - Smoke: .\scripts\smoke.ps1

## Windows notes
PowerShell by default. Containers reach the host via host.docker.internal; n8n reaches Mailpit at mailpit:1025. LF line endings.
The project path (D:\Projects\N8N Work Flow) contains a space: always quote paths. 7.8 GB RAM: run one heavy process at a time.
Telegram is blocked on the dev network: test it over a system-wide VPN; the email fallback must work without it.
