# UA-ART-CRM-DELETE-RECOVERY-002 v1.0

The approved change repairs CRM list access and introduces recoverable deletion.
The old list could fail on unrelated HTML; the old deletion path could leave
public pages behind or let a delayed publisher restore a sold listing.

This directory contains source-bound transformation recipes, new runtime
modules, isolated tests, and review evidence. Private production source captures,
CRM data, credentials, and generated full production payloads are excluded.
The historical UA-0002 emergency retirement is not repeated by this package.

## Current status

**Offline implementation verified; Gate B remains open; not installed.** No production code, car
row, public page, media, service setting, or unrelated task block was changed
while preparing this candidate. Private source-readback files were staged for
inspection only. Test receipts describe isolated execution, not Telegram or
production acceptance.

The final isolated suite passed **342/342 tests**, with no failures or skips.
All 32 materialized source snapshots matched their canonical files, and code
and recipe data remained unchanged during validation. See
`evidence/offline_validation.json` and `evidence/build_receipt.json` for exact
hashes. The generated inner release manifest is
`b2d20d8059fa9f363c48e384a4f673c4b1d30640722e2741ead6b55ca5442b5c`.

The approved specification, section 6.5, requires Gate B and a separate owner
installation command. The owner's command was received at 07:01:57 UTC on
21 September 2026 and verified against the original conversation; no repeat
permission is needed. Its exact instruction record is preserved in
`evidence/OWNER_INSTALL_INSTRUCTION_20260921.json`. The observed repository main contains an
unrelated `AUTOPILOT_HALT.json` from
`SEO-DAILY-PODBOR-CANONICAL-20260921` / run `35552076762`. This package does not
clear it or route around the normal production authority. Its resolution is
outside this change.

`deploy/` implements the existing launcher's environment contract for separate
backup, execute and rollback operations. It declares the complete executable
dependency closure, reconstructs private payloads from exact source hashes,
and checks remote evidence before producing a workflow receipt. The original
backup is reused; data or source drift prevents installation. Detailed source
extraction tests remain outside the runtime package; their two hash-only QA
snapshots are never executed by the builder. Shared admission checks remain
unchanged. See `admission/README.md` for the exact compatibility evidence.

Platform acceptance is still pending. The authenticated console could not see
the running CRM process in its own `/proc`. The future task must prove process
and singleton-lock visibility before requesting a CRM pause; unsupported
placement must stop without changing the service.

## Resulting behavior

| Area | Candidate behavior |
| --- | --- |
| CRM list | Current CRM rows remain accessible when HTML is missing, malformed, stale, or contains orphan cards. The two folders remain; uncertain site state is explicit. |
| Confirmation | Staff authorization and an opaque token bind the actual ID, code, VIN, and complete current row version. Numeric legacy callbacks cannot confirm deletion. |
| Deletion | A verified SQLite/file backup precedes a durable intent and job. Exact public aliases, list membership, sitemap entries and dynamic counters are retired. Completion requires separate database, file and HTTP proof. |
| Recovery | Repeated callbacks and restarts resume the same job. Shared-page rebasing preserves newer unrelated edits. The recovery path never restores a whole old database or recreates a sold listing. |
| Writers | Mapped final writes, publication admission, rollback and diagnostic cleanup respect deletion reservations under the existing publication fence. |
| Media | The deletion coordinator does not delete media. Delayed diagnostic cleanup skips a reserved or absent identity. |
| HTTP | Exact historical aliases and routes backed by durable deletion manifests return 410 through the WSGI wrapper after static files are removed. Existing analytics, bridge and robots behavior is retained. |

UA-0002's historical database ID is **8**, not 2. Its separate reservation is
bound to the actual prior emergency plan, result and verified backup hashes;
the builder does not invent a routine deletion intent for an already absent row.

## Layout

- `list_patch/`: exact list transform and resilient list helper.
- `bot_patch/`: Telegram adapter, background resume job and readiness evidence.
- `deletion_core/`: transaction state, coordinator, exact retirement and runtime binding.
- `writer_patch/`: publication/restore/media guards and source-bound recipes.
- `route_patch/`: exact WSGI transform and deletion-aware routes/sitemap filtering.
- `install/`: read-only package validation and isolated installation/lifecycle mechanics.
- `deploy/`: environment entrypoints, bounded transport, strict receipts and exact runtime snapshots.
- `admission/`: workflow compatibility review, snapshot materializer and non-authorizing installation draft builder.
- `evidence/`: hashes and authenticated observations; no private source bodies.
- `build_release.py`: compose one isolated package from the reviewed private sources.
- `test_release.py`: exercise the assembled package with the current schema,
  counter code, public markup and real filesystem/SQLite/fence fixtures.

The final candidate is generated only from exact observed source hashes. Helpers
and writers precede the CRM entrypoint. Runtime pins refer to installed
after-images. The writer receipt must match the current recipes, tests and all
standalone transformed candidates; stale evidence refuses a new build.

## Reproduction

Use a private source capture containing the reviewed files, `schema.json`, the
historical `emergency-plan.json`, and the captured `public_fixture_tree/`.
The external SEO dry-run source is captured as `seo_rehab_guard_068_repair.py`.
No production module is imported by the builder.

```sh
python cloud/crm_delete_recovery_002/build_release.py \
  --sources /absolute/private-sources \
  --output /absolute/new-private-staging

python cloud/crm_delete_recovery_002/install/package_install.py \
  --package /absolute/new-private-staging \
  --manifest-sha256 EXACT_BUILD_RECEIPT_MANIFEST_SHA256
```

The build command never installs, restarts, migrates or publishes. Source drift
requires a new review; changing the expected digest to suppress refusal is not
a recovery procedure. Installation backup is coherent in SQLite WAL mode;
rollback restores code conditionally and leaves current operator data intact.

Run the complete isolated suite with exact source captures:

```sh
python cloud/crm_delete_recovery_002/validate_release.py \
  --sources /absolute/private-sources \
  --receipt /absolute/new-validation-receipt.json
```

The receipt binds every implementation/test file and rejects skipped tests or
source changes during validation. Local tests use Python 3.12; production
payload syntax is separately parsed for Python 3.10. Actual provider API,
Telegram interaction, and production restart acceptance remain unexecuted.

## Production acceptance still required

Before installation: satisfy the
existing production admission, reconcile the unrelated incident through its
authorized route, and repeat provider/process/source checks. The owner's
installation instruction is already received. The actual installation must own CRM
pause and recovery, verify backup and WSGI reload, replace old processes, and
read back runtime/job startup. Afterwards, exercise the real Telegram flow and
verify direct HTTP 404/410 plus absence from current CRM/catalog/home/sitemaps.
Offline receipts alone cannot establish those facts.
