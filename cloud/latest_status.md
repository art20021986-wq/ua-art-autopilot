# Task 123 — site vehicle counters

2026-09-10: INSTALLED on PythonAnywhere at 11:54:10 UTC. Homepage now 18; Kiev 5, Georgia 1, sea 8, Korea 4. Verified Russian and Ukrainian homepage and catalog labels; clicked all four stage filters and confirmed rendered card counts 5/1/8/4.

15 Python tests and Node DOM-fixture checks pass. Server preflight passed existing golden catalog validation. Publisher now updates homepage counts in its existing publication transaction and includes homepage files in rollback snapshots. Task 266084 restarted: new process 12:02:29 UTC, client bot 12:02:30, internal bot 12:02:31; run_all_log confirms both active. All filter rendered 18 cards.

Code and backup hashes, scope and rollback: `tasks/task_123.md`. Supersedes the uninstalled total-only package in `cloud/home_total_auto/`. CRM folders previously deployed under task 122 / PR 87 remain intact. Main EMERGENCY_HALT and old workflow configuration unchanged.
