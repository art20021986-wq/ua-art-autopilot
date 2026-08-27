# TASK 014 — CORRECT TASK 013 CANDIDATE AFTER CODEX AUDIT

MODE: CORRECT_RELEASE_CANDIDATE / REAL_SERVER_SANDBOX_PREP / NO_PRODUCTION_WRITE
MAX_ROUNDS: 4

## Verified results from TASK 013

- Claude Autopilot TASK 013 run: SUCCESS.
- Claude-filtered PythonAnywhere Inbox Sync after TASK 013: SUCCESS.
- Candidate is present in the safe inbox; this is transfer only, not execution.
- Independent Codex local audit executed the exact committed `cloud/ua_cards_unified/START_UA_CARDS_UNIFIED.py`:
  - `python3 -m py_compile`: PASS.
  - default dry-run exit: 0.
  - receipt: `DRY_RUN_SANDBOX_OK`.
  - `deterministic_across_10_runs: true`.
  - production_touched: false.

## Why correction is mandatory

The current candidate is safe but does not yet satisfy the owner's real acceptance criteria:

1. `FIXTURE_CARDS` covers only UA-0001, UA-0009, UA-9998 and UA-9999. UA-0002..UA-0008 are not exercised.
2. The dry run writes only diag/track fixture pages. It does not create faithful sandbox copies of the real UA-0001..UA-0009 card pages and does not prove entry-button insertion in real card HTML.
3. `CardFactsReader` accepts synthetic dictionaries only. It does not implement bounded read-only discovery of real CRM evidence on PythonAnywhere.
4. It does not inspect the actual production generator chain read-only, so the root cause and exact canonical patch target remain NOT_PROVEN.
5. Generated pages are bare HTML: no viewport meta, no approved UA ART style reuse, no mobile layout proof, and no verification that floating WhatsApp will not cover the buttons.
6. Video poster is hardcoded to `/static/img/video-poster-fallback.jpg`, but existence/HTTP 200 is not verified. This could recreate the known iPhone/Safari black-screen problem.
7. Photos are accepted as arbitrary strings without bounded local-file validation equivalent to video validation.
8. `release_manifest_candidate.json` contains placeholders and has no trusted deterministic post-commit manifest builder.
9. The current `--apply` path compares the supplied Gate B value to the script's own SHA rather than a canonical release manifest SHA and has no real manifest verification. It correctly hard-stops production, but it is not an executable production gate.
10. A real reachable preview, actual UA-0001..UA-0009 matrix, real 390/430/768/1366 browser evidence, and exact UA-0009 readiness are still absent.

Do not lower progress or erase valid work. Correct the candidate so the next Gate A sandbox execution can collect real evidence safely.

## Owner authorization status

- The owner has already authorized automatic Claude filtering and transfer to the PythonAnywhere safe inbox.
- Do not ask again for safe-inbox transfer; it already succeeded.
- The owner wrote `УТВЕРЖДАЮ ПУБЛИКАЦИЮ`, but it remains publication intent only because it predates final exact manifested bytes and preview.
- No Gate A execution and no Gate B production publication are authorized by this task.
- No manual upload should be requested from the owner.

## Required corrected launcher behavior

Update `cloud/ua_cards_unified/START_UA_CARDS_UNIFIED.py` or create a versioned replacement under the same directory.

Default behavior must remain safe and local-fixture-only.

Add an explicit Gate A server-sandbox mode that can later be executed only through the trusted gate and that:

