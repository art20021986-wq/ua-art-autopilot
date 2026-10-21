# UA-ART-CRM-DELETE-RECOVERY-002: resilient CRM list candidate

This patch replaces only the existing `UA-ART-CRM-CATALOG-FOLDERS-001`
block in `cars_ui.py`. It does not change deletion, publication, pricing,
stage synchronization, authentication, or the database.

The builder accepts exactly this independently checked source SHA-256:

`d9bd8cb352ad95892f8ac2cddcce02898ec7f3f2fe5013f1a5007bf1469db837`

## Behavior

- CRM rows remain the sole authority for list membership. An orphan site entry
  neither blocks the list nor creates a CRM row.
- The existing strict `parse_catalog` reader remains in use. Missing, malformed,
  or concurrently changed catalog files show a paginated list of all CRM rows
  with an explicit **unknown site status** message.
- Healthy catalog reads restore **В каталоге** and **Не опубликованные** folders.
  Old folder callbacks also fall back safely while the catalog is unavailable.
- A rendering/enrichment failure for one card produces a minimal row with its
  original CRM ID and open button. Other cards continue to render.
- Pagination, the employee check, callback acknowledgement, context cleanup,
  root navigation, and original registration chain are retained.
- Rows are bounded and HTML-escaped to keep 20-card messages below Telegram's
  message size limit even with unusually long stored fields.

## Local verification

```bash
BASELINE_CARS_UI=/path/to/verified/private/cars_ui.py BASELINE_CATALOG_MODULE=/path/to/verified/private/ua_crm_catalog_folders.py python -m unittest -v test_resilient_list.py
```

The 19 checks execute the actual patched async handler extracted from the
hash-bound candidate using read-only DB and Telegram stubs. They do not import
or execute the rest of the production module. Missing/malformed/race coverage
includes both root callbacks and both existing folder callbacks. Three additional
checks load the exact recovered production catalog parser (SHA-256
`63cfe41b4ce4d6e5c1f5615235da8cad50c40fde3278a799a82dfae410daf7b0`)
and verify the original orphan regression, malformed-catalog fallback, and
the distinction between a valid empty catalog and a failed read. These three
checks skip when `BASELINE_CATALOG_MODULE` is omitted; the full recorded run
includes them. These checks do not substitute for live CRM acceptance after
deployment.

## Candidate construction and integration

```bash
python build_list_patch.py --source /path/to/verified/private/cars_ui.py --destination /path/to/private/cars_ui.candidate.py
```

The command compiles the result, emits source/candidate/helper hashes, refuses a
source hash mismatch, refuses to overwrite the input, and exclusively creates
the output. It performs no installation. Keep the resulting full private module
outside git. Only this patch, helper, and tests are suitable for the repository.

Deploy `ua_crm_resilient_list.py` as a sibling module of `cars_ui.py` within the
same authorized transaction as the composed candidate. The helper must exist
before the application imports the new `cars_ui.py`. Existing
`ua_crm_catalog_folders.py` remains unchanged. Compose any independent deletion
function patch *after* `build_candidate(verified_baseline_bytes)` so that the
original source hash check cannot be bypassed. Rollback restores the previous
`cars_ui.py` and the exact prior state or absence of the new helper.

No server, CRM, site, or production file was changed by this subtask.
