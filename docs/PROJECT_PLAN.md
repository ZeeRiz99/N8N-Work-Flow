# Replyline project plan

Rhythm: 1 phase = 1 branch = 1 pull request = 1 verified increment. Details per phase: `docs/MASTER_PROMPT.md` §13.

## M0 Foundation
- [ ] **P1 Discovery, environment audit, architecture** (branch `phase/01-discovery`)
  - [x] Environment audit run (`scripts/inspect-env.ps1`, 2026-11-20)
  - [x] Master prompt v3 (rename to Replyline, review fixes, decisions)
  - [x] Design mockups (8 screens, `docs/design/`)
  - [x] Installation plan (`docs/INSTALLATION_PLAN.md`)
  - [x] ADRs 001–010
  - [x] Architecture, draft schema, API skeleton, security stub
  - [x] Draft `CLAUDE.md` and `.claude/settings.json` (`docs/drafts/`)
  - [ ] Developer approval: (a) installation plan, (b) architecture and decisions, (c) draft schema
- [ ] **P2 Foundation and repeatable environment**: Docker, compose, backend and frontend skeletons, CI, `.env`
- [ ] **P3 Walking skeleton**: form → backend → n8n → backend → alert → dashboard row (fake AI)

## M1 Working MVP
- [ ] P4 Auth, organizations, CRM core
- [ ] P5 AI intelligence (Gemini first; scoring, grounding, evals)
- [ ] P6 n8n MVP automation, Telegram, approvals
- [ ] P7 MVP gate and demo readiness (`v0.1.0-mvp`)

## M2 Professional SaaS
- [ ] P8 Follow-ups, duplicates, recovery
- [ ] P9 Analytics, reports, settings, team
- [ ] P10 Security, QA and reliability hardening (`v0.2.0`)

## M3 Portfolio release
- [ ] P11 Deployment
- [ ] P12 Portfolio and freelance packaging, including polished screenshots
- [ ] After the last build phase: fix everything in `docs/BACKLOG.md`
