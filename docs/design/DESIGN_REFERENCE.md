# Replyline: design reference

Visual reference for the dashboard, the public form and the phone approval screen. Read it when you reach Phase 4 (design system, layout, Leads, Lead detail), Phase 5 (score breakdown, scoring settings) and Phase 6 (Approvals, Automation Center).

## What this is, and is not

- Eight screens drawn as mockups (list below).
- Live canvas (author's view): https://claude.ai/artifact/PToPGSH5EeXFUFiabjapES
- Static copies in `docs/design/mockups/*.html`. Plain HTML with inline styles; they open in a browser and link to each other. Open them to see the look; do not copy their markup.
- They are mockups, not code. Build the real screens as typed React components in Next.js (master prompt section 10.2), not by pasting this HTML.
- The master prompt wins on structure. The sidebar now shows all 9 items from section 10.3; Follow-ups, AI Assistant, Analytics and Integrations are not drawn yet.
- All people, companies and emails are fictional (example.com). The same data may be reused as demo seed data. Never use real people.

| # | Screen | File |
|---|---|---|
| 1 | Overview | `01-overview.html` |
| 2 | Lead detail with score breakdown | `02-lead-detail.html` |
| 3 | Approvals queue | `03-approvals.html` |
| 4 | Public lead form | `04-public-form.html` |
| 5 | Leads list | `05-leads.html` |
| 6 | Automation Center (n8n workflows) | `06-automation.html` |
| 7 | Settings: scoring | `07-settings-scoring.html` |
| 8 | Approve on phone (390 x 844) | `08-mobile-approval.html` |

## Look and feel

Calm B2B tool. Neutral cool-grey surfaces, one indigo accent, flat cards with a 1px border and no shadow, dense but readable tables. Light theme only for now.

## Tokens

| Token | Value |
|---|---|
| Page ground | `#F6F7FB` |
| Surface (cards, sidebar) | `#FFFFFF` |
| Border / strong border | `#E3E6EF` / `#CDD2E0` |
| Text / secondary / muted | `#1A1D2B` / `#3A4057` / `#5A6075` |
| Accent / accent ink | `#4338CA` / `#3730A3` |
| Accent tints | `#EEF0FF` (nav active), `#E9E8FF` (badge), `#F3F4FF` (selected row) |
| Demo banner | background `#1A1D2B`, text `#FFFFFF` |
| Chart bar / highlight / track | `#7C83E6` / `#4338CA` / `#E9ECF4` |
| Font | Public Sans 400, 500, 600, 700 (load with `next/font`), `font-variant-numeric: tabular-nums` for numbers |
| Type sizes (px) | 26 page title, 16 card title, 14 body, 13 secondary, 12 caption, 32 stat number, 48 score |
| Radius (px) | 8 controls, 12 cards, 999 pills |
| Spacing (px) | 4, 8, 12, 16, 20, 24, 32 |
| Controls | minimum height 44px, 1px `#CDD2E0` border |
| Focus | 2px `#4338CA` outline, 2px offset |
| Layout | sidebar 232px, top bar (search, notifications, user menu), main padding 20px 32px, content max width 1180px |

### Priority badges

Priority is never colour alone: each badge has a three-bar signal icon plus the word.

| Badge | Background | Text | Bar fill | Icon bars filled |
|---|---|---|---|---|
| High (score 80+) | `#FCE7E1` | `#A32A12` | `#D8553A` | 3 of 3 |
| Medium (50 to 79) | `#FDF0C8` | `#7A4A05` | `#B7791F` | 2 of 3 |
| Low (under 50) | `#E8EBF3` | `#444B63` | `#7B8299` | 1 of 3 |

### Status pills (always icon or word, never colour alone)

| Pill | Background | Text |
|---|---|---|
| Awaiting approval | `#E9E8FF` | `#3730A3` |
| New / neutral | `#E8EBF3` | `#444B63` |
| Spam flagged | `#EDEDED` | `#3F3F3F` |
| AI processing / Running | `#E6F0FA` | `#1F4E79` |
| Needs review | `#FFE9D6` | `#8A3B00` |
| Succeeded / checks passed | `#E3F4EA` (panel `#EEF7F1`) | `#1E5E3A` |
| Failed | `#FCE7E1` | `#A32A12` |

All pairs were chosen for at least 4.5:1 contrast. Re-check any new pair.

## Screen notes

1. **Overview.** Four stat cards (new leads, high priority, waiting for approval, median time to first reply with the target from Settings), leads per day, priority mix as **share of total**, an "Automation this week" strip, and a latest-leads table with a "Next step" column. One row shows a lead still "AI processing".
2. **Lead detail.** Header with priority and score, **Stage** and **Assigned to** selects (stage and draft status are separate things). Left: score card with 7 factor bars, original message with evidence highlighted, and "AI reading of this lead" (intent, urgency, buying signal, missing info) labelled as opinion that does not change the score. Right: draft summary with its status, extracted details with their source (form choice or message), timeline with links to each n8n run, emails and follow-up, notes.
3. **Approvals queue.** List sorted by score. Middle: lead context, top score factors, original message. Right: **read-only To** (from the lead record), editable Subject and Message, the **locked opt-out footer** added by code, **automatic check results** (replaces the old manual checklist), "Reject with reason", "Save edits", "Approve and send". Keyboard shortcuts shown.
4. **Public lead form.** Labelled fields marked required or optional, budget in the business's currency (USD), **consent checkbox unticked by default**, "Send request". The honeypot field is not visible and is not drawn.
5. **Leads list.** Search, filters (stage, priority, source, assignee, sort), Import CSV, Export, New lead, bulk-action bar, pagination. Rows show "AI processing", "Needs review: message gives orders to the AI" and "Spam flagged" markers.
6. **Automation Center.** n8n connection status and "Open n8n editor"; 7-day run stats; **the lead journey** as a row of steps (W1, W2, W3 only if High, W4, You approve, W4b) with counts; cards for each live workflow; scheduled workflows with next run times (only safe ones have "Run now…", which asks to confirm); recent runs with request IDs, a failed run that explains what happened, and Retry.
7. **Settings: scoring.** Seven weight sliders that must total 100, priority bands, reply-time target, live preview on a sample lead, and "Save as version N" (old scores keep their version until re-scored).
8. **Approve on phone.** What the Telegram alert link opens: lead summary, top factors, editable draft, checks result, a large "Approve and send".

## Data rules the mockups follow (the real app must too)

- **Scores come from the rules in master prompt section 8.3**, never hand-picked. Amira Hassan's 85 = 20 budget + 17 intent + 15 urgency + 15 service + 9 completeness (6 of 7 fields) + 0 engagement + 9 business fit.
- **Drafts obey the section 8.4 validator:** amounts only from catalog price ranges, no promised meetings or dates, opt-out line appended by code.
- **Form fields count as trusted input.** Service, budget band and timeline chosen on the form are stored as facts with source "form", not as quotes from the message (spec change recorded in MASTER_PROMPT v3).
- **Currency:** each business has one currency (USD for the demo). USDT and USDC count as USD. Other crypto amounts are shown but marked "not compared" and get neutral points.

## Rules for building from this

- Every control either works or is marked "Coming soon" (master prompt 10.1).
- Priority and status always show icon plus text.
- Plain-text rendering for all AI and customer text, never `dangerouslySetInnerHTML`.
- Keep the "Demo data" banner whenever seeded data is present.
- Real `<button>`, `<a>`, `<label>` and `<input>` elements; visible focus; table headers with `scope`.
- Add loading, empty, error and success states that the mockups do not show (section 10.5).
- Do not add features, numbers or copy the backend cannot support.
