# Replyline security

Status: final for M2 (Phase 10, 2026-11-24). Rules: `docs/MASTER_PROMPT.md` §11. Replyline
claims no compliance certification (no GDPR, HIPAA or SOC 2 claims); the operator is
responsible for consent and lawful basis when emailing leads.

## Assets

Lead personal data (names, emails, phones, messages) · user accounts and sessions · service API
key, webhook secret, AI keys, Telegram token, SMTP credentials · the n8n encryption key ·
outbound email reputation · tenant separation.

## Entry points

Public lead form and `/public/*` · dashboard (`/auth`, user endpoints) · invitation links ·
`/internal/*` (n8n only, service key) · n8n webhooks (webhook secret) · CSV import · AI provider
responses · SMTP and (later) Telegram delivery.

## Threats, mitigations and evidence

| Threat | Mitigation | Evidence |
|---|---|---|
| One organization reads or changes another's data (IDOR) | `organization_id` on every query; `get_owned` returns 404 for foreign ids | `test_security_matrix.py`: 21 isolation checks over leads, drafts, follow-ups, invitations, duplicates, reports (all 404, nothing changed); org-B lists never show org-A rows |
| A role does more than it may | Role re-checked on every request; admin-only settings, exports, invitations, erasure | `test_security_matrix.py`: 32 endpoints × anonymous / member / admin / owner (401 / 403 / allowed) |
| CSRF | `X-Requested-With` header + origin check on every non-GET; SameSite=Lax cookies | CSRF test in the matrix; P4 auth tests |
| Session theft | httpOnly cookies, 15-minute access token, rotating refresh token with reuse detection | P4 auth tests |
| Spam or abuse on the public form | Honeypot, per-IP rate limit, size caps, org from the public key, idempotency | P3 tests; load smoke (130 concurrent requests, duplicates deduplicated) |
| Prompt injection | Customer text as a tagged data block; no tools or secrets for the model; strict schema; guard flags `needs_review`; AI judgments cannot raise a flagged lead's score | 16-technique red-team corpus in the test suite; guard has no false positives on 38 honest inquiries |
| AI invents facts or numbers | Every fact needs a real quote; budgets re-parsed by code; report prose rejected unless every number is in the SQL metrics | grounding and narrative validator tests |
| Email sent without a human, or twice | Only an `approved` draft can be claimed, atomically; suppression list and contact rules checked at approval and at the claim | behavioural + static test ("no code path sends unless approved"); smoke and failure-injection scripts |
| Contacting someone who opted out | Suppression list, do-not-contact, reply logging; one contact-rules function on every send path | `test_followups.py` (replied / opted-out / do-not-contact / max attempts / cooldown) |
| Secrets leak | `.env` git-ignored and never read by tools; gitleaks in pre-commit and CI; secrets only in env and n8n credentials | CI `secret-scan` runs `gitleaks git` over the **full history** (`fetch-depth: 0`, 69 commits at P10): clean |
| Personal data in logs | Logs carry ids, paths, status and timings only; AI errors log codes, never text | P10 review: 117 KB of backend logs contained no email, phone or message text |
| Clickjacking, MIME sniffing, data leaks via headers | API: CSP `default-src 'none'`, `X-Frame-Options: DENY`, `nosniff`, `no-referrer`, `no-store`, HSTS when served over HTTPS. Frontend: same-origin CSP, frame DENY, nosniff, referrer policy, no `X-Powered-By` | header test in the matrix |
| CSV formula injection | Cells starting with `= + - @` prefixed on export (leads and analytics) | P4 export test |
| Data kept too long | Retention setting erases old archived leads (anonymous audit row); n8n execution data pruned after 14 days | retention test; `infra/compose.dev.yml` |
| Data loss | `scripts/backup.ps1` dumps both databases; `scripts/restore-drill.ps1` restores into a scratch database and compares every table | P10 drill: 27 tables, 0 differences, 14 s |
| n8n editor exposed | Private only (VPN, SSH tunnel or IP allow-list); `/internal/*` blocked at the reverse proxy | P11 (deployment) |

## Dependency audit (2026-11-24)

| Tool | Result | Action |
|---|---|---|
| `pip-audit` (backend) | No known vulnerabilities | None |
| `npm audit --omit=dev` (shipped frontend) | 0 | None |
| `npm audit` (incl. dev tools) | 4 moderate, all in the `shadcn` CLI chain (`ts-morph`, `minimatch`) | Moved `shadcn` to devDependencies (only a stylesheet is imported at build time; the CLI never runs in production). npm's suggested fix is a downgrade to 1.0.0, so it was not applied. **Accepted exception:** dev-only, moderate, re-check when shadcn updates. |

No high or critical findings.

## Accessibility (2026-11-24)

axe (WCAG 2.1 A/AA) over 18 pages, logged in and out (`e2e/a11y.spec.ts` via
`scripts/ui-audit.ps1`): **no critical issues**. One serious finding (inline links told apart by
colour only, Automation page) was fixed by underlining. Earlier manual audit:
`docs/audits/2026-11-23-p5-accessibility.md`. Still to do: a screen-reader pass (NVDA).

## Load (2026-11-24)

`scripts/load-smoke.ps1`: 100 unique leads + 30 exact duplicates sent concurrently (25 threads)
on a clean database: all 130 accepted in 4.4 s, exactly 100 leads, inquiries and intake events,
all 100 processed by n8n W1 within 30 s, no lead with two drafts.

## Documented exceptions

- **Frontend CSP allows `'unsafe-inline'` for scripts and styles.** Next.js inlines its bootstrap
  code; a nonce-based CSP via middleware is the stricter follow-up (backlog). Everything else is
  same-origin only and the app cannot be framed.
- **n8n uses one service key scoped to one organization** (backlog #38). Fine for a single
  business; a multi-tenant deployment needs a platform key or one credential per organization.

## Residual risks

- The n8n encryption key lives in `.env`; back up `.env` securely and separately from the database
  dumps (without it, n8n credentials cannot be decrypted after a restore).
- Free-tier Gemini terms: synthetic data only until a billing-enabled project is used (§8.8).
- Claude Code deny rules block the file tools but are not a perfect barrier against shell
  commands; keep only low-privilege development keys on the development machine.
- Telegram alerts are not verified yet (bot pending); email alerts are used meanwhile.
