# TASK 080 — prepared manual Gate B plan

Gate B is not authorized or executed in this round.

1. Re-run GET-only Gate A immediately before release. Refuse on any complete
   file or active-block SHA drift.
2. Create timestamped backups of the five audited Python files and a consistent
   SQLite backup. Record hashes and row/card counts.
3. Build the four patched live sources in memory from the freshly verified
   copies. Stage those files plus `price_parser.py` and
   `crm_price_atomic.py` outside the live directory.
4. Compile every staged Python file and run all 58 tests against the staged
   package and a disposable database copy.
5. Atomically install only the six approved files. `db.py`, CRM schema, card
   rows, site files, media, and publication state remain unchanged.
6. Compile/read back installed files and compare their SHA values with the
   candidate evidence. On any mismatch, restore backups before reload.
7. Reload only the CRM Telegram process once. Verify process health and retain
   rollback readiness.
8. Run a no-mutation live canary on an explicitly opened existing card using
   its already stored price. The message must be recognized as the same/filled
   sale price, create no audit/history row, and never create a card. Exercise
   typed and voice-transcript paths.
9. Re-audit card count, every `auto_number`/`price_uah`, audit delta, database
   quick check, unrelated fields, media/publication state, and process health.
10. If any check fails, restore all backed-up source files, reload once, and
    repeat the read-only postcheck. Do not restore or rewrite CRM data unless a
    separately reviewed unexpected data mutation is proven.

Success may be declared only after all postchecks pass and evidence records the
installed hashes. Until then the live CRM must not be described as fixed.
