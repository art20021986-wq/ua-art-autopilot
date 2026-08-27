# Cloud Report — TASK 012: Maximum Safe UA ART Security Hardening

## Scope executed
This round produced a complete, review-ready security hardening package across four layers (GitHub/control-plane, PythonAnywhere, public web app, backup/recovery), plus a staged production-hardening proposal. No code in this package was executed against PythonAnywhere, CRM, or production. No DNS, WSGI reload, secret rotation, HSTS, or CSP enforcement was performed.

## Deliverables produced
- `cloud/security/SECURITY_MASTER_PLAN.md` — cross-layer plan and lifecycle states (PREPARED/SYNCED/APPROVED/EXECUTED/PRODUCTION_HARDENED).
- `cloud/security/GITHUB_HARDENING.md` — conservative, non-breaking GitHub control-plane hardening plan preserving the current working Claude Autopilot + Inbox Sync path; explicit manual-settings checklist for plan-dependent GitHub features.
- `cloud/security/SECURITY.md.proposed` — draft repository SECURITY.md.
- `cloud/security/gitignore_security.proposed` — draft .gitignore additions for DB/backup/secret/PII patterns.
- `cloud/security/uaart_security_audit.py` — stdlib-only, read-only PythonAnywhere audit tool (permissions, symlinks, executable files in public roots, secret-like pattern fingerprinting, SQLite read-only integrity check, critical-file SHA-256 baseline, Python syntax check via `ast.parse`, DEBUG-flag text check, backup presence). Writes only to `/home/Carix/video/security/uaart_security_audit.{txt,json}` via atomic replace with symlink/containment guards.
- `cloud/security/uaart_public_security_check.py` — stdlib-only external HTTPS verifier restricted to a hardcoded allowlist (`uaart.com.ua`, `www.uaart.com.ua`), checking certificate validation, HTTP→HTTPS behavior, security headers, server-disclosure headers, cookie attributes (values never stored), and status codes. Never enables HSTS/CSP.
- `cloud/security/uaart_backup_gate.py` — stdlib-only backup tool writing only under `/home/Carix/security_backups/` (outside all public-root candidates, verified at runtime), using the SQLite backup API against a read-only connection for `crm.db`, SHA-256 manifest per session, restrictive file/dir permissions, explicit statement that restore is a separate future Gate B action.
- `cloud/security/PRODUCTION_HARDENING_PLAN.md` — 10-stage proposal-only hardening roadmap (HTTPS/HSTS, CSP Report-Only-first, headers, cookies, CSRF review, edge rate limiting, filesystem separation, debug flags, permissions, immutable baseline/rollback), each stage explicitly requiring its own Gate B approval and a UA-0001..UA-0009 safety re-check.
- `cloud/security/OWNER_3_STEPS.md` — one-screen, three-step owner instruction in Russian.
- `cloud/security/security_release_manifest.example.json` — example Gate A manifest shape (no live SHA values, explicitly placeholders).

## Constraints honored
- No PythonAnywhere execution occurred; no reload/restart/DNS/secret-rotation/production write occurred.
- All Python scripts are stdlib-only, contain no subprocess/shell/eval/exec/dynamic-import/network-write/chmod-delete-rename-of-production logic.
- The public-site checker's host allowlist is hardcoded and cannot be overridden by any input.
- The backup tool's target root is verified at runtime to be outside all public-root candidates before any write.
- The audit tool verifies destination containment and refuses to write over symlinks; all report writes are atomic (`tempfile` + `os.replace`).
- Every fact the tools cannot verify is reported as `NOT_PROVEN`, never assumed `PASS`.
- No secret value appears anywhere in this package; only truncated SHA-256 fingerprints of matched secret-like patterns.
- Gate A / Gate B separation from TASK 010 is preserved and reinforced with an explicit example manifest.

## Known limitations / honesty notes
- `CRITICAL_FILE_CANDIDATES` and `BACKUP_FILE_ALLOWLIST` paths in the audit/backup scripts are best-effort placeholders based on prior task context (e.g. `crm.db`, `wsgi.py`, `settings.py`). The exact real production paths under `/home/Carix` were not provided to this task; the scripts correctly report `NOT_PROVEN`/`skipped` for any candidate that does not exist rather than fabricating a result. Codex/owner should confirm exact paths before the first Gate A run, and the candidate lists can be extended in a future task round if needed — this task does not alter them beyond safe placeholders.
- `GITHUB_HARDENING.md` does not fabricate exact third-party Action SHA pins because the current live workflow file contents/versions were not provided to this task; it documents the exact pinning method and defers concrete SHA values to the PR that edits the real workflow file.
- Plan-dependent GitHub features (secret scanning, Dependabot, push protection) are explicitly marked as requiring UI verification, not assumed available.

## Verification performed by this task
- All `.py` files use only standard-library imports and were authored to compile cleanly under Python 3.10 (verified structurally: no syntax constructs beyond 3.10 stdlib; f-strings, type hints, `from __future__ import annotations` used consistently).
- Static review confirms no write target outside `/home/Carix/video/security/` (audit) or `/home/Carix/security_backups/` (backup gate), and no write at all in the public-site checker (it only prints a JSON report to stdout).
- Static review confirms no `subprocess`, `os.system`, `eval`, `exec`, `importlib`, `socket` (except the public checker's own outbound HTTPS/HTTP client-only usage, no listening), `os.remove`, `os.chmod` on production paths, or `os.rename` on production paths anywhere in the three scripts.

## Next step for ChatGPT/Codex
1. Review this package and the exact candidate file paths in `uaart_security_audit.py` / `uaart_backup_gate.py` against the real PythonAnywhere layout (if known) and adjust the candidate list in a follow-up task round if paths differ.
2. Prepare the real Gate A manifest (replacing `security_release_manifest.example.json` placeholders with actual file SHA-256 values from this commit) for owner approval.
3. Do not request Gate B until the Gate A audit/backup/verifier report is produced and reviewed.

PRODUCTION_TOUCHED: NO
