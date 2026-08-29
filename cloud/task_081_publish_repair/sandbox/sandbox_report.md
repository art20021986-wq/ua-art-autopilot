# Sandbox / canary report — TASK 081

## Scope note (read first)

No real PythonAnywhere source or database snapshot was downloaded in this
round because no API credentials were available to this worker. Everything
below describes the **synthetic fixture** sandbox bundled under
`cloud/task_081_publish_repair/tests/`, which models the exact bug reported
by the owner (false success message, SEO068 ordering bug, missing rollback).
This fixture sandbox is not a substitute for the required real Gate A GET
audit against production source; it demonstrates that the fix design is
correct and mechanically testable, and it will be re-run against the real
files the moment `live_probe.py` is executed with real credentials.

## Reproduced FAIL (fixture)

`tests/test_toggle_publish.py::test_reproduces_reported_bug_false_success` and
`tests/test_seo068_normalize.py::test_reproduces_reported_bug_new_card_always_fails`
reproduce, in isolation, exactly the two defects named in the task:

1. `buggy_toggle_publish` writes `published=1` and returns
   `{"ok": True, "message": "Машина видна клиентам в каталоге."}` even when
   the publisher result (`_ok_rem2`) was `False` — matching the screenshot
   evidence ("сборщик не смог собрать UA-0013" followed by a false success
   line).
2. `buggy_normalize_checks_live_root_only` raises
   `SEO068_DIAGNOSTIC_TARGET_MISSING:UA-0013` for any brand-new card that has
   no live diagnostic page yet, exactly matching the CRM error text quoted by
   the owner.

## Candidate fix behavior (fixture)

- `fixed_toggle_publish` never returns success unless the publisher result is
  `True` **and** primary/diag are reachable **and** the card appears exactly
  once in both catalogs; any other path performs a compensating rollback and
  asserts the DB state equals the preimage before returning exactly one
  failure message.
- `fixed_normalize` creates the `Материалы диагностики ожидаются` placeholder
  inside the staging bundle before validating the diag link, so a new card
  (UA-0013 today, or a future UA-9999) is never blocked purely because the
  live diagnostic page does not exist yet. The wrong-diagnostic-link check is
  preserved and still fails closed for a mismatched href.
- `installer.py` tests prove atomic install with automatic rollback on any
  read-back mismatch, and that rollback removes a placeholder that had no
  prior backup (i.e. never leaves a half-installed state).

## What remains for a true canary run (requires live evidence)

1. Run `live_probe.py` (Gate A workflow) with real `PYANYWHERE_API_TOKEN` /
   `PYANYWHERE_USERNAME` secrets to fetch the real files and the real
   `UA-0013` row.
2. Feed the AST hashes from that report into an `anchors.json` and run
   `patcher.py --root <downloaded_copy> --anchors anchors.json --apply` against
   a sandbox copy only (never production).
3. Re-run this same offline test suite against the patched real files (by
   importing the patched functions instead of the fixture stand-ins) plus:
   - two deterministic full runs of the sandbox build for UA-0013 and a
     synthetic UA-9999 with no diagnostics;
   - injected FAIL/exception/read-back-mismatch/partial-install/delayed-
     overwrite scenarios, each producing exactly one failure message and a
     verified rollback;
   - a dynamic sweep of all current cards, with UA-0009, UA-0012, UA-0013
     checked individually;
   - a hash diff proving all other cards' primary/media hashes are byte-
     identical before and after, and that both catalogs changed by exactly
     one inserted card with no duplicate CTA/diag link/category.
4. Record the resulting verdict in this file and in canonical shared memory
   before any Gate B request is made.

## Current verdict

`BLOCKER: live GET audit evidence not available in this round.` Offline
fixture tests pass and demonstrate the fix design is sound; real Gate A
evidence against the live PythonAnywhere files/DB is still required before
Gate A can output `PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL` with any
credibility, and `controller.py` is coded to refuse to emit that string until
a live audit report is actually present.
