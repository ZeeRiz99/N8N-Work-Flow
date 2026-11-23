# Performance sanity check (P7)

**When:** 2026-11-23 · **Where:** the development laptop (7.8 GB RAM, Windows 11, Docker Desktop
running PostgreSQL, n8n and Mailpit) · **Data:** demo organization with 163 leads, analyses,
drafts and timelines. Production build of the frontend (`next start`).

## API (20 calls each, logged-in session)

| Endpoint | p50 | p95 |
|---|---|---|
| Leads list, page 1 | 23 ms | 31 ms |
| Leads search ("bak", trigram) | 23 ms | 32 ms |
| Leads sorted by score | 19 ms | 20 ms |
| Lead detail | 17 ms | 25 ms |
| Lead analysis (facts + factors) | 17 ms | 18 ms |
| Lead timeline | 18 ms | 25 ms |
| Overview, 30 days | 46 ms | 56 ms |
| Trends, 60 days | 14 ms | 29 ms |
| Approvals queue | 29 ms | 29 ms |
| Automation overview (includes a live n8n health check) | 81 ms | 104 ms |

## Pages (phone width, 390 × 844, until network idle)

Overview 0.76 s · Leads 1.04 s · Approvals 0.73 s · AI Assistant 0.72 s · Automation 0.69 s ·
Scoring settings 0.75 s · Public form 0.57 s. No horizontal overflow on any page.

## AI

Gemini analysis is the slow step: 10.2 s mean, 13.7 s p95 on the evaluation sample (1.4 to 20 s
seen in development). It runs in the background through n8n; the dashboard shows "AI processing"
and never waits on it. The n8n analyze timeout is 60 s.

## Verdict

Fine for the MVP. Watch later: the Automation overview's synchronous n8n health check, and the
synchronous Re-analyze button (backlog #30).
