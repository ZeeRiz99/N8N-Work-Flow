# Installation plan (Phase 2)

Status: **proposed in Phase 1, awaiting approval.** Nothing below is installed yet except the GitHub CLI (approved and installed on 2026-11-21).
Machine: Windows 11 Pro build 26300, Intel i5-8365U (4 cores / 8 threads), **7.8 GB RAM**, C: 30.4 GB free, D: 60.6 GB free. Audit: `scripts/inspect-env.ps1`, run 2026-11-20.

## 1. What is already present

| Tool | Version | Notes |
|---|---|---|
| Git | 2.55.0 | Branch `main`; global `init.defaultBranch=main` set 2026-11-21 |
| GitHub CLI | 2.105.0 | Installed 2026-11-21. Developer runs `gh auth login` before the first push |
| Node.js / npm | 24.18.0 / 11.16.0 | Fine for current Next.js |
| Python | 3.14.6 (`C:\Python314`) | The only full install. A 3.12 Microsoft Store package also exists; not used |
| winget | 1.30 | Install method for everything below |
| VS Code | 1.146 | Claude Code and Python extensions present |
| WSL 2 | Ubuntu distro, stopped | Virtualization works (hypervisor present) |
| Ports 1025, 3000, 5432, 5678, 8000, 8025 | Free | No native PostgreSQL service |

## 2. What to install, in order

| # | Item | Method | Size (approx.) | Risk | How to undo |
|---|---|---|---|---|---|
| 1 | **Docker Desktop** (WSL 2 backend) | `winget install --id Docker.DockerDesktop -e` | ~600 MB download, ~3 GB on C: | Reboot may be needed; uses 1 to 1.5 GB RAM while running | `winget uninstall Docker.DockerDesktop` |
| 2 | Move Docker's disk image to `D:\docker` | Docker Desktop → Settings → Resources → Advanced → Disk image location | Images and volumes then grow on D: | If the setting is missing in the installed version: stop and ask | Point it back to the default folder |
| 3 | **`.wslconfig` change**: `memory=3GB`; remove `vmIdleTimeout=-1` and `instanceIdleTimeout=-1` | Edit `C:\Users\<user>\.wslconfig` after backing it up to `.wslconfig.bak` | None | System setting; WSL restarts (`wsl --shutdown`) | Restore `.wslconfig.bak` |
| 4 | Docker images, **pinned tags chosen in P2** from current release notes: PostgreSQL, n8n (and its task-runner image only if Code nodes are ever needed), Mailpit | `docker compose pull` | ~1 GB total on D: | Tag choice must match n8n 2.x docs | `docker compose down -v` + `docker image rm` |
| 5 | Backend Python packages (FastAPI, SQLAlchemy, psycopg, Alembic, pydantic-settings, pytest, Ruff, argon2-cffi, phonenumbers) | `pip install` **inside `backend\.venv` only** | ~150 MB | A package without a 3.14 wheel → fall back to Python 3.13 (ADR 003) | Delete `.venv` |
| 6 | `pre-commit` (gitleaks, Ruff, Prettier hooks) | `pip install pre-commit` in the venv; hooks fetch their own binaries | ~50 MB | gitleaks hook downloads a binary from GitHub | `pre-commit uninstall`, delete the venv |
| 7 | Frontend packages (Next.js, Tailwind, shadcn/ui, TanStack, Zod, openapi-typescript, Vitest) | `npm install` in `frontend\` | ~400 MB `node_modules` on D: | None beyond disk | Delete `node_modules` |
| 8 | VS Code extensions (optional): Ruff, Docker / Container Tools, ESLint, Prettier, Tailwind CSS IntelliSense | `code --install-extension <id>` | Small | None | Uninstall from the Extensions panel |
| 9 | Playwright browsers (**P4**, not P2) | `npx playwright install chromium` | ~300 MB in the user profile on C: | Uses C: | `npx playwright uninstall` |

Not installed: native PostgreSQL, `psql`, pnpm, uv (none are needed).

## 3. How n8n runs: comparison

| Option | RAM on this machine | Matches production (P11)? | Webhooks to the native backend | Verdict |
|---|---|---|---|---|
| **Docker Compose** (with PostgreSQL and Mailpit) | Containers ~0.8 GB, plus Docker Desktop's VM ~1 to 1.5 GB | Yes: same images and env vars | `http://host.docker.internal:8000` | **Chosen (D1)** |
| `npx n8n` (native Node) + native PostgreSQL | ~0.4 GB for n8n, no VM | No: a different runtime from production | `http://localhost:8000` | **Fallback** if Docker is too heavy |
| n8n Cloud | None locally | No: and it cannot reach `localhost` | Needs a public tunnel | Rejected (D3) |

## 4. Working rule for RAM

One heavy process at a time: no Next.js dev server during backend-only work; Docker stopped (`.\scripts\dev.ps1 down`) during frontend-only work; close browser tabs you do not need. Check `docker stats` after P2 and record real numbers in `docs/DEVELOPMENT_LOG.md`.

## 5. Network notes

- api.telegram.org is **blocked** on this network (DNS resolves, TCP times out). Telegram tests need a **system-wide** VPN (ADR 005). Everything else the project needs was reachable.
- Docker Desktop is free for personal use and small businesses; a freelancer working alone qualifies. Re-check the terms if that changes.

## 6. Developer steps in P2 (not Claude)

1. Approve this plan (or strike items).
2. After Docker Desktop installs: open it once, accept its terms, then set the disk image location (item 2).
3. Create `.env` from `.env.example` and type the secrets yourself. Never paste them in chat.
4. Run `gh auth login` when we are ready to create the private GitHub repo `N8N-Work-Flow`.
