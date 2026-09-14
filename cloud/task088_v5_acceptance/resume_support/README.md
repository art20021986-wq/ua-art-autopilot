# Offline continuation inspection

This additive helper inspects persisted PR114 evidence. It is not an executor,
Gate, acceptance evaluator, automatic production recovery, credential reader or
alternative authority system. It never calls a network service, subprocess or
runtime controller. Only new inspection reports may be written; existing
requests, claims, transactions, receipts, checkpoints and evidence stay intact.

From the repository root:

```sh
python3 -I -B cloud/task088_v5_acceptance/resume_support/checkpoint_inspect.py
python3 -I -B cloud/task088_v5_acceptance/resume_support/checkpoint_inspect.py --save-name continuation
python3 -I -B cloud/task088_v5_acceptance/resume_support/test_checkpoint_inspect.py
```

The first command is read-only. The second creates an immutable report under
`resume_support/checkpoints/`, named with its content SHA256. Each report records
the original checkpoint hash/time, evidence integrity, changed source scope,
original quota observation/time limit, canonical local identities and one next
read/reconciliation step. No original observation timestamp is refreshed. Commit
sanitized reports through the existing repository workflow to make them durable
outside this local checkout. The helper does not commit or claim remote saving.

The write uses file fsync, an exclusive hard link and directory fsync. Readers
see either no final report or a complete report. A crash can leave a `.partial-`
file; it is never considered a completed report. If publication succeeds before
acknowledgement, the same content/name finds the existing report instead of
writing it twice. A new batch creates a separate version and preserves history.
This is for inspection reports only, not atomicity of remote operations.

## What the checks mean

- All `{path, sha256, bytes}` references directly contained in the checkpoint are
  checked against regular local files. These are integrity checks, not source
  authentication, archive extraction or acceptance of nested unindexed evidence.
  If the direct software report is absent in a new checkout, the helper reads
  exactly `gallery_fix_v2/FINAL_CURRENT_CANDIDATE_RESULTS.json` from the existing
  `PR114_GALLERY_V2_SOFTWARE_EVIDENCE_20260914.zip` pinned by checkpoint SHA256.
  It checks the archive and member hashes, rejects duplicate/oversized members,
  and reads in memory without extraction. A present changed file is never
  replaced by old archive evidence. Other missing files require explicit
  restoration/reconciliation; no general archive search is attempted.
- The named `AUDIT_CONTINUATION_NOTICE.json` is read explicitly. Its later audit
  state supersedes the obsolete checkpoint pending-prompt narrative. The helper
  never surfaces old `next_actions` as active instructions, and even the audit
  notice's recorded console state requires an actual current readback.
- The hash-bound software report's complete declared `source_files_sha256` map
  is compared to local source bytes. Changed paths are listed for a selective
  rerun decision. Unchanged historical results are retained; exact private
  capture, environment/dependencies and applicable live bindings still need
  separate checks. No test result is newly asserted or rerun by this helper.
- Quota age comes from the original hash-bound quota report. The existing
  1800-second canonical limit is applied, with expired, future and missing
  observations identified. Updating a summary timestamp cannot freshen evidence.
  All live bindings, Preview/Gate, writers and reader checks remain with their
  existing canonical validators; this helper never makes them current.
- Existing local `TASK088` claims/transactions are read. Request hashes and
  task/run identity are checked; claim receipt hash/identity are checked when
  present, along with the request's receipt path and matching terminal status.
  Terminal transactions also require a matching terminal claim bound to that
  transaction. Any nonterminal/unknown status, identity mismatch or missing receipt
  calls for reconciliation of the SAME operation and actual external result.
  Even a terminal local record only calls for fresh readback, never replay.
  The helper is deliberately conservative: an old superseded failed attempt
  remains visible as unclassified local history. This history is not a list of
  currently active operations and never demands reinstallation of closed Stage
  1/2. The default next step is current Git/server/receipt readback; determine
  which historical attempts have already been superseded using existing records.

Existing production controls remain authoritative: `automation/control_plane.py`
owns canonical atomic claims, receipts and reconciliation;
`automation/transaction_watchdog.py` validates pending production transactions.
`PREPARING`, `OPEN` and `ROLLING_BACK` must be reconciled using those controls.
Missing records are never a grant to execute. This helper does not import these
modules or invoke their mutating code.

## Isolated interruption coverage and limits

Tests create temporary local files only. They cover real process exit before
report publication and after publication before acknowledgement, retained old
batches, changed/missing evidence, timestamp refresh attempts, request/receipt
identity mismatch and a simulated successful operation with a still-RUNNING
claim. The last case requires reconciliation and cannot replay. No production
process is interrupted. These tests accept only this offline helper; universal
process persistence, remote restart behavior and Stage 3/4 remain unaccepted.
