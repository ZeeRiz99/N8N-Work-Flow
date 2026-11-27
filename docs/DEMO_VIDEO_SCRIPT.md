# Demo video script

Two cuts. Record at 1080p (OBS Studio or Xbox Game Bar: Win + Alt + R), browser zoom 100%,
notifications off (Windows Focus), no `.env`, terminal or password manager on screen. Use the
`harbor-web` demo organization and the public form at `http://localhost:3000/f/harbor-web`.
Keep a recorded backup in case the live run fails. Add captions (YouTube auto-captions, then
correct them). Publish **unlisted** on YouTube or Loom and link it from the README.

**Before recording:** dev stack up (`scripts\dev.ps1 up`, backend, frontend), workflows active,
Mailpit open in a tab (`http://localhost:8025`), n8n W1 open in a tab, the Gemini budget not used
up today (or set `AI_PROVIDER=fake` and say "offline AI" on screen). Prepare the form text:

> Hi! We are a family bakery opening a second shop. We need a new website with online ordering
> for cakes and pickup times. Budget is around $3,500 and we would like it live within a month,
> before the holiday rush. Could you send a quote?

## 90-second cut

| Time | Screen | Voice-over / caption |
|---|---|---|
| 0:00 | Title card: "Replyline" | "Small businesses lose good leads in a messy inbox. Replyline sorts them and drafts the reply, and nothing is sent until you approve it." |
| 0:10 | Public form, fill and submit | "A customer asks for a quote." |
| 0:20 | Leads list: the new lead shows "AI processing" | "It lands in the dashboard straight away." |
| 0:30 | n8n tab: W1 execution, green | "n8n runs the automation; the backend makes every decision." |
| 0:40 | Lead turns High; open it; scroll to "Why this score" | "The AI pulls out the facts, each with a quote from the message. The score comes from fixed rules, so it can always be explained." |
| 0:50 | Mailpit: the team alert email | "High-priority leads alert the team." (Telegram later, once the bot exists) |
| 1:00 | Approvals: open the draft, edit a line, approve | "The reply draft is checked against your price list and waits for a person." |
| 1:15 | Mailpit: the customer's email arrives | "Approved, sent exactly once." |
| 1:25 | Closing card: name, GitHub link, contact | "Replyline: a portfolio project. Code and case study linked below." |

## 3–5 minute cut (adds)

1. **Architecture (30 s):** the diagram from the README; "thin n8n, fat backend"; the outbox.
2. **n8n tour (45 s):** the 9 workflows; W1 nodes; W9 error alert; W9b retry sweeper.
3. **Human approval principle (20 s):** the automatic checks on a draft; reject with a reason.
4. **Failure moment (45 s):** stop the backend (`Ctrl+C`), submit another form, restart the
   backend: the lead is processed, nothing lost, nothing sent twice.
5. **Prompt injection (20 s):** open the "Sam Taylor" lead in the portfolio org: flagged for
   review, score not raised.
6. **Evaluation (20 s):** `evals/reports/2026-11-27-gemini.md`. Say the sample size
   (25 of 40 cases so far) out loud.

## Screenshots to capture by hand

The final set in `docs/portfolio/final/` was captured by `frontend/scripts/final-shots.mjs`.
Two need you:

- **07 n8n W1 canvas with a successful execution:** n8n → workflow "RL | W1 | Lead Intake & Orchestration" →
  Executions → open a green run → screenshot the canvas at 1440×900. Hide the browser bookmarks
  bar; no credential dialogs open.
- **08 Telegram alert on a phone:** only after the bot exists (backlog #17). Mask the chat id.

Check every image for tokens, real emails, URLs with keys and real names before publishing.
