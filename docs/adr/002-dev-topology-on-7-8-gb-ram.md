# ADR 002: Dev topology on a 7.8 GB RAM machine

- Status: Accepted (Phase 1, 2026-11-21)
- Amends: D1

## Context
The audit found 7.8 GB RAM with 0.7 GB free during normal use. `.wslconfig` gives WSL 5 GB and keeps its VM alive while idle (`vmIdleTimeout=-1`). Docker Desktop's VM adds about 1 to 1.5 GB on top of PostgreSQL, n8n and Mailpit (~0.8 GB together). Windows, VS Code with Claude, a browser and the Next.js dev server already need most of the memory.

## Options
1. Docker Desktop with WSL capped at about 3 GB (matches production).
2. Docker Engine inside the existing Ubuntu WSL distro (lighter, more Linux setup).
3. No Docker: native PostgreSQL plus `npx n8n` (lightest, does not match production).

## Decision
Option 1, with option 3 as the fallback if Phase 2 shows the machine cannot cope. Operating rules:
- `.wslconfig`: `memory=3GB`; remove the idle-timeout overrides (system change, approved per item in the installation plan).
- One heavy process at a time: no Next.js dev server during backend-only work; Docker stopped during frontend-only work.
- Record real `docker stats` numbers after Phase 2.

## Consequences
Slightly slower switching between backend and frontend work. Production parity is kept for Phase 11.
