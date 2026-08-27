# Production Hardening Plan — Proposal Only (TASK 012, Phase E)

No item in this document is applied automatically. Every item below becomes a candidate Gate B patch only after: (1) evidence from `uaart_security_audit.py` and `uaart_public_security_check.py` proves the current state, and (2) a compatibility/regression test plan is defined for that specific change.

## Staged order (each stage gated separately)

### Stage 1 — Evidence gathering (Gate A only, no production change)
- Run `uaart_security_audit.py` on PythonAnywhere (read-only).
- Run `uaart_public_security_check.py` against `uaart.com.ua` (read-only, external).
- Run `uaart_backup_gate.py` to create a fresh, restorable baseline backup before any hardening is even proposed.

### Stage 2 — HTTPS enforcement (Gate B, only after HTTPS proven healthy)
- Confirm valid certificate, correct hostname coverage (including `www` subdomain if used), and that redirect from HTTP already works or can be added without breaking existing bookmarked HTTP links.
- Only then propose a `Strict-Transport-Security` header, starting with a **short max-age** (e.g. a few hours) before any long-lived or `includeSubDomains`/`preload` value, to allow safe rollback if something breaks.

### Stage 3 — Security headers, Report-Only first
- Add `Content-Security-Policy-Report-Only` first, built from an actual inventory of scripts/styles/fonts/images the site loads (must be enumerated from real page source, not guessed).
- Monitor Report-Only violations before ever switching to enforcing `Content-Security-Policy`.
- Add `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Permissions-Policy` with a conservative default-deny feature list — these are low-risk and can move to Gate B relatively early, but still require a visual regression check after deployment.
- Add clickjacking protection via `X-Frame-Options: SAMEORIGIN` and/or CSP `frame-ancestors 'self'`, unless the site intentionally embeds itself in a partner iframe (must be confirmed first).

### Stage 4 — Cookies (only if/where sessions exist)
- If the CRM or public site sets cookies, ensure `Secure`, `HttpOnly`, and an explicit `SameSite` attribute. This is only actionable where cookies are confirmed to exist (see Phase C tool output); do not add cookie logic where no cookies exist.

### Stage 5 — CSRF / input-output review (only where forms exist)
- Any HTML form (contact, lead, admin) should be checked for CSRF token presence and server-side validation, and for output escaping of any user-supplied text rendered back into HTML. This requires manual code review, not automated patching, because incorrect CSRF/escaping changes can break legitimate submissions.

### Stage 6 — Edge rate limiting / WAF (recommendation only)
- Recommend, at the hosting/edge layer (e.g. Cloudflare in front of PythonAnywhere, if the owner chooses to add it later), basic rate limiting on login/admin endpoints and a managed ruleset WAF. This is an infrastructure decision for the owner, not something this repository can configure.

### Stage 7 — Filesystem separation
- Confirm (via audit) that `crm.db`, `.env`, and any credential exports are NOT under any path served by the web server. If the audit finds any such file under a public root, that specific file's location is a same-day Gate B candidate (moving a stray secret file out of a public root is low-risk and high-value), always following the two-gate approval process.

### Stage 8 — Debug/error leakage
- Confirm `DEBUG=False` (or framework equivalent) and that error pages do not leak stack traces to the public internet. Fix only after the audit confirms the current value with evidence, not assumption.

### Stage 9 — Least-privilege file permissions
- Any world-writable file found by the audit on `crm.db`, source, or config files is a high-priority Gate B candidate (permission tightening is low-risk relative to functionality, but must still go through Gate B and a post-change smoke test).

### Stage 10 — Immutable baseline & rollback
- Every Gate B production change must be preceded by a `uaart_backup_gate.py` run and followed by a visual/functional smoke test of the public site and CRM before being considered complete.

## UA-0001..UA-0009 safety check
- Before and after any Gate B change, the SHA-256 of UA-0001 through UA-0008 (previously protected production files) must be re-verified unchanged, and UA-0009 must be re-verified to still render/behave safely. Any unexpected SHA-256 delta on UA-0001..UA-0008 blocks the change and triggers rollback via the Stage 1 backup.

## What this document does NOT do
- It does not contain a single line of applied production configuration.
- It does not enable HSTS or enforce CSP.
- It does not assume any specific current header/cookie/debug state — those are determined only by the audit/verifier tool output.
