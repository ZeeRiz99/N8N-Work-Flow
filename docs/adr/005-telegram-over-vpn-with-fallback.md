# ADR 005: Telegram over a VPN, with an email fallback

- Status: Accepted (Phase 1, 2026-11-21)
- Amends: D15

## Context
On the development network `api.telegram.org` resolves in DNS (149.154.166.110) but HTTPS connections time out, so Telegram is blocked. The Phase 2 and Phase 3 gates require a Telegram message. A production server abroad would reach Telegram normally. Telegram also rejects `localhost` URLs in inline buttons.

## Decision
- Telegram stays the MVP alert channel, tested through a **system-wide** VPN (a browser-extension VPN does not cover Docker containers).
- The alert step is pluggable: if Telegram is unreachable, the alert goes to email (Mailpit in dev). Gates can pass on the fallback first, then Telegram is verified over the VPN.
- Dashboard links go in the message text, not in inline URL buttons.

## Consequences
The developer connects the VPN before Telegram tests and demo recordings. A notification-channel setting exists from the start, which also makes Slack or Discord easy to add later.
