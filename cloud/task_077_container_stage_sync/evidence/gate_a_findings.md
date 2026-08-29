# TASK 079 — Gate A Findings (restated from TASK 076/077 evidence)

MEMORY MARKERS (verbatim):
`CONTEXT_BUNDLE_SHA256=2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c`
`MEMORY_VERSION_READ=4`

This file restates, for traceability inside TASK 079, the live defects that
were already proven by GET-only evidence in:

- `cloud/task_076_eta_sync/evidence/gate_a_live.json`
- `cloud/task_077_container_stage_sync/evidence/live_audit.json`

No new production access was performed to produce this file. This is a
restatement of already-recorded evidence for the purpose of this task's
release candidate design, not a new capture.

## Confirmed defects (as given by the task contract)

1. `konteyner.sprosit_dni` stores the wait field `eta_manual` directly from
   free-text owner input, without a bounded/validated writer.
2. `konteyner.prinyat` parses an integer N and writes only `eta_manual`,
   leaving `days_to_kyiv` unsynchronized in some historical rows.
3. `konteyner._peresobrat` is fire-and-forget (`subprocess.Popen`), so the
   handler claims a successful page rebuild without ever verifying the
   result.
4. `cars_ui.apply_value("eta_days")` performs the days write and the ETA
   write as two separate transactions, and also declares success without
   verifying publication.
5. Existing DB state is inconsistent as a direct result of (2) and (4):
   - UA-0009: `days_to_kyiv=13`, `eta_manual=2026-09-28` (mismatched pair).
   - UA-0010 and UA-0011: `days_to_kyiv=NULL`, `eta_manual=2026-09-28`
     (missing days field entirely).
6. UA-0009's public description contains a stale, independently-dated
   arrival sentence referencing `9 вересня 2026`, which no longer matches
   the current dynamic ETA of `2026-09-28`.
7. The current dynamic public ETA for UA-0009/0010/0011 already renders as
   30 days / `2026-09-28`; this release candidate's design goal is to make
   the underlying DB rows and the stale sentence consistent with that
   already-visible result, not to change what a visiting customer already
   sees.

## Design response implemented in this task

- A single shared writer (`eta_release_candidate.write_eta_sync`) is
  designed to replace both (1)/(2) and (4)'s separate-transaction behavior
  with one short, atomic SQLite transaction that writes `days_to_kyiv`,
  `eta_manual`, and (only when explicitly enabled and only for the exact
  approved ferry statuses) `status`, together with `updated_at` and audit
  rows, then commits before anything else runs.
- `run_eta_sync_release` replaces the fire-and-forget rebuild in (3) and the
  unverified publication in (4) with: independent-connection read-back,
  bounded staged-file build/install, and a real publisher-verification
  step — with full compensating rollback (DB row + exact file bytes) on any
  failure at any stage.
- `sanitize_stale_arrival_sentence` is designed to remove only sentence (6)
  above for UA-0009 — a sentence that is simultaneously about arrival AND
  contains an independent calendar date matching the stale fragment — while
  leaving all other sentences (service, auction, repair, registration dates)
  byte-semantically untouched.
- Applying any of this to the real UA-0009/0010/0011/0012 rows and files is
  explicitly out of scope for this delivery (see `README.md` and
  `sandbox/release_candidate_report.md` for the fail-closed reasoning).

Production touched to produce this file: **NO**.
