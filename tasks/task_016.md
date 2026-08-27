# TASK 016 — RESUME AND COMPLETE TASK 014 WITH PYTHONANYWHERE GATE A

MODE: CORRECT_RELEASE_CANDIDATE / PYTHONANYWHERE_SANDBOX_GATE_A / NO_PRODUCTION_WRITE
MAX_ROUNDS: 4
PARENT_TASK: task_014
PROJECT_TZ: UA-CARDS-UNIFIED-01

## Owner authorization received

The owner explicitly wrote: `Продолжай исправление TASK 014 с доступом к PythonAnywhere`.

This authorizes:

- Claude filtering and GitHub -> PythonAnywhere safe-inbox transfer;
- execution of the exact bounded Gate A sandbox launcher on PythonAnywhere;
- read-only inspection of the real UA ART CRM, real UA-0001..UA-0009 pages, media and generator candidates;
- writes only to:
  - `/home/Carix/video/preview/ua-cards-unified/`
  - `/home/Carix/video/reports/ua_cards_unified/`
  - an internal non-public Gate A receipt/staging root under `/home/Carix`.

This does NOT authorize:

- production card writes;
- edits to live UA-0001..UA-0009 pages;
- edits to CRM or production generators;
- WSGI reload;
- publication of UA-0009;
- Gate B.

PRODUCTION_TOUCHED must remain NO.

## Prior verified history

1. TASK 013 produced a safe candidate under `cloud/ua_cards_unified/`.
2. TASK 013 was automatically delivered to `/home/Carix/autopilot_inbox/`.
3. Independent syntax and fixture dry-run checks passed, including deterministic fixture output across 10 runs.
4. The first candidate was not sufficient for real acceptance:
   - it exercised only UA-0001, UA-0009 and two synthetic future cards;
   - it did not inspect the real CRM or production generator chain;
   - it did not generate faithful preview copies for all UA-0001..UA-0009;
   - it used an unverified hardcoded poster;
   - it did not provide a real reachable preview or exact Gate A manifest.
5. TASK 014 was created to correct these issues. Claude generation completed, but the GitHub commit step failed with a non-fast-forward push while another task advanced main. No TASK 014 corrected outputs landed.
6. Autopilot safe-push/rebase handling has now been repaired. This task must regenerate the corrected outputs against current main and preserve unrelated Shared Memory/CRM work.

## Required deliverables

Create or fully replace the corrected files under `cloud/ua_cards_unified/`:

1. `START_UA_CARDS_UNIFIED.py`
2. `build_gate_a_manifest.py`
3. `RUN_GATE_A_TASK016.py` — exact no-argument restricted server entrypoint
4. `UNIFIED_CARDS_SPEC.md`
5. `LEGACY_CONFLICT_AUDIT.md`
6. `PRODUCTION_PATCH_PLAN.md`
7. `TEST_MATRIX.md`
8. `OWNER_NEXT_STEP.md`
9. `BLOCKED.md` only if factual Gate A execution remains impossible from this worker
10. `cloud_report_016.md`
11. `cloud/latest_status.md`
12. `cloud/owner_reply.md`

Do not create `PROGRESS_100.md` unless a real PythonAnywhere receipt and reachable preview already exist. GitHub-side generation alone remains at maximum 80%.

## Gate A launcher requirements

All Python must use Python 3.10 stdlib only.

Default execution must be safe and must never write production.

The explicit PythonAnywhere Gate A mode must:

1. Use fixed, hardcoded allowed roots only.
2. Reject symlinks, path traversal, zero-byte files, unexpected file types and arbitrary CLI paths.
3. Discover the real CRM from a small hardcoded candidate list. Open SQLite with URI `mode=ro`, `PRAGMA query_only=ON`, then run `quick_check`.
4. Map fields only from an explicit alias allowlist. Unknown values must remain `Уточняется` or `NOT_PROVEN`.
5. Read exactly UA-0001..UA-0009.
6. Discover real card HTML and relevant generator files from a small hardcoded candidate list, read-only. Never import or execute production generators.
7. Take before/after SHA-256 snapshots of:
   - CRM;
   - protected live UA-0001..UA-0008 files;
   - UA-0009 targets;
   - generator candidates.
