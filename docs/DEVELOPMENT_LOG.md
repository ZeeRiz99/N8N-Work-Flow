# Development log

Newest first. Every new dependency gets a one-line justification here (contract rule C13).

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
