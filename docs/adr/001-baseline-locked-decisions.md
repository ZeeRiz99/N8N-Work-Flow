# ADR 001: Baseline Locked Decisions D1–D24

- Status: Accepted (Phase 1, 2026-11-21)
- Source: `docs/MASTER_PROMPT.md` §4 (v3)

## Context
The master prompt lists 24 Locked Decisions as recommended defaults to confirm or amend in Phase 1. Recording each unchanged default as its own file would repeat the master prompt, so this ADR accepts the set and the following ADRs record every decision that changed or was added after the Phase 1 audit and review.

## Decision
D1–D24 in master prompt v3 §4 are accepted as written. Amendments and additions:

| ADR | Decision | Change |
|---|---|---|
| 002 | D1 dev topology | Low-RAM operating rules, fallback stays |
| 003 | D4 Python version | Python 3.14 instead of 3.11–3.13 |
| 004 | D11 AI providers | Gemini first; Claude and OpenAI behind the same interface later |
| 005 | D15 notifications | Telegram over a system-wide VPN, email fallback, links in text |
| 006 | D17 money | One currency per organization; stablecoin and crypto rules |
| 007 | D22 names | Replyline and naming map (new) |
| 008 | D23 Ponytail | Phase-end review only (new) |
| 009 | D24 design reference | Mockups as the visual source (new) |
| 010 | §8, §9.3 | Review fixes to AI grounding and n8n workflow patterns |

## Consequences
Changing any Locked Decision later needs a new ADR and the developer's approval (contract rule C3).
