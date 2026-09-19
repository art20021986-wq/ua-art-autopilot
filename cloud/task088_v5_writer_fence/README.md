# TASK088 v5 writer fence — isolated candidate

This package provides the smallest reusable cooperative fence for the actual
filesystem mutation gaps identified in `cars_ui.py` and `stranica.py`.

It is deliberately **not** a production installation or a writer PASS.
Production use remains blocked until the exact private sources are patched and
read back under their pinned before/after SHA-256 values, complete writer drain
is observed, and canonical Gate B/backup/activation succeeds.

Required integration boundaries:

1. Acquire `publication_fence()` inside the synchronous worker before the
   first `os.remove` in `cars_ui._ubrat_fayly_foto`; keep it through the
   associated database update and page rebuild.
2. Acquire the same fence before the database update in bulk photo/video
   deletion callbacks and keep it until cache/media deletion and
   `_peresobrat_stranicy` complete.
3. Require the same fence around the complete legacy
   `stranica.reloadstranica -> main` path, including the fallback write of the
   previous HTML after validation failure.
4. Publication fence must be acquired before any SQLite write transaction.
   The helper never acquires SQLite or the separate spec84 lock.
5. For async handlers, enter the fence in the `to_thread` worker that performs
   the mutation.  Do not hold it in the event-loop thread and reacquire it in a
   worker.

The implementation is same-thread reentrant and exclusive across threads and
processes.  It uses the already established lock path
`/home/Carix/.ua_art_publish_transaction.lock`, rejects alternate production
paths and symlinks, never deletes the lock file, and fails closed on timeout.
