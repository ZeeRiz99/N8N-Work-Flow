# ADR 007: Product name Replyline and the naming map

- Status: Accepted (Phase 1, 2026-11-21)
- Adds: D22

## Context
"AI LeadFlow" was a working title. The developer chose **Replyline** after a web search of candidates (Inquira, LeadLens, Prospecta, Leadwise, Qualivo and Inquiro were already in use). The folder name `N8N Work Flow` stays. Compose project names and GitHub repo names cannot contain spaces.

## Decision

| Where | Name |
|---|---|
| Product (UI, README, portfolio) | Replyline |
| Folder | `D:\Projects\N8N Work Flow` |
| Docker Compose project | `n8n-work-flow` |
| GitHub repository | `N8N-Work-Flow` (private until P12) |
| App database / role | `replyline` / `replyline_app` |
| n8n database / role | `n8n` / `n8n_app` |
| n8n workflow names | `RL \| W1 \| ...`, utilities `RL \| Util \| ...` |
| n8n credentials | `RL Backend Service Key`, `RL Webhook Secret`, `RL Telegram Bot`, `RL SMTP` |
| Webhook base | `/webhook/rl/` |

## Consequences
Before the repository goes public, check the .com domain and the GitHub name. A web search only finds existing products; it is not a trademark search.
