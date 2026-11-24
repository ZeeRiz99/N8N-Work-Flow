# Freelance offers (drafts)

Drafts built only from shipped features. **You set the prices and delivery times**; the ranges
below are a starting point from public listings, researched on 2026-11-24. Never promise results
(more sales, conversion, revenue); describe the process and the deliverables.

## Market price research (2026-11-24)

| Source | What it shows |
|---|---|
| Fiverr n8n gigs (individual listings, e.g. [benuame](https://fiverr.com/benuame/automate-your-workflow-with-n8n-and-ai), [eric_hoy](https://fiverr.com/eric_hoy/automate-your-business-workflows-using-ai-n8n-zapier-and-make-com), [excelsisj](https://fiverr.com/excelsisj/install-n8n-on-your-domain-and-build-custom-automation-workflows)) | Basic about $40–150, Standard about $140–250, Premium about $240–450; tiers scale by steps, app count, AI steps, revisions and support days |
| [Fiverr cost guide: AI automation experts](https://www.fiverr.com/resources/guides/costs/ai-automation-experts) | About $75–520 per project on average; hourly $18–150 |
| [Upwork hourly-rate guide](https://www.upwork.com/resources/upwork-hourly-rates) | New freelancers typically $10–25/h |
| [UpHunt analysis of Upwork AI-automation jobs](https://uphunt.io/blog/upwork-ai-consultant-hourly-rate-2026-data) (third party) | Median posted budgets $15–30/h; about 7% reach $100+/h |
| Live Upwork n8n job posts ([example](https://www.upwork.com/jobs/~022065135086388308733)) | Client budgets about $15–47/h |

Caveats: a small sample of individual listings, some on hold; client budgets are not what
freelancers earn. Check current listings in your own category before publishing.

**Suggested starting ranges** (new seller with a strong portfolio piece, no reviews yet):

| Offer | Basic | Standard | Premium |
|---|---|---|---|
| A. Lead capture automation | $80–120 | $180–250 | $350–450 |
| B. AI lead qualification and scoring | $200–300 | $400–600 | $800–1,200 |
| C. Custom lead-management dashboard | quote only (scoped per client; typically several weeks) | | |

Upwork hourly: start around $25–35/h and raise it after the first reviews.

## Offer A: Lead capture automation (n8n)

**Fiverr title:** I will build an n8n lead capture automation with instant email alerts

**Description:** Every form submission becomes a clean, de-duplicated lead with an instant alert
to your team. I build it in n8n: your form or webhook → validation → spam filter → email (or
Telegram) alert → a row in Google Sheets or your CRM. You get the workflow, a short video
walkthrough and a written runbook.

| | Basic | Standard | Premium |
|---|---|---|---|
| Sources | 1 form/webhook | 2 | 3 |
| Destinations | Email alert | Email + Google Sheets | Email + Sheets/CRM + daily summary |
| Duplicate check | — | Exact (email/phone) | Exact + fuzzy name/company |
| Revisions | 1 | 2 | 3 |
| Support after delivery | 7 days | 14 days | 30 days |

Note for you: Replyline proves the capture, validation, duplicate and alert parts. The Google
Sheets/CRM step is a standard n8n node but is **not** in Replyline; build one test workflow with
it before listing this offer.

**Included:** workflow JSON, credentials set up in your n8n, runbook, walkthrough video.
**Not included:** n8n hosting fees, paid app subscriptions, CRM licences, ad campaigns.
**Requirements:** access to your n8n (cloud or self-hosted) or permission to set one up; the
form or webhook; where alerts should go.

## Offer B: AI lead qualification and scoring

**Fiverr title:** I will add AI lead scoring and reply drafts with human approval to your workflow

**Description:** Gemini reads each inquiry and pulls out service, budget, timeline and intent,
with every fact backed by a quote from the message. A transparent rule set scores the lead and
explains why. High-priority leads alert your team, and a reply draft waits for your approval:
nothing is sent automatically.

| | Basic | Standard | Premium |
|---|---|---|---|
| AI extraction + score with explanation | ✓ | ✓ | ✓ |
| Reply drafts with price-list checks | — | ✓ | ✓ |
| Approval step before sending | — | ✓ | ✓ |
| Follow-up scheduling | — | — | ✓ |
| Scoring rules tuned to your services | Defaults | 1 round | 2 rounds |

**Included:** workflows, scoring configuration, prompt and evaluation on 10–20 sample inquiries
you provide (fictional or anonymized), runbook.
**Not included:** AI provider fees (you own the API key), guarantees of accuracy beyond the
evaluation you see.
**Requirements:** a Gemini API key on your account (paid tier for real customer data), your
service list with price ranges, example inquiries.

## Offer C: Custom lead-management dashboard

FastAPI + Next.js + n8n, tailored services, scoring, pipeline stages and roles: Replyline
adapted to the client. Quote after a discovery call using `CLIENT_DELIVERY_KIT.md`.

## FAQ (Fiverr)

- **Will the AI send emails on its own?** No. Every outbound message waits for a person.
- **Do I need n8n?** Yes. n8n Cloud or self-hosted; I can set up self-hosted on your server.
- **Who owns the workflows?** You do, along with the n8n instance and all credentials.
- **Can you use OpenAI or Claude instead of Gemini?** The design supports other providers;
  Gemini is the tested one. Ask before ordering.
- **Is my data used to train AI?** On Gemini's paid tier, Google states it does not; on the free
  tier it may be. Use a paid key for real customer data.

**Buyer requirements questions:** 1) Where do your leads come from and how many per month?
2) Which tools do you use (CRM, Sheets, email)? 3) Where should alerts go? 4) Do you already
have n8n? 5) What should happen to a high-priority lead in the first hour?

**Gallery:** `docs/portfolio/final/` 01, 03, 04, 05, 06 + the demo GIF; the 90-second video.

## Upwork

**Profile overview:** I build lead-management automations with n8n, Python and AI, designed so a
person stays in control. My portfolio project, Replyline, captures inquiries, extracts the facts
with Gemini (each one quoted from the customer's message), scores them with transparent rules
and drafts replies that wait for human approval. It's tested end to end: 361 automated tests, a
failure-injection suite, and a live AI evaluation with its sample size stated. I work in small,
verified steps, document everything, and hand over workflows you own.

**Portfolio item:** "Replyline: AI lead management with human approval": the demo GIF, screenshots
01/03/05/06 and a link to the case study.

**Project Catalog entry:** Offer B (Basic/Standard/Premium as above).

## LinkedIn series (4 posts)

1. **The problem:** "Most small businesses don't lack leads; they lose them in the inbox. I built
   a system that sorts inquiries, explains why one matters, and drafts the reply, without ever
   sending on its own. Here's why I designed it that way…"
2. **Architecture in one picture:** the README diagram. "n8n schedules and connects; the backend
   decides. Here's why I kept business logic out of the workflows."
3. **Keeping AI from making things up:** grounding (every fact needs a quote), deterministic
   scoring, the prompt-injection corpus, human approval. Include the evaluation numbers with
   "14 cases" stated.
4. **The demo:** the 90-second video. "A self-built portfolio project; code and case study in
   the comments."
