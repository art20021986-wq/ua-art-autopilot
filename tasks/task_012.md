# TASK 012 — MAXIMUM SAFE UA ART SECURITY HARDENING

MODE: SECURITY_HARDENING_PREP / DEFAULT_DENY / NO_UNAPPROVED_PRODUCTION_WRITE
MAX_ROUNDS: 5

## Owner directive — highest priority

The owner wants UA ART protected as strongly as practical with maximum automation and minimum owner work.

Permanent roles remain:
- ChatGPT/Codex = strategy, orchestration, task specification, audit.
- Claude via Anthropic API worker = only author of owner-facing technical working files.
- GitHub = durable provenance/control plane.
- PythonAnywhere = execution environment.
- Owner = sole authority for Gate A execution and separate Gate B production change.

The owner has configured the PythonAnywhere API token. A successful `PythonAnywhere Inbox Sync` has been observed after Claude output, so quarantine transport is active. Quarantine upload is NOT execution and NOT production approval.

## Non-negotiable safety boundary

Do as much protection as possible automatically WITHOUT breaking the current site and WITHOUT bypassing owner approval.

This task itself MUST NOT:
- execute anything on PythonAnywhere;
- modify CRM;
- modify production site files;
- reload/restart WSGI/webapp;
- change DNS/domain registrar settings;
- enable HSTS/CSP enforcement blindly;
- rotate/revoke secrets automatically;
- expose any secret/token/password value;
- publish any vehicle/card;
- weaken the owner approval gates.

All PythonAnywhere execution requires Gate A approval bound to exact TASK_ID + manifest SHA + file SHA. Any production mutation requires a separate Gate B approval.

## Current verified control-plane facts

- Repository `art20021986-wq/ua-art-autopilot` is PRIVATE.
- `main` is currently NOT protected by branch protection/ruleset; do not pretend otherwise.
- Claude Autopilot writes Claude outputs to `cloud/`.
- PythonAnywhere Inbox Sync has now completed successfully and transports Claude output to quarantine/inbox.
- TASK 010 designed a two-gate approval architecture; preserve it.

## Security objective

Build a production-grade security package that protects four layers:

1. GitHub/control plane and software supply chain.
2. PythonAnywhere account/server/files/CRM/backups.
3. Public web application `uaart.com.ua` and browser-facing security.
4. Recovery/incident response so the site can be restored after accidental or malicious change.

Use default-deny, least privilege, immutable provenance, SHA-256 verification, atomic writes, backups, rollback, and no secret disclosure.

## PHASE A — GitHub/control-plane hardening package

Produce exact, conservative hardening recommendations/proposals that do NOT break Claude Autopilot or PythonAnywhere Inbox Sync.

Required controls:
- keep repository PRIVATE;
- protect a stable release path/branch from deletion and force-push;
- do not blindly protect `main` in a way that blocks the existing Claude worker before a safe bot-compatible migration exists;
- explicit least-privilege `permissions:` for every workflow;
- pin third-party GitHub Actions to immutable full commit SHAs in proposed hardened workflow versions, with comments recording upstream action/version;
- no secrets on command line or logs;
- no workflow execution of untrusted PR code with repository secrets;
- concurrency lock for deployment/sync paths;
- artifact/source SHA verification;
- preserve Claude-only provenance;
- preserve Gate A/Gate B separation;
- add a repository `SECURITY.md` proposal;
- add a safe `.gitignore`/deny policy proposal for databases, backups, tokens, env files, private keys, credentials and customer exports;
- provide a manual-settings checklist for GitHub features that cannot be safely changed from code (2FA/passkey, collaborator review, ruleset/branch protection, forking policy, Dependabot/security features when plan-supported).

Do NOT assume private-repository Secret Protection/Code Security is available on the owner's current GitHub plan. Mark plan-dependent controls honestly.

## PHASE B — PythonAnywhere read-only security audit runner

Create `cloud/security/uaart_security_audit.py`, Python 3.10 stdlib-only, intended for later Gate A execution.

It must be READ-ONLY with respect to production/CRM and must never print secret values.

It must inspect, where safely discoverable under `/home/Carix`:
- dangerous world/group-writable permissions on source, DB, config and credential-like files;
- symlinks/path escapes in sensitive roots;
- unexpected executable files in web/static/media roots;
- presence of plaintext secret-like patterns WITHOUT reporting the secret value; report only file path, line number if safe, category and non-reversible fingerprint;
- `.env`, private keys, credential exports, DB/backups accidentally located under public web roots;
- `crm.db` permissions and integrity using SQLite read-only URI + `PRAGMA query_only=ON` + `quick_check`;
- production generator/source file SHA-256 baseline;
- protected UA-0001..UA-0009 relevant production files without modifying them;
- existing backup presence/age where discoverable;
- Python source syntax for selected critical files without importing/executing them;
- WSGI/config text only if safely readable, looking for DEBUG-like unsafe configuration without executing it;
- report exact NOT_PROVEN instead of PASS when evidence is unavailable.

