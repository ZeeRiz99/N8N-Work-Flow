# ADR 008: Ponytail as a phase-end review only

- Status: Accepted (Phase 1, 2026-11-21)
- Adds: D23

## Context
Ponytail is a third-party Claude Code plugin that pushes a "write less code" (YAGNI) rule set through Node hooks. This project deliberately carries defensive code: idempotency keys, evidence grounding, tenant isolation tests, retry caps, outbox redispatch.

## Decision
- Not installed as an always-on hook.
- Optional review at the end of a phase, on frontend and glue code only, to catch over-engineering. Findings never remove defensive code or tests.
- Before any install: identify its exact repository, read its hooks, and get the developer's approval (C3).

## Consequences
The built-in `/code-review`, `/security-review` and `/simplify` remain the default phase-end tools.
