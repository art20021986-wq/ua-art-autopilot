# CRM opening/editing hotfix candidate — 21 September 2026

Status: **local candidate, not installed, no production PASS**.

This patch changes only `open_card`, `edit_menu`, and `edit_ask`, plus their new
display/media helpers in `cars_ui.py`. It does not alter `db.py`, price writes,
registration routes, the existing authorization model, deletion, publication,
the specification generator, or the public website. Other AST nodes are checked
unchanged. The existing list problem addressed by PR116 remains a separate item.

The source is pinned to SHA-256
`d9bd8cb352ad95892f8ac2cddcce02898ec7f3f2fe5013f1a5007bf1469db837`.
The builder rejects source drift and does not import the application, create a
backup, install files, restart services, or launch any remote operation.

## Behavior

- Normal cards retain their original display and keyboard. A renderer error,
  oversized message, or Telegram HTML rejection falls back to a short plain-text
  card with the original keyboard. If keyboard construction itself fails, a
  minimal keyboard retains editing, media, and return-to-list actions.
- Missing rows and failed reads produce an explicit message and a return button.
- The field editor escapes the displayed stored value and bounds its length.
  Only the preview is shortened; stored text is unchanged. An edit session is
  activated only after the prompt is successfully sent. Each opening/editor
  clears the previous active card before reading or sending; the requested card
  becomes active only after its screen is accepted. UA and GE field names,
  dollar hints, and saving paths remain unchanged.
- Photo/video delivery runs separately from the opening callback. One
  application-managed task per Telegram user has one replaceable latest-request
  slot. Repeated opens cancel older delivery; its replacement starts after that
  task finishes. Entering editing cancels both current and pending delivery.
  The existing per-delivery photo/video timeouts (9 and 6 seconds) remain.
- Telegram transport failures other than `BadRequest` are not retried as HTML
  failures. No hidden write or success message is generated after a failed read.

## Checks

Run from this directory:

```sh
python -W error::RuntimeWarning test_ui_hotfix.py -v
```

The suite extracts the actual functions from the built candidate using AST;
it never imports the full production module. Telegram transport and application
task management are simulated. Nineteen checks passed, including:

- the original handler remaining blocked on slow media while the candidate
  returns with its edit keyboard;
- malformed HTML, oversized descriptions, renderer/keyboard failures, and
  missing/temporarily unreadable records;
- full source binding and unchanged surrounding AST, Python 3.10 syntax;
- HTML-safe field previews without changing stored text, unchanged UA/GE field
  identity, no invisible active editor after a transport failure;
- navigating from card 9 to card 5 activating only card 5 after a successful
  screen, and transport failure leaving no prior card active for later input;
- 100 replacement requests coalescing to one active delivery and a single latest
  slot, cancellation on editing, and cancellation before a PTB-style wrapper
  starts closing its unstarted coroutine without warnings.

These checks do not establish live Telegram behavior or provider availability.

## Material limitations and remaining work

1. Synchronous database reads, specification summary rendering, and catalog
   reads can still block the event loop. Current `db.connect()` runs
   `PRAGMA journal_mode=DELETE` on every connection. Under a conflicting lock its
   initial busy timeout is 30 seconds, then read operations use 20 seconds.
   The current presence of such a lock has not been measured.
2. The read-only error fallback begins after a blocked synchronous read returns;
   this candidate is not a complete database performance repair.
3. The complete list/deletion recovery package in PR116 is not incorporated.
   Its orphan-catalog regression can still prevent entering the list until the
   corresponding reviewed list patch is installed.
4. Media timeouts rely on cooperative asyncio cancellation. The tests cover
   cancellation-cooperative senders, consistent with normal Telegram async I/O.
   No process or service restart is introduced.
5. Authorization rules are deliberately unchanged. The existing outer routing
   and staff checks have not been expanded or replaced by this patch.
6. Installation requires current source verification, the applicable authorized
   route, a verified backup, source readback, and live opening/editing acceptance.
   No production installer is included.

## Files

- `build_ui_hotfix.py`: pinned builder, exclusive output creation.
- `ui_hotfix_block.py.txt`: reviewable handler/helper source without private
  baseline configuration or credentials.
- `test_ui_hotfix.py`: isolated regression suite.
- `validation_receipt.json`: exact checks and source hashes.
- `cars_ui.candidate.py`: **private** complete generated server source; do not
  publish this file or put it into a public repository.
- `cars_ui.hotfix.diff`: changes to the three handlers and inserted helpers.

To regenerate into a new private output path:

```sh
python build_ui_hotfix.py --source ../current/cars_ui.py --output cars_ui.new.py
```
