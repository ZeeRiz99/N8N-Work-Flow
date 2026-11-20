# Replyline security (threat-model stub)

Status: Phase 1 stub; completed in Phase 10. Rules: `docs/MASTER_PROMPT.md` §11.

## Assets

Lead personal data (names, emails, phones, messages) · user accounts and sessions · service API keys, webhook secret, AI keys, Telegram token, SMTP credentials · the n8n encryption key · outbound email reputation · tenant separation.

## Entry points

Public lead form and `/public/*` · dashboard (`/auth`, user endpoints) · `/internal/*` (n8n only) · n8n webhooks · CSV import · AI provider responses · Telegram and SMTP delivery.

## Threats and mitigations

| Threat | Mitigation | Phase |
|---|---|---|
| One organization reads another's data (IDOR) | `organization_id` required in every repository method; isolation test matrix; optional RLS | P4, P10 |
| Spam or abuse on the public form | Honeypot, per-IP rate limit, size caps, optional Turnstile, org resolved from the public key | P3 |
| Prompt injection in a customer message | Message passed as delimited data; model gets no tools or secrets; schema validation; `guard.py` flags `needs_review`; red-team corpus | P5 |
| AI invents facts | Evidence quotes must appear in the message; numbers re-parsed by code; form fields marked `source: form` | P5 |
| Email sent without a human | Send path requires `status=approved` with an atomic claim; a test proves no other path sends | P6 |
| Duplicate sends or alerts on retry | Idempotency keys, outbox, atomic claim, unique execution ids | P3, P6 |
| Secrets leak | `.env` git-ignored and never read by Claude; gitleaks pre-commit and CI; secrets only in env and n8n credentials | P2 |
| n8n editor exposed | Private only (VPN / SSH tunnel / IP allow-list); `/internal/*` blocked at the proxy | P11 |
| Session theft | httpOnly cookies, SameSite=Lax, CSRF header + origin check, refresh rotation with reuse detection | P4 |
| CSV formula injection on export | Prefix cells starting with `= + - @` | P4 |
| Losing the n8n encryption key | Persisted and backed up separately from the database | P2, P10 |

## Residual risks (known now)

- Claude Code deny rules block the file tools but are not a perfect barrier against shell commands; keep only low-privilege dev keys on this machine.
- Free-tier Gemini terms: synthetic data only until a billing-enabled project is used (§8.8).
- The operator is responsible for consent and lawful basis for emailing leads; Replyline claims no compliance certification.
