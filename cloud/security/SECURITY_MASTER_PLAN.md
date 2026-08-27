# UA ART — Security Master Plan (TASK 012)

## Purpose
Establish the maximum practical, default-deny security hardening for UA ART across four layers, without touching production, CRM, DNS, or PythonAnywhere execution, and without weakening the Gate A / Gate B owner-approval architecture from TASK 010.

## Layers covered
1. GitHub / control plane & software supply chain — see `GITHUB_HARDENING.md`, `SECURITY.md.proposed`, `gitignore_security.proposed`.
2. PythonAnywhere account/server/files/CRM/backups — see `uaart_security_audit.py`, `uaart_backup_gate.py`.
3. Public web application `uaart.com.ua` — see `uaart_public_security_check.py`.
4. Recovery / incident response — see `uaart_backup_gate.py` and `PRODUCTION_HARDENING_PLAN.md`.

## Lifecycle states (owner-visible, never conflated)
PREPARED -> SYNCED -> APPROVED(Gate A) -> EXECUTED(read-only report) -> [optional] PRODUCTION_HARDENED(Gate B)

TASK 012 delivers only **PREPARED** and **SYNCED**. Nothing beyond that is claimed anywhere in this package.

## Non-negotiable guarantees preserved by this package
- No production or CRM file is modified by any script in this package.
- No PythonAnywhere command execution, process reload, or webapp restart occurs.
- No DNS/domain registrar setting is touched.
- No secret value is ever printed, logged, stored in a report, or committed to git — only path, category, and a one-way SHA-256 fingerprint truncated to 16 hex chars.
- No HSTS or CSP enforcement is auto-enabled anywhere.
- Gate A and Gate B remain fully separate, human-approved, and bound to exact TASK_ID + manifest SHA + file SHA.

## What runs later, only after explicit owner Gate A approval
1. `uaart_security_audit.py` — read-only audit of the PythonAnywhere filesystem, permissions, and CRM DB integrity.
2. `uaart_backup_gate.py` — creates one consistent, non-public, SHA-256-manifested backup.
3. `uaart_public_security_check.py` — external, read-only HTTPS check of the public site; can run from CI or any host with outbound HTTPS, does not require PythonAnywhere execution.

None of these three tools can mutate production, CRM, DNS, or web-server configuration. Any resulting hardening recommendation becomes a separate, explicit Gate B proposal — never auto-applied.

## Honesty rule (binding)
Every claim in every generated report is one of:
- `PASS` — evidence-backed positive finding,
- `FAIL` — evidence-backed negative finding,
- `NOT_PROVEN` — no safe evidence was available; never upgraded to PASS by assumption.

## Files in this package
- `SECURITY_MASTER_PLAN.md` (this file)
- `GITHUB_HARDENING.md`
- `SECURITY.md.proposed`
- `gitignore_security.proposed`
- `uaart_security_audit.py`
- `uaart_public_security_check.py`
- `uaart_backup_gate.py`
- `PRODUCTION_HARDENING_PLAN.md`
- `OWNER_3_STEPS.md`
- `security_release_manifest.example.json`
