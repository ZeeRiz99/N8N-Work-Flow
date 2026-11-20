# ADR 006: One currency per organization; crypto rules

- Status: Accepted (Phase 1, 2026-11-21)
- Amends: D17

## Context
Budget fit (20 of 100 points) compares a lead's stated budget with the matching service's price range, so both must be in the same currency. Target clients are mostly international; some may quote crypto.

## Decision
- `organizations.currency` (ISO code). The demo organization uses USD.
- USDT and USDC are treated as USD at 1:1.
- Other crypto (BTC, ETH and so on) is stored and shown with its unit but marked `not_compared` and gets the neutral budget share with a note.
- A budget in a different fiat currency is also `not_compared`. No live exchange rates in the MVP.
- The public form's budget options use the organization's currency.

## Consequences
No price-feed dependency. A converter can be added later behind the same `not_compared` path.
