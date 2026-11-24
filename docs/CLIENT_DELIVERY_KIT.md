# Client delivery kit

How to turn Replyline into paid work for one client: discovery, configuration without code
changes, deployment patterns and the handover pack.

## 1. Discovery questionnaire

1. Where do leads come from (website form, email, ads, marketplaces, spreadsheets)? How many per
   month?
2. Which tools do you use today (CRM, Google Sheets, email provider, chat)?
3. Which services do you sell, with typical price ranges and currency?
4. Who is your ideal customer (size, industry, budget, location)? Who is not?
5. Who should be alerted about an urgent lead, and how (email, Telegram)? Working hours and time
   zone?
6. Who may approve outbound replies? Any wording you never use (discounts, guarantees)?
7. Tone and signature for replies; languages your customers write in.
8. Data and privacy: where your customers live, consent wording, how long to keep data, who may
   see it.
9. Success for you in the first month (described as a process, e.g. "every lead answered within
   one business day"), not a sales number.

## 2. Per-client configuration (no code changes)

| Setting | Where |
|---|---|
| Service catalog with price ranges | API `POST/PATCH /api/v1/settings/services` (no settings screen yet, backlog #45) |
| Scoring weights and thresholds (7 factors, versioned) | Settings → Lead scoring |
| Pipeline stages | Settings → Pipeline |
| Follow-up rules, notifications, data retention, suppression | Settings → Rules & data |
| AI provider and default reply style (professional, friendly, concise) | Settings → AI |
| Team members and roles | Settings → Team → Invite |
| Alert recipients, SMTP | `.env.production` (`ALERT_EMAIL_TO`, `SMTP_*`) |
| Response-time line, time zone, currency, country | API `PATCH /api/v1/org` |
| Public form | `/f/<org-slug>` (embed or link) |

## 3. Deployment patterns

**(a) Client-owned (recommended).** The client owns the server, the domain, the n8n instance, the
Gemini key and the SMTP account. Deploy with `docs/DEPLOYMENT.md`. This also keeps the setup
within n8n's Sustainable Use License (the client runs its own instance).

**(b) "Lite" for small budgets.** No dashboard: n8n only, with a form or webhook → AI extraction →
rule-based score (in an n8n node) → alert → a row in Google Sheets or Airtable, plus a draft
reply sent to the owner for manual sending. Not part of this repository; scope it separately.

## 4. Handover pack

- **Credentials checklist:** server SSH key, domain registrar, DNS, SMTP account, Gemini key,
  `N8N_ENCRYPTION_KEY` (stored separately), Replyline owner login, n8n owner login. All created on
  the client's accounts; the developer's access removed at the end of support.
- **Runbook:** `docs/DEPLOYMENT.md` sections 6–10 (checks, n8n editor, backups, updates,
  monitoring).
- **Backup and restore:** nightly `scripts/backup-prod.sh`; restore steps in the runbook; one
  restore rehearsed together before sign-off.
- **Key rotation:** change the value in `.env.production`, run `./scripts/deploy.sh` (it
  re-imports n8n credentials). Rotate the Gemini key and SMTP password at least yearly or when
  someone leaves.
- **Support boundaries:** what is covered (bugs in delivered workflows, configuration help)
  and for how long; what is not (new features, third-party outages, content of replies the
  client approves).
- **Acceptance test:** walk `docs/DEMO_SCRIPT.md` on the client's domain with the client:
  form → AI → alert → draft → approve → email received; plus `./scripts/deploy.sh --check`.

## 5. Licensing note

n8n's Sustainable Use License allows building workflows for clients who own their instance. Hosting
n8n so clients build or run workflows on your instance, or selling a hosted product whose value
comes substantially from n8n, needs a commercial licence. Read the current n8n licence FAQ before
offering Replyline as a hosted multi-tenant service. Not legal advice.
