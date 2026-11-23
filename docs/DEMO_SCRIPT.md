# Demo script (under 3 minutes)

For the P7 gate rehearsal and for client calls. Fictional data only.

## Before you start (5 minutes, once)

1. `.\scripts\dev.ps1 up`, backend on :8000, frontend `npm run start` on :3000.
2. `.\scripts\seed.ps1 -Fresh` for fresh demo data.
3. Open four tabs: the public form (`localhost:3000/f/harbor-web`), the dashboard (logged in,
   **Leads** sorted by "Latest activity"), n8n (`localhost:5678`, Executions list), Mailpit
   (`localhost:8025`).
4. If the Gemini daily budget is used up, the demo still works: scores show "provisional".
   For a guaranteed High score, use the message below.

## The script

| Time | Do | Say |
|---|---|---|
| 0:00 | Leads list | "Small businesses lose leads in their inbox. Replyline catches every inquiry, scores it, and drafts the reply, and a person approves everything." |
| 0:15 | Public form: name, email `you+demo@example.com`, *Website Development*, *$1,500 to $5,000*, *Within 1 month*, message: "We run a bakery and need a new website with online ordering. Budget around $2,000, live within a month. Can you send a quote?", tick consent, Send | "A visitor sends a request." |
| 0:30 | Dashboard: the new lead appears, "AI processing" | "It is in the CRM straight away; the AI works in the background." |
| 0:40 | n8n tab: the W1 run | "n8n moves it along. The backend makes every decision." |
| 0:55 | Open the lead: AI analysis, quotes, Why this score | "Every fact quotes the customer's words. The score is computed by rules you control, not by the AI, and it explains itself." |
| 1:20 | Mailpit: the team alert | "High priority, so the team is alerted. Telegram works the same way." |
| 1:35 | Approvals: the draft, checks all green; edit a sentence; Approve and send | "The AI drafted the reply. Automatic checks catch wrong prices, promised dates or bad links. Nothing goes out until someone approves." |
| 2:05 | Mailpit: the reply arrives; Approvals → Sent | "Sent exactly once, logged, and a follow-up is scheduled." |
| 2:20 | Overview | "The dashboard shows volume, priorities and how fast you reply." |
| 2:35 | Automation Center | "Every run is visible. If n8n or email is down, nothing is lost and nothing is sent twice." |
| 2:50 | Close | "That's Replyline." |

## Backup

If something fails live, show the screenshots in `docs/portfolio/` in the same order.
