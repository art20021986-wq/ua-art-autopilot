# Rollback / Gate B plan (NOT executable in this task)

This plan documents what a future, separately owner-approved Gate B would
do. Nothing in this document is executed, scheduled, or triggered by
TASK 042. No script in this package performs any of the steps below.

## Preconditions before any Gate B step may run

1. Real bounded read-only discovery (`discover.py`) has been executed on
   PythonAnywhere against the approved root, and the resulting occurrence
   inventory has been merged into `inventory.json` and reviewed.
2. The real UA-0001..UA-0009 preview matrix has been built from real
   source (not synthetic fixtures) and passed the full acceptance suite.
3. Protected before-hashes for CRM, production generators, live pages,
   media, and UA-0001..UA-0009 have been captured and stored.
4. The owner has given explicit, separate, written approval referencing
   this exact task and exact file list to be changed.

## Gate B steps (future, owner-approved only)

1. Apply the reviewed candidate transform to the exact canonical
   generator/template/renderer files identified by real discovery only
   (never a broad find/replace across the whole tree).
2. Re-render UA-0001..UA-0008 in a staging copy and diff against
   production; confirm only the ferry-wording text changed and all
   internal identifiers, filters, URLs, and tracking/container data are
   byte-identical apart from the approved text.
3. Capture after-hashes and compare against before-hashes; abort on any
   unexpected delta outside the approved wording change.
4. Apply the same reviewed change to the live production paths only after
   the above diff is approved by the owner.
5. Do not reload WSGI, restart bots/services, or change scheduled tasks
   as part of this text-only change unless the owner explicitly approves
   a reload separately.
6. UA-0009 publication is a separate, distinct decision and is never
   bundled into this Gate B; it requires its own explicit owner approval
   and its own full readiness evidence.

## Rollback

If any unexpected change is detected after Gate B:

1. Immediately restore the affected file(s) from the captured before-hash
   backup.
2. Recompute hashes and confirm restoration is byte-identical to the
   pre-Gate-B state.
3. Report the incident with exact file paths, hashes, and timestamps
   before any retry.
