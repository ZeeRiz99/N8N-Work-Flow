# Replyline: AI lead management that never sends without a human

*A self-developed portfolio project. No customers, no revenue; all data is fictional. Every
number below comes from a committed test or evaluation report (see
[PORTFOLIO_CLAIMS.md](PORTFOLIO_CLAIMS.md)).*

## The business problem

Small service businesses (web studios, agencies, clinics, trades) get inquiries from forms,
email and spreadsheets. The good ones get lost among spam, job seekers and price shoppers; replies
go out late or not at all; follow-ups depend on someone remembering. Generic "AI auto-reply"
tools make it worse in a different way: they answer instantly, sometimes with invented prices or
promises nobody approved.

## The solution

Replyline captures every inquiry, reads it with AI, scores it with transparent rules, alerts the
team about the urgent ones, writes a reply draft, and **waits for a person to approve it** before
anything is sent. Afterwards it schedules the follow-up, checks in on quiet leads, and reports on
which sources bring good leads.

## Architecture

```
Form / CSV / manual ─► FastAPI backend ──outbox──► n8n W1 ─► backend: analyze (Gemini + grounding + rules)
                         ▲   decides everything        │      ├─ High? alert the team
                         │                             │      └─ write reply draft ─► Approvals queue
                         └──── internal API ◄──────────┘                                 │ a person approves
                                                         n8n W4b ◄── draft.approved ◄────┘
                                                           └─► claim once ─► SMTP ─► sent + follow-up
```

Next.js dashboard · FastAPI · PostgreSQL · n8n (9 workflows) · Gemini · Docker Compose · Caddy.

## Key decisions and why

1. **Thin n8n, fat backend.** n8n schedules, retries and connects; every business decision
   (score, who to alert, whether a draft may be sent) lives in tested Python. Workflows stay
   simple to read for a client, and the logic has unit tests.
2. **Deterministic scoring.** The AI extracts facts (service, budget, timeline, intent); a
   versioned, configurable 7-factor rule set turns them into a 0–100 score with an explanation per
   factor. The AI never sets the number, so a score can always be explained and reproduced.
3. **Evidence-grounded extraction.** Every fact the AI returns must quote the customer's own
   words. A claim whose quote is not in the message is dropped before scoring.
4. **Human approval for every outbound message.** Drafts pass automatic checks (prices from the
   service list, no promised dates or discounts, link allow-list, opt-out line added by code),
   then wait in an Approvals queue. Sending uses an atomic claim, so an approved draft is sent
   exactly once even if n8n retries.
5. **Transactional outbox and idempotency keys.** Events to n8n are written in the same database
   transaction as the change that caused them, so a crash cannot lose a lead or create a
   duplicate.

## AI safeguards

- Prompt-injection detection: suspicious text is flagged for review and can never raise a score
  (16-technique red-team corpus in the test suite).
- Schema-validated output; invalid output is rejected, not repaired by guesswork.
- When the AI is unavailable or over its daily budget, the lead gets a provisional score from the
  form choices and is retried later. Nothing waits silently.
- AI-written report text is checked number by number against SQL; on any mismatch a plain
  template is used instead.

## Security

Session cookies with CSRF protection, rate-limited login and form, role-based access (owner,
admin, member) and a tenant-isolation matrix test over 32 endpoints. Security headers and CSP,
no secrets in logs or images. In production only the HTTPS proxy is public; n8n is reachable
through an SSH tunnel only.

## Testing and real evaluation numbers

- 361 backend tests, 4 Playwright suites, a 16-step journey run 3 times from a clean database
  (including killing the backend mid-flow), failure injection and a load smoke (130 concurrent
  submissions → exactly 100 leads, no duplicates).
- Live Gemini evaluation on **25 of 40 fictional inquiries** so far: priority band agreement
  88%, band within one step 100%, service and budget extraction 100%, grounding rejected 1 of
  125 claims, no schema-invalid output, mean latency 8.6 s. A small sample: one case moves a
  percentage by 4 points, and the expected labels are one person's judgment.

## Limitations

- Not yet deployed on a public server (the production setup is built and rehearsed locally).
- Telegram alerts are prepared but not shipped; alerts go by email.
- The live AI evaluation covers 25 of 40 cases so far (free-tier daily limit).
- Rate limits are per process, so production runs one backend worker.
- No screen-reader (NVDA) pass yet; axe and keyboard checks only.

## What I would build next

A Google Sheets / Airtable "lite" variant for small budgets, Telegram alerts, a shared rate
limiter for horizontal scaling, nonce-based CSP, and the full live evaluation.

## Stack

FastAPI (Python 3.14, SQLAlchemy 2, Alembic, Pydantic 2) · Next.js 16, React 19, TypeScript,
Tailwind 4 · PostgreSQL 18 · n8n 2 · Gemini · Docker Compose · Caddy · GitHub Actions ·
Playwright · pytest.