Allowed audit writes only:
- `/home/Carix/video/security/uaart_security_audit.txt`
- `/home/Carix/video/security/uaart_security_audit.json`
using atomic writes, non-symlink checks, and exact root containment.

No subprocess, shell, eval, exec, dynamic import, package install, network, reload, chmod, delete, rename or production write.

## PHASE C — public-site external security verifier

Create `cloud/security/uaart_public_security_check.py` that performs READ-ONLY HTTPS requests only to exact hardcoded allowlisted UA ART hostnames.

Check at minimum:
- HTTPS certificate/hostname validation using standard library defaults;
- HTTP -> HTTPS behavior;
- HTTPS reachability;
- security headers: Strict-Transport-Security, Content-Security-Policy or Report-Only, X-Content-Type-Options, Referrer-Policy, frame protection via CSP frame-ancestors and/or X-Frame-Options, Permissions-Policy where appropriate;
- obvious server/version disclosure headers;
- cookie Secure/HttpOnly/SameSite attributes if cookies are observed, without storing cookie values;
- representative public pages return expected safe status codes;
- no empty or obviously broken security-sensitive redirects.

Do NOT enable HSTS automatically. HSTS may only be recommended after HTTPS/certificate/subdomain readiness is proven. Do NOT enforce a CSP automatically without compatibility testing; recommend Report-Only first if needed.

## PHASE D — backup and recovery package

Create `cloud/security/uaart_backup_gate.py`, intended for later Gate A execution only.

Requirements:
- no production mutation;
- create timestamped security backup under dedicated non-public `/home/Carix/security_backups/` only;
- backup only an explicit allowlist of critical source/config/DB files discovered safely;
- never copy secrets into public `/video` or web roots;
- SHA-256 manifest of every backed-up file;
- restrictive permissions for newly created backup files/directories where supported;
- SQLite-consistent backup for `crm.db` using SQLite backup API with read-only source, not a blind live byte copy;
- retention proposal, but DO NOT delete old backups automatically;
- machine-readable receipt and restore instructions;
- restore is a separate Gate B action and is NOT automatically executed here.

## PHASE E — safe production-hardening plan (proposal only)

Define a staged hardening plan; do not hardcode production edits now.

Cover:
- force HTTPS only after valid HTTPS is proven;
- OWASP-aligned security headers, with CSP Report-Only compatibility stage before enforcement;
- no inline-script-breaking CSP without inventory/testing;
- secure cookie attributes where sessions/cookies actually exist;
- CSRF/input/output escaping review where forms exist;
- rate limiting/WAF recommendation at edge layer where appropriate;
- database/public-root separation;
- disable debug/error leakage;
- least-privilege file permissions;
- immutable baseline and rollback;
- visual/site regression tests after every security change;
- explicit check that UA-0009 remains safe and UA-0001..UA-0008 remain unchanged.

Any actual production patch generated later requires Gate B.

## Required deliverables — all Claude-authored under `cloud/`

1. `cloud/security/SECURITY_MASTER_PLAN.md`
2. `cloud/security/GITHUB_HARDENING.md`
3. `cloud/security/SECURITY.md.proposed`
4. `cloud/security/gitignore_security.proposed`
5. `cloud/security/uaart_security_audit.py`
6. `cloud/security/uaart_public_security_check.py`
7. `cloud/security/uaart_backup_gate.py`
8. `cloud/security/PRODUCTION_HARDENING_PLAN.md`
9. `cloud/security/OWNER_3_STEPS.md`
10. `cloud/security/security_release_manifest.example.json`
11. `cloud/cloud_report_012.md`
12. `cloud/owner_reply.md`
13. `cloud/latest_status.md`

## Owner 3-step instruction requirement

`cloud/security/OWNER_3_STEPS.md` must fit on one mobile screen and reduce owner work to exactly three conceptual steps:

1. Security package prepared automatically by Claude and synced to PythonAnywhere quarantine — no execution yet.
2. Owner approves exact Gate A manifest to run read-only audit + backup + external verifier.
3. System returns one security report; any production hardening is shown separately and requires Gate B approval.

Do not ask owner to manually upload individual files.

## Acceptance tests in GitHub worker

- all generated `.py` compile successfully;
- no executable writes outside the stated report/backup roots by static inspection;
- no production mutation logic in audit/public-check package;
- no secret values in reports/examples;
- no arbitrary command/path/URL execution from owner or Claude input;
- external verifier host allowlist is exact and cannot be overridden by CLI/free-form input;
- backup root is outside public web roots;
- `crm.db` source is opened read-only and backup logic is consistent;
- every unknown/unavailable fact becomes NOT_PROVEN, not PASS;
- owner-facing report clearly distinguishes PREPARED / SYNCED / APPROVED / EXECUTED / PRODUCTION_HARDENED.

## Required owner-facing reply in Russian

State briefly:
- what security package Claude created;
- what is already automatically protected at the GitHub/quarantine layer;
- that no production site change was made yet;
- that the next owner action is only the exact Gate A approval after ChatGPT/Codex verifies the package and manifest;
- that Gate B will be requested only if a production hardening patch is later proven necessary and safe.

PRODUCTION_TOUCHED: NO
