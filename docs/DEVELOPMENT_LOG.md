# Development log

Newest first. Every new dependency gets a one-line justification here (contract rule C13).

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
