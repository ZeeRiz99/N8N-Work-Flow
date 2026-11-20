# ADR 009: Design mockups as the visual source

- Status: Accepted (Phase 1, 2026-11-21)
- Adds: D24

## Context
The master prompt describes the screens in words only. Eight mockups now exist: Overview, Lead detail, Approvals, Public form, Leads list, Automation Center, Settings: scoring, Approve on phone.

## Decision
`docs/design/DESIGN_REFERENCE.md` and `docs/design/mockups/` are the visual source for Phases 4–6. The master prompt wins on structure. Mockup HTML is never pasted into the app; screens are built as typed React components. Screens not drawn yet (Follow-ups, AI Assistant, Analytics, Integrations) follow the same tokens.

UI decisions fixed by the mockups:
- Approvals: recipient read-only; automatic check results instead of a manual checklist; locked opt-out footer; reject needs a reason.
- Lead detail: pipeline stage and draft status are separate.
- Overview: median time to first reply against the organization's target (`first_reply_at`, `settings.reply_target_minutes`).
- Public form: consent unticked by default.

## Consequences
Clients can see the product's look before any frontend code exists, and the screenshots planned for P12 have a defined target.
