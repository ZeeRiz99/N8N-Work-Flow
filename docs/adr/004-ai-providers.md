# ADR 004: AI providers behind one interface

- Status: Accepted (Phase 1, 2026-11-21)
- Amends: D11

## Context
The developer can use Gemini, Claude, OpenAI or others. The master prompt already isolates the model behind an `AIProvider` interface with a `FakeAIProvider` for tests.

## Decision
- Only the backend calls an AI provider. n8n never does.
- Build `GeminiProvider` first (free tier, synthetic data only, per §8.8).
- Add `ClaudeProvider` and `OpenAIProvider` in Phase 5 only when the developer supplies keys. Claude asks for each key at that moment; the developer types it into `.env`. Paid API use is a C3 stop-and-ask item.
- Provider and model names come from env (`AI_PROVIDER`, `<PROVIDER>_MODEL`). Each provider SDK is imported in exactly one file.
- The evaluation harness can run the same dataset through each configured provider; only committed reports may be quoted.

## Consequences
One more provider file and smoke test per provider. A provider comparison becomes a portfolio point, backed by real eval reports.