8. Generate faithful copies of every real UA-0001..UA-0009 card under the isolated preview root.
9. In each COPY only, remove known legacy duplicate diagnostic/tracking controls, validate one exact structural anchor, then insert:
   - exactly one `Комплексная диагностика` button;
   - exactly one `Отследить контейнер онлайн` button.
   If the anchor is ambiguous, mark that card FAIL and do not guess.
10. Generate diagnostic and tracking companion pages for all nine real cards.
11. Always show truthful empty states when CRM/media/tracking evidence is absent. Do not invent container numbers, links, diagnostic results or media.
12. Reuse verified UA ART styling safely and include viewport metadata. Do not redesign the approved card.
13. Verify WhatsApp/floating controls do not structurally cover the two required buttons.
14. Validate all referenced local photos/videos: containment, regular file, non-symlink, non-zero, allowed extension, SHA-256 duplicate detection.
15. Never use an unverified poster path. Use a verified existing image or generate a local safe fallback SVG inside the preview root.
16. Run HTML checks: exact button count, no empty/unsafe href/src, no traversal, no duplicate IDs, viewport present, return links present, empty-state text present.
17. Run the complete real-data generation/check sequence 10 times in staging and prove canonical hashes are identical before exposing preview.
18. Use atomic writes, fsync and os.replace. Clean incomplete staging output on failure.
19. Write only the approved preview/report/receipt roots.
20. Never reload WSGI, modify CRM, edit live cards/generators, or publish UA-0009.

## Exact test matrix

For every UA-0001..UA-0009 record and preview page report:

- real source located or NOT_PROVEN;
- preview card created;
- diagnostics button count = 1;
- diagnostics page exists;
- diagnostics state truthful;
- tracking button count = 1;
- tracking page exists;
- tracking state truthful;
- no empty/unsafe links;
- no duplicate legacy variants;
- verified poster/fallback;
- mobile structure checks;
- media containment/integrity;
- protected before/after hashes unchanged.

Keep synthetic UA-9998 empty and UA-9999 full only as future-card regression tests. They may not substitute for the nine real rows.

## Manifest and restricted entrypoint

`build_gate_a_manifest.py` must:

- accept no arbitrary paths;
- hash an exact hardcoded file set under
  `/home/Carix/autopilot_inbox/cloud/ua_cards_unified/`;
- write canonical deterministic JSON;
- set `target_mode` to `SANDBOX_ONLY`;
- bind the allowed actions to the exact preview/report/receipt roots;
- record actual source provenance available at runtime;
- require Gate A true and Gate B false;
- print the exact manifest SHA-256;
- refuse missing/symlink/zero-byte/unexpected files.

`RUN_GATE_A_TASK016.py` must:

- accept no arguments;
- verify its own location is under the safe inbox;
- invoke only the exact manifest builder and exact corrected launcher;
- force Gate A sandbox mode;
- reject environment overrides that broaden paths or actions;
- never provide a production/apply option;
- emit a machine-readable receipt;
- be safe for an allowlisted PythonAnywhere API console execution.

## Factual progress reports

During real Gate A, publish atomically:

- `/video/reports/ua_cards_unified/progress.json`
- `/video/reports/ua_cards_unified/latest_status.html`
- immutable 20/40/60/80 milestone evidence;
- 100 only if every required check passes and preview is reachable.

At successful Gate A completion, stop at `AWAITING_GATE_B` and report:

- preview URL;
- CURRENT CARDS SAFE;
- UNEXPECTED PROTECTED CHANGES;
- UA-0009 PUBLICATION READINESS;
- SAFE TO PUBLISH UA-0009;
- PRODUCTION WRITE: NO.

If any check fails, do not claim 100%. Report maximum 80% + BLOCKED with exact cause and safe next action.

## Owner-facing result

Russian reply must state:

- TASK 014 was safely resumed as TASK 016 after the non-fast-forward failure;
- no manual upload is required;
- PythonAnywhere permission covers Gate A only;
- production and CRM remain unchanged;
- the next owner action is requested only after a real preview and manifest-bound Gate B phrase exist.

PRODUCTION_TOUCHED: NO
