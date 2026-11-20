# ADR 010: Review fixes to AI grounding and n8n workflow patterns

- Status: Accepted (Phase 1, 2026-11-21)
- Amends: master prompt §8.2, §8.4, §9.3, Appendix B, Appendix C

## Context
A top-to-bottom review of master prompt v2 found patterns that would fail or contradict other rules.

## Decisions

| Problem in v2 | Fix in v3 |
|---|---|
| W9 throttles alerts "once per 10 min", but n8n keeps no state without Code nodes | The backend decides: `/internal/notifications/log` returns `should_alert` |
| W5, W8 and W10 use one cron in one n8n timezone; organizations can have different timezones | Hourly triggers; the backend returns only the organizations due in their own local time |
| W4 drafts a reply for every lead, including spam | The backend returns `skipped` for spam and job-seeker intents |
| W3 sends a Telegram inline URL button to `localhost` | Link in the message text |
| Grounding accepts only quotes from the message; the form also collects service, budget and timeline as structured fields | Form fields are trusted facts with `source: "form"`; conflicts with the message are kept and flagged |
| Approval UI had a manual checklist | Validator results shown as automatic checks, rerun on every saved edit; recipient read-only |
| `SMTP_HOST=localhost` but n8n sends email from inside Docker | `SMTP_HOST=mailpit` (compose service name) |
| `.claude/settings.json` had only `Bash(...)` rules; this machine uses the PowerShell tool | Every rule gets a `PowerShell(...)` twin |

## Consequences
Business rules stay in the backend (thin n8n, D10), and the schedules are correct for every organization.
