# Accessibility audit: Phase 5 screens

**Standard:** WCAG 2.1 AA · **Date:** 2026-11-23 · **Method:** code review, computed contrast,
keyboard test in Chromium (Playwright). Not yet tested with a real screen reader (NVDA).

**Screens:** lead detail AI panels (AI analysis, Why this score, Reply draft, Ask), AI Assistant
(Analyze text, Ask about a lead), Settings (Lead scoring, AI).

## Summary
Issues found: 5 · Critical: 0 · Major: 3 · Minor: 2 · **All fixed in this phase.**

| # | Issue | WCAG | Severity | Fix |
|---|---|---|---|---|
| 1 | Form field borders #CDD2E0 were 1.51:1 on white | 1.4.11 Non-text contrast | Major | Field border #8A90A6 (3.17:1) |
| 2 | No explicit keyboard focus indicator (only a 50% transparent default ring) | 2.4.7 Focus visible | Major | Global `:focus-visible` 2px indigo outline (7.9:1) |
| 3 | Errors in the Ask panel and the playground were not announced | 4.1.3 Status messages | Major | `role="alert"` on error text |
| 4 | Assistant tabs: no `aria-controls`, no arrow keys, every tab in the Tab order | 4.1.2 Name, role, value | Minor | WAI-ARIA tabs pattern: roving tabindex, arrows, Home/End, labelled panel |
| 5 | Lead picker said "No leads found" while loading | 3.3.1 / clarity | Minor | "Loading leads…" until the first response |

## Contrast check (all text passes)

| Element | Ratio | Required |
|---|---|---|
| Muted text #5A6075 on white / #F6F7FB | 6.24 / 5.83 | 4.5 |
| Warning #7A4A05 on #FFF8EC | 7.08 | 4.5 |
| Error #A32A12 on #FEF6F3 | 6.80 | 4.5 |
| Success #1E6B3A on #F6F7FB | 6.09 | 4.5 |
| Evidence quote #3A4057 on #FFF6D6 | 9.46 | 4.5 |
| Primary button white on #4338CA | 7.90 | 4.5 |
| Priority badges (High, Medium, Low) | 6.09 to 7.24 | 4.5 |
| Factor bar fill #4338CA vs track | 6.94 | 3.0 |

The factor bar track (#EEF0F6) is faint against the card, but every bar also shows its points as
text ("14/15") and is exposed as `role="meter"` with values, so no information depends on it.

## Kept as is
- Check results use a symbol plus a screen-reader word ("Passed:", "Problem:"), never colour alone.
- Priority is icon plus word, never colour alone.
- Customer text is rendered as plain text.

## Still to do
- Test with NVDA (and 200% zoom) before the P7 demo gate.
