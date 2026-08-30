# TASK 094 — UA-WEB-DESIGN-ROLLBACK-035 v1.0

OWNER_DIRECTIVE (binding): УТВЕРЖДАЮ UA-WEB-DESIGN-ROLLBACK-035 v1.0. НЕМЕДЛЕННО В PRODUCTION. ВЕРНУТЬ PREVIOUS APPROVED WEB DESIGN 1:1, СОХРАНИВ АКТУАЛЬНЫЕ ДАННЫЕ 13 / 3 / 1 / 7 / 2. BACKUP → RESTORE → CROSS-CHECK → PUBLIC VERIFY → AUTO-ROLLBACK ПРИ ОШИБКЕ.

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## What this package is

This is the bounded, zero-LLM, owner-authorized production controller PACKAGE for restoring
the previous approved web design while preserving current live business data
(13 / 3 / 1 / 7 / 2) and all CRM/media/database content untouched.

This package was prepared by the Claude/Cloud stage under the AUTOPILOT communication
protocol. **Claude/Cloud has no direct filesystem or shell access to the PythonAnywhere
production account.** Therefore:

- Phase A (forensic audit) scripts are provided but have **not been executed against real
  production data** in this round. No real SHA-256 hashes for `/home/Carix/video/index.html`,
  `/home/Carix/video/katalog.html`, TASK 086 backups, or TASK 093 backups are known to this
  stage beyond the one preimage hash already published in the task
  (`7e621e50282d240ab73ded3903c95490fc8145435061c69e49eca14c021910f4`, noted in the task text
  with 65 hex characters — this must be re-verified byte-for-byte against the actual backup
  file by the forensic audit script before any use, because a malformed/truncated hash string
  must never be trusted blindly).
- `restore_map.json` is delivered as a **template with no fabricated hashes**. Per the
  mandatory fail-closed rule ("Fail closed if the approved preimage cannot be proven. Do not
  invent or reconstruct a design from memory when a verified backup exists."), this stage
  does **not** guess or reconstruct the approved design and does **not** populate placeholder
  hashes.

## Required execution sequence (to be run by the owner-authorized runner, e.g. GitHub Actions
with the `PYTHONANYWHERE_API_TOKEN` secret, or a human operator with production shell access)

1. Run `forensic_audit.py` against production (read-only). It enumerates:
   - `/home/Carix/backups/task_093_home_counters/20260830T010212Z_7e621e5028`
   - all `task_086_*` backup directories
   - current `/home/Carix/video/index.html`, `/home/Carix/video/katalog.html`, and any
     presentation CSS/JS referenced by them
   and writes `audit_report.json` with real SHA-256 hashes and file sizes/timestamps.
2. A human (owner or ChatGPT/Codex auditor) reviews `audit_report.json`, confirms which
   backup is the last verified approved presentation preimage, and fills in
   `restore_map.json` (target path → source backup path → expected source SHA-256 →
   expected restored SHA-256) using **only** hashes taken directly from `audit_report.json`.
   No hash may be typed from memory.
3. Run `restore_controller.py` (or the bash equivalent `production_restore.sh` via a
   PythonAnywhere console) with the completed `restore_map.json`. The controller:
   - refuses to run if any hash in `restore_map.json` does not match `audit_report.json`;
   - takes a fresh emergency backup of every target before writing;
   - acquires `/home/Carix/.ua_art_production_writer.lock`;
   - writes each target atomically (write to temp file in the same directory, verify hash,
     then `os.replace`);
   - never touches CRM, SQLite, or media paths;
   - runs `verification_checks.py` twice (immediate + delayed) against the public site;
   - automatically restores the fresh emergency backup if any invariant fails.
4. Evidence (`evidence.json`, `owner_report.md`) is written to this same directory by the
   controller run, not fabricated here.

## Scope guarantees encoded in the scripts

- No full-server rollback (only the explicit `restore_map.json` target list is touched).
- No CRM write, no SQLite write, no media write/move/rename/delete.
- No deletion of any UA-XXXX record.
- Hard refusal to write if source/target hash verification fails.
- Hard refusal to PASS on exit code alone — PASS requires the public HTTP+content checks.
