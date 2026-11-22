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
