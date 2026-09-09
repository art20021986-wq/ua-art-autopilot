# Independent review: WSGI lifecycle interpretation

2026-09-09. Scope: `wsgi_lifecycle.py`, its focused tests, `WSGI-LIFECYCLE.md`,
and the private complete 7159-byte server-log capture with SHA-256
`c9e694abf84b6ee242a0b038a2c69fb94b0cccbbecbb148af4d6e8f00eb0d71f`.
No live calls, platform changes, production imports, or production writes.

## Findings

1. **New master reused previous startup configuration.** After a master close,
   `startup`, `mapped_cores`, and `preforking` remained available to a new master
   even if its complete startup stanza was missing. An append-only two-capture
   replay returned `PREEXISTING_WORKERS_TERMINATED_IN_ORDERED_LOG` with the new
   master's `startup_offset` pointing into the previous generation. The author
   added `startup_claimed` and a regression; that fix was independently inspected.

2. **Unknown lifecycle activity after the historical shutdown boundary was
   ignored.** Inserting `Respawned uWSGI worker 4 (new pid: 99)` after the prefix
   `goodbye`, before the first complete startup, did not invalidate the boundary.
   The comparison returned success despite ambiguity about that earlier worker.
   An unparsed lifecycle event after the boundary must reject the observation or
   require a new unambiguous shutdown boundary.

3. **Unknown worker-spawn syntax was ignored in the active interval.** Appending
   `spawned worker 4 (pid: 99, cores: 1)` before the three known burials and
   `goodbye` returned success. The suspicious-line recognizer only matched a
   bare `worker N` when followed by selected death/respawn words. It must also
   reject unparsed worker-slot lifecycle text indicating a spawn.

4. **DISABLE accepted a new startup before its master-spawn line.** This uses
   only original captured bytes: the after-capture ends immediately before the
   second `gracefully (RE)spawned uWSGI master process` line (offset 5926). It
   includes the new startup, mapped capacity, operational mode, and WSGI app
   readiness. DISABLE still returned success because its forbidden-event list
   only included `MASTER_SPAWN` and `WORKER_SPAWN`. `STARTUP` must also prevent a
   DISABLE success, and incomplete pending startup must remain explicit.

## Corrected-source readback

All four findings were corrected by the author. Independent replay of the four
exact counterexamples now rejects them, respectively, with
`NEW_MASTER_WITHOUT_NEW_STARTUP`,
`INCOMPLETE_HISTORY_WITHOUT_SHUTDOWN_BOUNDARY`,
`UNSUPPORTED_LIFECYCLE_LINE`, and `INCOMPLETE_NEW_STARTUP`. Unknown worker-slot
text is detected case-insensitively, the historical boundary is invalidated by
later lifecycle activity, and `DISABLE` explicitly forbids `STARTUP` events.
The new focused regression cases were inspected; the author's complete suite
reports 17 tests. This reviewer reran only the four counterexamples, the original
valid historical shutdown, and the actual current observation.

**PASS for the reviewed data-only interpretation scope.** No unresolved
must-fix findings remain within this bounded review. Final reviewed hashes:

- `wsgi_lifecycle.py`:
  `ec6bb9e993bf81ac29ba323961290fb7eb0622c908ac49cf64077e11a40b9256`
- `tests/test_wsgi_lifecycle.py`:
  `c3963cc0fa465891cc3ce184ea3ba70f48d4ead80f9088efb51dd70c838345a7`

## Correctly retained limitations

The actual current log has live worker slots/PIDs 1/12, 2/13, and 3/18. The
unscoped child exits 356 and 1034 correctly block a current-generation drain
claim, even if hypothetical worker burials are appended. Matching reused PIDs
from different complete generations are distinguished by spawn offsets.

Byte-prefix continuity is not transport authentication, exclusive log-writer
authority, operation binding, process ancestry coverage, or proof of loaded
runtime. The explicit `external_writer_verified: false`,
`installation_authorized: false`, and `loaded_runtime_verified: false` are
necessary. Historical replay does not establish a new platform DISABLE/RELOAD,
external-writer verification, an installation window, or overall Gate B.
