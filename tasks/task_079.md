# TASK 079 — Finish TASK 077 ETA/status synchronization release candidate

## Contract
- Contract: `CRM-CONTAINER-STAGE-SYNC-004 v1.0`.
- This is the final safe continuation of TASK 077 and TASK 076.
- Mode: BACKUP -> SANDBOX/CANARY -> Gate A only.
- Production writes, CRM writes, site writes, process reloads, and Gate B execution are forbidden.
- Production touched must remain exactly zero.
- Do not modify or regenerate `cloud/task_078_voice_watchdog/`.
- Do not create another workflow watchdog. The existing workflow name
  `task077-container-stage-sync-gate-a` is already covered by
  `.github/workflows/safe_workflow_watchdog.yml`.

## Proven live defect and exact anchors
The current live source was captured by GET-only evidence at:
- `cloud/task_076_eta_sync/evidence/gate_a_live.json`
- `cloud/task_077_container_stage_sync/evidence/live_audit.json`

Current full-file SHA-256 anchors:
- `db.py`: `b732a5c731d85cb4c9b1cfddb2fc20961b75230d64e29563a5b5ac328d62c086`
- `cars_ui.py`: `50f1cb15b6e1ec3a35878a3021beb362a87f3607ac46abf3eb44566023b14306`
- `konteyner.py`: `2d56a970fb76c782f0d5caebd65b6a7ffd44fd3ad1278a775bf641cffd39080d`
- `stranica.py`: `84a56024e185932c3f2af289db87d1b98558acdf9c4788256dfd36d544ec28b3`
- `publikaciya.py`: `7bb8b0e51b41d94ad305179c35bce20d89dee7f7704c844335a478f87499f0a4`

Proven call path:
- `konteyner.sprosit_dni` stores wait field `eta_manual`.
- `konteyner.prinyat` parses N and writes only `eta_manual`.
- `konteyner._peresobrat` is fire-and-forget `subprocess.Popen`.
- The handler then claims the page is updating without a verified result.
- `cars_ui.apply_value("eta_days")` performs days and ETA as two separate
  transactions, also without verified publication.
- Existing DB state is inconsistent: UA-0009 has days=13/ETA=2026-09-28;
  UA-0010 and UA-0011 have days=NULL/ETA=2026-09-28.
- UA-0009 public description contains a stale independent arrival sentence
  with `9 вересня 2026`.
- Current dynamic public ETA for UA-0009/0010/0011 is already 30 days /
  2026-09-28; the release must preserve that visible result.

## Required architecture
1. Create one shared ETA writer used by both live entry points. It accepts an
   integer car ID, integer N in 0..400, actor, and optional safe status
   normalization.
2. One short SQLite transaction performs only:
   - optional normalization to `sea_loaded` only from the exact Korea/ferry
     statuses approved by TASK 077;
   - `days_to_kyiv=N`;
   - `eta_manual=UTC_today+N`;
   - `updated_at`;
   - audit entries for both logical fields and status when changed.
   Commit before any renderer, filesystem, subprocess, HTTP, or publisher call.
3. After commit use a new connection for exact read-back. Then build a bounded
   staging file set: primary card, diagnostic page or explicit placeholder,
   /video catalog, and /site catalog. Validate identifiers, days, ETA, status,
   links, and file presence. Atomically install and read back.
4. Before DB mutation capture the exact DB row preimage and hashes/bytes of the
   bounded live file set. On any DB read-back, build, install, delayed-overwrite,
   or public verification failure, run a compensating DB transaction and
   restore the exact file preimages. Verify rollback. Never keep a DB
   transaction open during publication.
5. Preserve the exact preimage value of `published` on PASS and rollback.
   Never force `published=1`.
6. `konteyner.prinyat` and `cars_ui.apply_value` must call the same writer.
   Delete fire-and-forget success semantics. Emit exactly one success message
   only after DB read-back and verified publisher PASS; otherwise exactly one
   failure message.
7. `cars_ui.toggle_publish`: on publisher failure restore the preimage
   `published` and emit no success text. “Машина видна клиентам…” is allowed
   only after verified PASS.
8. Status behavior:
   - canonical ferry status is `sea_loaded` / owner label “На пароме”;
   - remove the legacy customer option “В пути”;
   - preserve real protected statuses `ge_waiting`, `ge_to_kyiv`,
     `ua_arrived`, every `sold_*`, and archive/terminal states;
   - no backwards normalization of protected statuses.
9. Stale text sanitation must change only a sentence that simultaneously:
   - is about arrival/delivery/hand-over; and
   - contains an independent calendar date.
   Preserve service, auction, repair, registration, and all unrelated dates.
   For UA-0009 remove only the stale arrival sentence containing
   `9 вересня 2026`, preserving the rest byte-semantically.
10. All source transforms must fail closed on both the full-file SHA above and
    the exact active function source/hash. Reject duplicate definitions or an
    unexpected active wrapper. No generic search-and-replace.
11. Provide a prepared but unexecuted Gate B plan with one exact distinct owner
    token:
    `CRM-CONTAINER-STAGE-SYNC-004-V1.0-PRODUCTION-APPROVED`.
    Merely mentioning the token in documentation is never approval.

## Mandatory sandbox tests
Use only temporary/local copies. Cover:
- N=0,1,30,400 and invalid/negative/401 input;
- idempotence and integer IDs;
- real protected statuses and allowed ferry normalization;
- preimage published=0 and published=1;
- proof DB commit happens before publisher starts;
- injected publisher failure, DB read-back failure, partial file install,
  delayed overwrite, and compensating rollback;
- exact file-byte restoration and DB-row restoration;
- narrow stale-date sanitation, including unrelated service/auction dates;
- UA-0009/0010/0011 -> days=30, ETA=2026-09-28, sea_loaded;
- UA-0012 -> sea_loaded, days=30, ETA=2026-09-28 plus diagnostic placeholder;
- both card roots and both catalogs;
- preservation hashes for photos/videos/VIN/price/description/status outside
  the allowed fields;
- exactly one owner message;
- deterministic function/SHA anchor refusal.

The test/report result may be only:
- `PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL`, or
- a specific fail-closed result.
Never claim PASS from placeholder tests.

## Deliverables
Return complete contents for each exact file:
- `cloud/task_077_container_stage_sync/patcher/eta_release_candidate.py`
- `cloud/task_077_container_stage_sync/patcher/live_patcher.py`
- `cloud/task_077_container_stage_sync/tests/test_eta_release_candidate.py`
- `cloud/task_077_container_stage_sync/sandbox/release_candidate_report.md`
- `cloud/task_077_container_stage_sync/README.md`
- `cloud/task_077_container_stage_sync/evidence/gate_a_findings.md`
- `cloud/task_077_container_stage_sync/gate_b_manual_workflow.md`

Also update the normal status/reply files. Do not touch any production path.
