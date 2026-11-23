# Evaluation report: gemini (2026-11-23)

**Status:** PARTIAL: 14 of 15 cases scored; stopped at b02: daily Gemini budget reached; resets at midnight Pacific.

- Dataset: `evals/datasets/inquiries.jsonl`, 15 fictional inquiries (stratified sample of 40, every category included); expected values written by hand before any model run.
- Provider: gemini; model(s): gemini-3.6-flash; prompt `analysis-v1`; schema `analysis-schema-v1`.
- Pipeline: the production code (`app/ai/pipeline.py`): guard, prompt, provider, grounding, deterministic scoring with default weights.

## Results

| Measure | Value |
|---|---|
| Service (exact set) | 100% |
| Service (recall) | 100% |
| Budget (amount and currency) | 100% |
| Timeline urgency | 93% |
| Intent | 93% |
| Priority band agreement | 93% |
| Band within one step | 100% |
| Grounding rejection rate (claims without a real quote) | 1.6% (1 of 62) |
| Injection cases flagged for review | 1 of 1 |
| Schema-invalid outputs | 0 |
| Mean latency | 10.22 s |
| p95 latency | 13.69 s |
| Mean tokens in / out | 329 / 252 |

## Band agreement by category

| Category | Cases | Band agreement |
|---|---|---|
| clear_high | 2 | 100% |
| vague | 2 | 100% |
| missing_contact | 2 | 100% |
| budget_format | 1 | 100% |
| ambiguous_timeline | 1 | 0% |
| price_shopper | 1 | 100% |
| job_seeker | 1 | 100% |
| spam | 1 | 100% |
| multilingual | 1 | 100% |
| multi_service | 1 | 100% |
| injection | 1 | 100% |

## Misses (band, service or budget)

- `t01` (ambiguous_timeline): band high (80) vs medium; services ['Website Development'] vs ['Website Development']; budget 2500 USD vs 2500 USD; intent hiring vs hiring

## Limits of this evaluation

- 14 scored cases is a small sample; one case moves a percentage by 7.1 points.
- Expected bands are one person's sales judgment, not ground truth.
