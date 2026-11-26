# ADR 012: Keep `'unsafe-inline'` for scripts while Cache Components is on

- Status: accepted (2026-11-27)
- Context: backlog #39 asked for a stricter Content Security Policy without `'unsafe-inline'`.

## Context

The frontend uses Next.js 16 with Cache Components (Partial Prerendering): each page has a static
shell prepared at build time, and dynamic parts stream in. Next.js puts small inline scripts in
every page (the React Server Components payload). A CSP without `'unsafe-inline'` must allow
those scripts some other way.

## Options checked

1. **Nonces through `proxy.ts`.** Next.js's own guide (bundled with 16.4,
   `content-security-policy.md`) states that nonces need dynamic rendering and that *Partial
   Prerendering is incompatible with nonce-based CSP*, because the static shell is built before
   any request (and nonce) exists. Taking this route means turning Cache Components off and
   rendering every page on every request: slower pages and more server work, for the whole app.
2. **Hash-based CSP with Subresource Integrity (`experimental.sri`).** Tested on 2026-11-27:
   with `script-src 'self'` and SRI on, the build succeeds, but the browser blocks the inline
   payload scripts (5 CSP violations on `/f/harbor-web`), and without them the page cannot
   hydrate. SRI only covers script *files*; the inline scripts change per
   page and per data, so their hashes cannot be listed ahead of time.

## Decision

Keep `script-src 'self' 'unsafe-inline'` (and `style-src 'self' 'unsafe-inline'`) while Cache
Components is on. The rest of the policy stays strict.

## Why the remaining risk is acceptable

`'unsafe-inline'` matters when an attacker can inject markup. Replyline's mitigations:

- React escapes all rendered text; the app has no `dangerouslySetInnerHTML` and no inline
  scripts of its own (checked with a code search).
- `default-src`, `connect-src`, `img-src`, `font-src`, `form-action` and `base-uri` are `'self'`,
  so injected code could not load scripts from or send data to another origin.
- `object-src 'none'`, `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `nosniff`.
- Session cookies are httpOnly (scripts cannot read them) and state-changing requests need the
  CSRF header and a same-origin `Origin`.
- No third-party scripts.

## Revisit when

Next.js supports nonces or hashes together with Partial Prerendering, or the app turns Cache
Components off for another reason. Then apply option 1 and run `scripts/ui-audit.ps1`, which
fails on any CSP violation in the console.
