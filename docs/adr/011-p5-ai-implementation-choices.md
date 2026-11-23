# ADR 011: Phase 5 AI implementation choices

- Status: Accepted (Phase 5, 2026-11-23)
- Amends: ADR 004 (models), master prompt §8.4 (draft persistence timing), §8.7 (fallbacks)

## Context
Building the AI layer against the Gemini free tier surfaced decisions the master prompt leaves
open, and one place where P5 and P6 overlap (reply drafts).

## Decisions

| Topic | Decision | Why |
|---|---|---|
| Models | `gemini-3.6-flash`, fallback `gemini-3.5-flash`; empty `.env` values mean these defaults | Measured on the dev key: 3.6 answered valid JSON (1.4 to 20 s); `gemini-2.5-flash` returned 404 |
| Structured output | Send the Pydantic model as `response_json_schema` (JSON Schema), not the SDK's typed `response_schema` | The typed form rejects `additionalProperties`, which our strict models emit (HTTP 400) |
| One pipeline | The pure steps (guard, prompt, ground, score) live in `app/ai/pipeline.py`, used by the service and by `evals/run_eval.py` | The evaluation measures the code that runs in production |
| Cache key | `input_hash` plus the provider name | An offline result must never be served as a Gemini result |
| Quota exhaustion | Daily cap per organization (AI settings, never above the server cap); failed analyses retried with backoff (5 min doubling to 6 h, 8 attempts, about 16 h) by a background worker | §8.7 "queue, not drop"; the free tier's daily quota was used up in one working day |
| Drafts in P5 | Generate and check drafts as a **preview** (`POST /leads/{id}/drafts/generate`, `/drafts/check`); saving, approval and sending stay in P6 with `communication_drafts` | The table, approval flow and send path are one P6 unit; a half-built approval path would be a send risk |
| Fallbacks | AI unavailable: analysis gives a provisional score; drafts use a code template; Q&A shows records that mention the question's words. Each is labelled in the UI | A lead, a draft and an answer are always possible, and never presented as AI output |
| Follow-ups | Eligibility in code (open stage, contactable, fewer than 3, 3-day cooldown); the AI only writes the wording. Replies are not tracked until P6 logs communications | §8.5 |
| Sample data | `app.cli sample-data` and a development-only "Load 40 sample leads" button; generated locally, flagged `custom_fields.sample`, scored by the offline provider | Testing any account without real data or quota; removable without touching real leads |

## Consequences
- P6 builds persistence and approval around the existing draft generator and checks.
- Accuracy numbers may be quoted only from committed reports in `evals/reports/`.
