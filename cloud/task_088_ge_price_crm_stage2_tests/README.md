# Local Stage 2 behavior tests

These tests execute synthetic handler fixtures and a retained connection helper
against temporary SQLite databases. They are development tests only, kept out
of the hash-closed production controller package and never uploaded or invoked
by a production workflow. They do not establish live Telegram acceptance.

Run from the repository root:

```bash
PYTHONPATH=cloud/task_088_ge_price_crm_stage2 python3 -B -m unittest discover -s cloud/task_088_ge_price_crm_stage2_tests -p 'test_*.py'
```

The production package retains `test_remote_installer.py`, which exercises real
temporary SQLite backup integrity, immutable claims, changed-source refusal,
candidate hashes and safe rollback without dynamic execution. The ordinary
production execution contract and its code restrictions remain unchanged.
