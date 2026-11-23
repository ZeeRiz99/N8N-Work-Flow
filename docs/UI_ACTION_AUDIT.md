# UI action audit (M1)

Every button, link, form and menu item, what it should do, and what verified it (master prompt
§10.6). Run on 2026-11-23 against the dev stack. **All rows pass.**

Verified by: **J** `e2e/mvp-journey.spec.ts` (16-step journey, 3 runs from a clean database via
`scripts/journey.ps1`) · **C** `e2e/crm-journey.spec.ts` · **A** `e2e/ui-audit.spec.ts`
(`scripts/ui-audit.ps1`, fails on any console error or HTTP 5xx) · **T** backend tests ·
**S** `scripts/smoke.ps1` / `failure-injection.ps1`.

All sidebar items are built (Follow-ups in P8, Analytics in P9).

| Screen | Control | Expected result | By | Result |
|---|---|---|---|---|
| Public form | Fields, consent, Send request | Lead stored, thank-you message, event to n8n | J, S | Pass |
| Public form | Resubmit same inquiry | No duplicate lead, no second send | J, S | Pass |
| Public form | Hidden honeypot | Bots rejected silently | T | Pass |
| Login | Email, Password, Log in | Session cookie, lands on Leads | J, A | Pass |
| Register | Business, name, email, password, Create account | New org + owner, lands on Leads | C | Pass |
| Top bar | Log out | Session ended, back to Log in | A | Pass |
| Sidebar | Overview, Leads, Approvals, Duplicates, AI Assistant, Automation, Integrations, Settings | Each page opens with its heading | A | Pass |
| Overview | 7 / 30 / 90 days | Cards and charts reload; pressed state | A | Pass |
| Overview | Show as table / Show chart | Accessible table of the daily series | A | Pass |
| Overview | Bar hover | Tooltip with day, new and high counts | manual (browser) | Pass |
| Overview | Latest leads → lead name, All leads, Automation Center | Navigate | A, J | Pass |
| Leads | Search | Filters by name, company, email (typos ok) | A, C, J | Pass |
| Leads | Stage, Priority, Source, Assigned to, Sort | List filters and sorts | A, C | Pass |
| Leads | New lead dialog (Add lead, Escape) | Creates lead and opens it / closes | C, A | Pass |
| Leads | Import CSV | Opens import page | A, C | Pass |
| Leads | Export (admin) | CSV download, formula-safe | A, T | Pass |
| Leads | Remove sample data / Load 40 sample leads (dev, admin) | Sample leads only, real leads kept | T, manual | Pass |
| Import | CSV file, preview, confirm | Preview with errors, then import | C | Pass |
| Lead detail | Stage, Assigned to | Saved, toast, timeline entry | A, C | Pass |
| Lead detail | Archive / Restore | Toggles, timeline entry | A, C | Pass |
| Lead detail | Erase (admin) | Confirmed erase, anonymous audit row | T | Pass |
| Lead detail | Edit contact details, Save | Saved, rechecks duplicates | C, T | Pass |
| Lead detail | Add note, Save note | Plain-text note, timeline entry | C | Pass |
| Lead detail | Re-analyze | New analysis (cache, fallback when AI unavailable) | T, manual | Pass |
| Lead detail | Ask about this lead (input, example chips) | Answer with cited records; refuses off-topic | A, T | Pass |
| Lead detail | Reply draft: Type, Style, Write a draft | Draft saved to Approvals with checks | A, T | Pass |
| Lead detail | Draft: edit, Save and check again, Copy draft, Review in Approvals | Checks rerun; clipboard; navigate | A, manual | Pass |
| Approvals | Queue item, J / K / arrows | Selects draft, shows context | A, J | Pass |
| Approvals | Subject, Message, Save edits | Saved, checks rerun, marked edited | A, J | Pass |
| Approvals | Approve and send (Ctrl+Enter) | Approved, W4b sends once, Sent tab | J, S | Pass |
| Approvals | Reject with reason, Cancel | Reason required, timeline entry | A, T | Pass |
| Approvals | Waiting / Sent / Failed / Rejected | Filters by status | A, J | Pass |
| Duplicates | Scan, Merge, Dismiss | Human-only merge | A, T | Pass |
| AI Assistant | Analyze text: Use an example, Analyze | Facts and score, nothing saved | A, T | Pass |
| AI Assistant | Tabs (click, arrow keys) | WAI-ARIA tabs | A | Pass |
| AI Assistant | Ask about a lead: search, pick, ask | Lead Q&A | manual, T | Pass |
| Automation | Open n8n editor | Opens n8n in a new tab | A | Pass |
| Automation | Retry failed deliveries (admin) | Requeues gave-up events | T | Pass |
| Integrations | Test connection (n8n, SMTP, Gemini, Telegram) | Live result; Telegram disabled until set up | A, T | Pass |
| Settings | Lead scoring / AI tabs | Switch sections | A | Pass |
| Scoring | Weights, bands, industries | Total must be 100; save disabled otherwise | A, T | Pass |
| Scoring | Save new version, Reset to recommended, Re-score existing leads | Versioned config; rescore without AI | A, T | Pass |
| AI settings | Default style, daily limit, Save | Saved (admin), limit ≤ server cap | A, T | Pass |
| Follow-ups (P8) | Tabs, Prepare now, Skip with reason, Review draft | Rules checked; draft to Approvals or skip with reason | A, T | Pass |
| Lead detail (P8) | Customer replied, Schedule follow-up, Opt out | Logged; follow-ups stopped or scheduled; address suppressed | T, manual | Pass |
| Duplicates (P8) | Keep this one… → merge preview → Confirm / Cancel | Shows result first; merges only on confirm | T, manual | Pass |
| Analytics (P9) | Sources, Funnel, Team, Reports tabs; 30 / 90 days / 1 year; Export CSV | Figures equal raw SQL (reconcile tests) | A, T | Pass |
| Analytics (P9) | Daily summary now, Source report now | Snapshot saved; numbers validated | T, manual | Pass |
| Settings · Team (P9) | Role select, Remove, Invite (email, role), Copy link, Revoke | Audit rows; one open invite per address | T, manual | Pass |
| Invite link (P9) | Name, password, Join the team | Account created (or verified), logged in | T, manual (browser) | Pass |
| Settings · Pipeline (P9) | Rename, ↑ ↓, Remove (custom), Add stage | Saved; built-in stages cannot be removed | A, T | Pass |
| Settings · Rules & data (P9) | Notifications, follow-up limits, retention, Erase now | Saved; only old archived leads erased | A, T | Pass |
| Scoring (P9) | Preview on recent leads | Old vs new band, nothing saved | A, T | Pass |
| Phone width | All screens at 390 px | Layout reflows, no horizontal page scroll | manual (P7 bug bash) | Pass |