1. Uses Python 3.10 stdlib only.
2. Reads only under exact bounded roots below `/home/Carix`.
3. Discovers the real CRM database from a small hardcoded candidate list; opens it with SQLite URI `mode=ro`, `PRAGMA query_only=ON`, and runs `quick_check`.
4. Dynamically but safely maps real card/diagnostic/tracking columns using an explicit alias allowlist; never guesses values.
5. Reads UA-0001..UA-0009 only by exact ID; unknown data remains `Уточняется`/NOT_PROVEN.
6. Discovers real card HTML and relevant generator files from a small hardcoded candidate list, read-only; never imports or executes production generators.
7. Takes before/after SHA-256 snapshots of CRM, UA-0001..UA-0008 protected pages, UA-0009 targets, and generator candidates.
8. Creates faithful preview copies under an exact isolated preview root, never overwriting live card paths.
9. For each real card copy, removes known legacy duplicate diagnostic/tracking entries in the COPY only, then inserts exactly one canonical diagnostics button and one canonical tracking button at a structurally validated anchor. If the anchor is ambiguous, mark the card FAIL; do not guess.
10. Creates diag and track companion pages for all UA-0001..UA-0009 in the preview.
11. Reuses verified existing UA ART CSS safely in preview or embeds a bounded reviewed style copied from the real card; includes viewport meta and does not redesign the card.
12. Performs local HTML structure checks for exact button counts, empty/unsafe href/src, path traversal, duplicate IDs, viewport, return links, and required empty-state text.
13. Validates photo and video local files with containment, regular-file, non-symlink, non-zero size, allowed extension, and SHA-256 duplicate checks.
14. Never hardcodes an unverified poster path. Select a verified existing poster/photo inside allowed roots, or create an explicit safe fallback SVG inside the preview root and verify it exists/non-zero before referencing it.
15. Writes only to exact allowlisted Gate A roots:
    - `/home/Carix/video/preview/ua-cards-unified/`
    - `/home/Carix/video/reports/ua_cards_unified/`
    - an internal non-public sandbox/receipt root if required.
16. All writes are atomic, reject symlinks and zero-byte output, and include rollback/cleanup for incomplete preview generation.
17. Runs the full real-data generation/check sequence ten times in a staging workspace and proves canonical hashes are stable before atomically exposing the preview.
18. Does not reload WSGI, modify CRM, edit live UA card pages, edit generator files, or publish UA-0009.
19. Writes real `progress.json`, `latest_status.html`, milestone reports, and a machine receipt only from measured evidence.
20. Stops at `AWAITING_GATE_B` after successful Gate A and reachable preview; does not apply production.

## Exact real-data test matrix

Gate A must cover every UA-0001..UA-0009 row, not merely synthetic fixtures. For each:

- real card source located or NOT_PROVEN;
- preview card generated;
- diagnostics button exactly 1;
- diagnostics page exists;
- correct truthful state;
- tracking button exactly 1;
- tracking page exists;
- correct truthful state;
- no unsafe/empty links;
- no duplicate button variants;
- mobile structure checks;
- media checks;
- before/after protected hashes unchanged.

Keep UA-9998 empty and UA-9999 full as clearly synthetic future-card regression fixtures, but do not use them as substitutes for the nine real-card rows.

## Manifest builder requirement

Create `cloud/ua_cards_unified/build_gate_a_manifest.py`, stdlib-only, default-deny, that runs locally in the safe inbox and:

- accepts no arbitrary paths;
- hashes an exact hardcoded file list under `/home/Carix/autopilot_inbox/cloud/ua_cards_unified/`;
- records actual source commit `4bea3a7b33da29c19e83bdaee70e6d356fea9ff9` as the TASK 013 base provenance and clearly records the later TASK 014 correction commit as pending until known;
- constructs canonical JSON per TASK 010 rules;
- sets target_mode SANDBOX_ONLY;
- sets allowed action to the exact Gate A preview/report roots only;
- requires Gate A true, Gate B false;
- never inserts fake Actions run IDs or commit SHAs;
- writes a deterministic manifest and prints its exact SHA-256;
- refuses if any expected file is missing/symlink/zero-byte/changed unexpectedly.

The final exact approval phrase must only be formed after this builder produces the manifest SHA on PythonAnywhere.

## Documentation corrections

Update:
- `UNIFIED_CARDS_SPEC.md`
- `PRODUCTION_PATCH_PLAN.md`
- `TEST_MATRIX.md`
- `BLOCKED.md`
- `OWNER_NEXT_STEP.md`
- `cloud_report_014.md`
- `cloud/latest_status.md`
- `cloud/owner_reply.md`

Do not create `PROGRESS_100.md`. Keep factual maximum status at 80% / AWAITING_GATE_A until a real Gate A receipt exists.

Owner-facing Russian reply must say:
- TASK 013 files were successfully delivered to the safe inbox automatically;
- independent local syntax and 10-run fixture test passed;
- a corrective Claude round was required because the first candidate did not yet test all real cards or real CRM/generator;
- no production/CRM changes occurred;
- the owner does not need to upload anything;
- the next owner phrase will be requested only after an exact Gate A manifest SHA is measured.

PRODUCTION_TOUCHED: NO
