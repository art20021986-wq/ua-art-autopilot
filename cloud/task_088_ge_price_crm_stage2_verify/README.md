# Stage 2 GET-only verification

This separate request performs eight fixed GETs: cars_ui.py, db.py, price_parser.py and the historical Stage 1 receipt, each read twice. It never downloads databases or requests process/upload endpoints. No downloaded module is imported or executed.

The immutable repository Stage 1 receipt SHA is checked before any network operation. Source snapshots remain in memory. Only selected helpers that pass the inherited no-secret source policy are exported; other source is represented by hashes and AST structure. The existing local, hash-pinned Stage 2 patcher receives the full original cars_ui text. The candidate is compiled only, with an additional independent AST and explicit-route proof. No complete source or candidate is written to disk or evidence.

`FINISHED` is verification completion only. `candidate_verification` must separately be PASS. A source fingerprint or anchor refusal is recorded with a fixed safe reason while preserving fresh helper evidence. Current schema, running bot imports, price read-back, UI behavior, backup integrity and Stage 2 installation remain unverified.

Run offline checks: `python -m unittest discover -s cloud/task_088_ge_price_crm_stage2_verify -p 'test_*.py' -v`.

Before committing the request, refresh the exact bundled runtime.py and patcher.py copies from cloud/task_088_ge_price_crm_stage2 and refresh all dependency hashes if either original is edited. Launch identity, nonce, marker and claim are assigned by the normal control-plane workflow; this package does not create or bypass them.
