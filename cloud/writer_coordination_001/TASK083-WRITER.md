# TASK083 admission to the common publication lock

Prepared 9 September 2026. This is an exact-source patch, not a live installation.

The observed installer source has SHA-256
`13dbcbced164c73bb1767fee6d35ca9597c14b552baaeb31ebbf90cad70b1b46`.
`patch_task083_writer.py:patch(bytes)` refuses every other source, including an
already-patched source. It produces SHA-256
`13b61a13b73f4a029b01fa0f3c071ab8d4790b656d8fa5f37876e92ac5231684`.

The patch wraps the actual `main`, `run_install` and `run_rollback` functions in
common publication-lock admission. Publication admission is acquired first;
main then retains its existing lock order:

1. `.task082_catalog_stage_repair.lock`
2. `.task082_catalog_stage_guard.lock`
3. `.task083_catalog_dedup.lock`

Admission uses the existing `.ua_art_publish_transaction.lock` inode and
nonblocking exclusive flock. Existing legacy lock files are validated and never
created, truncated, replaced or touched. The old main loop that touched these
three files is removed. Busy publication, missing or unsafe lock, changed inode,
durable intent of any state, and an intent-inspection I/O error defer execution.
The intent is `.uaart_writer_coordination/active-intent.json`; an expired,
released, corrupt or symlink intent is still present and denies admission.

Nested calls from main are admitted only on the same thread and PID, with the
recorded resource identities still matching. Application payload errors,
including errno 22, remain their original exceptions. The publication lock is
released on success or exception. The server fence attempts its own existing
locks nonblocking, so its different acquisition order cannot wait in a deadlock
with this installer.

The patch compares the entire old and new AST after removing only its helper
definitions/imports/decorators and the reviewed lock-initialization loop. All
other functional AST, installation content, rollback logic and three-lock order
must match the observed source exactly.

## Verification and limits

11 isolated tests execute the extracted actual entrypoint AST with synthetic
roots, fake payload helpers and real local flocks. They cover blocked direct
install/rollback/main, durable intent and inspection errors, missing/symlink/
hardlink locks, existing lock order, same-thread reentrancy, PID mismatch,
unchanged lock inode/mtime, admission held through payload, and preservation of
payload errno. The full application is not imported and production is not read
or written by these tests. This is local evidence; no PythonAnywhere test or
live installation is claimed by this report.

When admission fails before original main starts, the process fails and the
previous install receipt remains untouched. A previous PASS receipt must never
be reused as proof of the new invocation: the caller must check the current exit
and an operation-bound current receipt. The guard does not fabricate a success
receipt while blocked.

Already-running or queued old installer processes retain their old loaded code.
Installing these bytes cannot prove they have drained. The reviewed quiet-window
and process verification remain necessary during rollout. This patch closes the
normal newly-started TASK083-versus-publication race once actually installed; it
does not alone verify every external writer or close Gate B.
