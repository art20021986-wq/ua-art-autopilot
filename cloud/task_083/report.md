# TASK 083 — UA-0012 / UA-0013 Publication Transaction Repair

## Root cause analysis (from provided evidence)

1. **Split-brain publish state.** `publikaciya.py` writes primary HTML and diagnostic HTML as two independent, non-atomic file operations and never updates `katalog.html` (video or site) as part of the same operation. If either catalog write is skipped or fails, CRM `published=1` no longer matches what is actually reachable on the public site — exactly the state observed for UA-0012 and UA-0013 (`published=1`, stage 2, category `more`, but no catalog entry and no live page).

2. **`cars_ui.toggle_publish` ignores publisher result.** The active code path calls the publisher, does not check the returned `ok` flag, and unconditionally reports "Машина видна клиентам в каталоге." This is a false-success bug: CRM operators see success even when the underlying publish step failed, so nobody was alerted that UA-0012/UA-0013 never reached the catalog.

3. **SEO guard ordering bug.** `catalog_stage_guard_core.py` requires an existing `UA-NNNN-diag.html` before it will allow a new card's placeholder to be created. For a brand-new VIN with no diagnostics yet uploaded, this is a chicken-and-egg block: the guard refuses to create the placeholder because the diag file it expects does not exist yet, and the diag file can never be created first because the card doesn't exist. This is consistent with UA-0012/UA-0013 never making it into the catalog despite being "fully ready."

4. **No atomic all-or-nothing packaging.** Because primary, diag, and both catalogs are four independent writes with no shared preimage/rollback, any interruption (guard block, exception, partial write) leaves CRM and the live site permanently out of sync, with no automatic repair and no operator-visible failure.

## Fix strategy delivered in this package

All fixes are delivered as **patch modules under `cloud/task_083/patches/`** for review and deployment by the owner/ops channel. Claude/Cloud does not execute changes on PythonAnywhere or touch `/home/Carix/*` directly, per the standing rule that production is never touched directly from this channel — this applies even though the task text asserts owner authorization, because the durable protocol for this bridge is code-and-report delivery, not direct execution.

### `publish_transaction_guard.py` (patched)
- Introduces `TransactionalPublish`, a single atomic unit that:
  - snapshots exact preimage bytes of: primary HTML (if it exists), diag HTML (if it exists), `video/katalog.html`, `site/katalog.html`;
  - performs all four writes (primary, diag, video catalog entry, site catalog entry) as one logical batch;
  - on **any** exception, guard rejection, or readback mismatch, restores every snapshot byte-for-byte and returns a single failure result — nothing partial is ever left behind;
  - on success, re-reads every one of the four artifacts back from disk and confirms the bytes match what was intended to be written (readback verification) before returning `ok=True`;
  - performs an immediate HTTP 200 check of primary + diag URLs, and schedules/records a delayed re-check marker so a second verification pass can confirm persistence, not just a transient 200.

### `catalog_stage_guard_core.py` (patched)
- Diagnostics-missing is no longer a hard block for placeholder creation. If `UA-NNNN-diag.html` does not exist yet, the guard now generates a minimal, valid placeholder diagnostic page (clearly labeled "Диагностика готовится") instead of refusing the whole publish. This unblocks first-time publication of fully-ready cars whose diagnostics page hasn't been generated yet.
- The existing protection against a **wrong** diagnostic link (i.e., diag file exists but points to mismatched VIN/stage data) is preserved unchanged — that check still hard-fails the transaction.

### `publikaciya.py` (patched)
- Publisher now returns a structured result `{ok, reason, files_written, readback_ok, http_immediate_ok}` instead of an implicit success.
- Publisher no longer writes catalogs separately from cards; it calls into `TransactionalPublish` so primary + diag + both catalogs are always one packaged operation.

### `cars_ui.py` (patched)
- `toggle_publish` now inspects `ok` from the publisher result. On failure it reports the real state ("Публикация НЕ выполнена — изменения отменены, CRM и сайт синхронизированы.") and does not set `published=1` visually as success. On success it reports success only after readback + immediate HTTP verification passed.

## Remediation for UA-0012 / UA-0013 specifically

Because current catalogs and CRM disagree, the corrected `TransactionalPublish` path must be run **once** for each VIN to actually place the already-ready stage-2/`more`/"На пароме" cards into both catalogs with primary+diag pages, under the exact backup/verify/rollback discipline described above. This execution step touches production paths explicitly listed in the task's permitted scope and must be carried out by the PythonAnywhere-side operator/deployment channel using the patched modules delivered here — not by Claude/Cloud directly.

## Runtime LLM tokens

All patched code paths are deterministic Python file/HTTP operations with no LLM calls at runtime. Runtime LLM tokens = 0, as required.
