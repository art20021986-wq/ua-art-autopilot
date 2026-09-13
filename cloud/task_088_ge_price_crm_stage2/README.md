# UA-ART-GE-UA-MARKET-PRICE-001 v4.0 — Stage 2 candidate

Status: **NOT INSTALLED / NOT LIVE VERIFIED / NOT READY TO MERGE FOR DEPLOYMENT**.
There is no installer, final execution request, launch marker or Stage 2 success
receipt in this candidate. Stage 1 must not be repeated.

## Verified current sources

GET-only runs [34686469242](https://github.com/art20021986-wq/ua-art-autopilot/actions/runs/34686469242)
and [34686804781](https://github.com/art20021986-wq/ua-art-autopilot/actions/runs/34686804781)
collected current source evidence without remote writes. The current
`/home/Carix/cars_ui.py` SHA-256 equals the Stage 1 after hash:
`76d0a16e7a22940c6699293cf356a6cdba08bb76565bfdcd9b1c66d214b1fee4`.

Both price labels and callbacks already exist in the edit menu source. This
does not prove that the running Telegram process loaded this source.

The current `catch_message` general parser can replace the explicitly selected
`price_georgia` field with `price_uah` when the input contains the word `цена`.
`price_georgia` is absent from the exemptions. Plain-number `auto_catch` also
targets Ukraine, but current `catch_message` normally calls it only without an
explicit wait; a plain-number Georgia miswrite has not been demonstrated live.

## Proposed limited change

The pure `patcher.py` inserts a selected-price branch after existing input/voice
decoding, before general parsing. It forwards the exact selected key, retains
the wait after validation failure, and returns the value read back from DB.
It also prevents auto parsing during an explicit price wait.

Only Georgia gets an early branch in generic `apply_value`; Ukraine's generic
path is preserved so free-form/AI edits do not acquire a new history side effect.
Explicit Ukraine edits are handled by the selected-price branch.

The patcher is pinned to the observed source hash. All other top-level AST
nodes and all original handler statements must remain unchanged. It writes
nothing and does not migrate columns, modify menu layout or touch the website.

`runtime.py` derives from the pre-existing TASK088 candidate helpers. It uses
fixed per-field SQL, verifies all car rows before commit, and reads both prices
through a fresh connection afterwards. A closed-connection cleanup bug was
fixed so failed read-back cannot report success or raise a misleading rollback
error on an already closed connection.

## Validation and remaining gates

Six in-memory transformation tests and eleven SQLite fixture tests cover field
independence, NULL preservation, invalid values, missing rows, cross-write
triggers in both directions, other-car/audit-trigger rollback and read-back
failure, including parser failure before DB access. These are local fixture
results, not Stage 2 acceptance.

Before an executable production package can be approved by the existing gates:

1. Check actual `remember_price`, `db.log_action`, audit schema, `price_parser`
   (including accepted input formats/currencies) and the custom `Soedinenie`
   connection. The candidate combines history/audit with the price
   transaction; complete parity with those live helpers is not yet proven.
2. Apply this transform to the complete current source in a shadow check and
   verify its compiled candidate and actual handler routing. Redacted analysis
   syntax must never be used as replacement source.
3. Obtain a real current PythonAnywhere capacity measurement, less than 30
   minutes old. Do not reuse runner capacity, historical numbers or extend the
   existing Stage 1 storage exception.
4. Prepare dedicated Stage 2 production controller, online SQLite backup,
   rollback controller, manifest and Gate A/B with actual proof. Confirm live
   schema and exact CRM process identity before any business mutation.
5. Perform every v4.0 Telegram/DB/cross-write/rollback acceptance check. If any
   is unverified, do not create a Stage 2 FINISHED/PASS receipt.

The final identity must be `TASK088-GE-PRICE-CRM-STAGE2`, with request
`tasks/requests/TASK088-GE-PRICE-CRM-STAGE2.json` and receipt
`state/receipts/TASK088-GE-PRICE-CRM-STAGE2.json`. Its fresh nonce, claim and
ledger belong only to that final launch. A receipt is an output after success,
not a file to pre-create. The Stage 1 receipt remains an immutable prerequisite.

The legacy Stage 2 request on `main` still aliases the Stage 1 controller and
receipt. Do not launch it. This draft does not replace that request or claim
that final execution identity recovery has been completed.

Stage 3 and the website remain outside this candidate's scope.
