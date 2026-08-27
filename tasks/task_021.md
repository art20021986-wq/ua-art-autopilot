# TASK 021 — Resume and correct TASK 014/017 after Shared Memory acceptance

## Ordering and authority

This is the required next step after the controller independently accepted TASK 015 Shared Memory.

- TASK 015 Shared Memory: accepted by the controller after 15/15 tests, bootstrap, full managed-file hash verification, healthcheck, and deterministic context build.
- TASK 014/017 may now resume.
- Gate A only is authorized.
- Production, CRM, live card HTML, generators, database, live index, WSGI, processes, scheduled tasks, and media must not be modified or reloaded.
- UA-0009 must remain unpublished.

The safe terminal state is either `READY_FOR_GATE_A_EXECUTION` for a reviewed code package or `BLOCKED` with exact reasons. Generated code alone must never claim that live Gate A ran, that a preview is reachable, or that production is fixed.

## Mandatory rejection of the TASK 018 package

Do not reuse TASK 018 as-is. Independent controller execution found:

1. Its unit suite fails `test_valid_card_reaches_awaiting_gate_b` because preflight reports FAIL.
2. Its preflight scans its own source text for banned strings such as `api_url`, so it false-positively blocks itself.
3. It treats the real identifiers UA-0001 through UA-0008 as banned synthetic placeholders, contradicting the requirement to process those exact real cards.
4. It is primarily a JSON-fixture pipeline and does not implement the bounded live HTML/CRM/generator discovery, faithful preview transformation, and cryptographic manifest binding required by TASK 014/017.

The replacement tests must explicitly prove that self-scanning cannot create those false positives and that real identifiers UA-0001…UA-0008 are accepted as real source-card IDs. Synthetic substitution remains forbidden.

## Canonical Shared Memory context

The Autopilot worker supplies verified canonical Shared Memory context and records `MEMORY_VERSION_READ` plus `CONTEXT_BUNDLE_SHA256`. Respect the active owner directives:

- safe-inbox sync is allowed but is not production-write permission;
- Production remains behind a separate owner-bound Gate B;
- UA-0009 readiness requires real Gate A evidence;
- current UA-0009 `SAFE_TO_PUBLISH` remains `NO`.

Include both memory markers in `cloud/latest_status.md`, `cloud/owner_reply.md`, and the package report. Do not invent their values; use the values provided by the worker context.

## Required bounded live discovery

The PythonAnywhere Gate A runner must use Python 3.10 standard library only and inspect only exact hardcoded candidates. It must not recursively scan `/home/Carix`.

For each exact code UA-0001…UA-0009, card candidates must include:

- `/home/Carix/video/{CODE}.html`
- `/home/Carix/video/cards/{CODE}.html`
- `/home/Carix/video/cards/{CODE}/index.html`
- `/home/Carix/site/{CODE}.html`
- `/home/Carix/public_html/video/{CODE}.html`
- `/home/Carix/public_html/cards/{CODE}.html`
- `/home/Carix/mysite/{CODE}.html`
- `/home/Carix/{CODE}.html`

CRM candidates must include `/home/Carix/crm.db` and may include only other explicitly named bounded candidates inherited from TASK 014/017.

Generator/template candidates must include explicit bounded paths for `master_card.py`, `stranica.py`, `yadro.py`, and the existing named generator/template candidates from TASK 014/017. Read source bytes only; never import or execute a production module or generator.

Every required live input must be a regular, non-symlink file. Resolve canonical paths, reject traversal/escape, and record path, mode, size, mtime_ns, and SHA-256. For UA-0001…UA-0008, a missing real card source is a hard BLOCKED result. UA-0009 may be prepared only from actual CRM/generator evidence; otherwise its readiness is BLOCKED. Never generate a demo replacement for any real code.

## Strict isolated preview transform

All writes must be centralized through an atomic safe writer and limited to:

- `/home/Carix/video/reports/ua_cards_unified/preview/`
- `/home/Carix/video/reports/ua_cards_unified/`

The runner must reject symlinks, hard-link surprises, pre-existing non-regular targets, traversal, unresolved paths, and any write outside those roots. It may create a unique staging directory below the report namespace and atomically expose only a complete Gate A result. It must never write a production card or generator.

For each real source-card copy:

1. Parse HTML structurally with a standard-library `HTMLParser`-based inspection; do not preflight by naïvely searching the runner's own source for field-name substrings.
2. Require exactly one purchase anchor whose class-token set contains both `dejstvie` and `kn_kupit`. Zero or multiple matches is card FAIL; never guess an insertion point and never fall back to `</body>`.
3. Remove only structurally recognized legacy diagnostics/tracking entries from the copy.
4. Insert exactly one canonical diagnostics entry and one canonical tracking entry immediately before the purchase anchor, deterministically and without changing unrelated HTML.
5. Use exact card-specific hrefs `{CODE}-diag.html` and `{CODE}-track.html`.
6. Preserve unrelated text, purchase behavior, media references, styling, and verified real carrier URLs.
7. Diagnostics companion content must use real bounded source evidence or a truthful explicit empty state.
8. Tracking companion content must preserve verified carrier/container data and safe original carrier URL when present, or show the truthful explicit state `данные отслеживания уточняются`.
9. Never invent VIN, mileage, auction, diagnostic, carrier, container, or status data.

Approved source-media roots are exactly bounded roots such as `/home/Carix/video`, `/home/Carix/site`, `/home/Carix/public_html`, and `/home/Carix/mysite`. Canonically resolve referenced local files, reject escapes/symlinks/zero bytes/unsupported extensions, and copy only verified preview dependencies. A remote URL may be preserved only if already present in bounded real evidence and passes an explicit safe `http`/`https` URL policy; no network download is permitted by the code package.

## Read-only CRM rules

- Open SQLite with URI `mode=ro` and `PRAGMA query_only=ON`.
- Run bounded `quick_check`; transient lock or ambiguity is BLOCKED without mutation.
- Discover schema through bounded introspection and an explicit column-alias allowlist; do not guess mappings.
- Select only exact IDs UA-0001…UA-0009 with parameterized queries.
- Serialize only non-PII evidence needed for diagnostics/tracking/readiness.
- Never issue mutable PRAGMAs, DDL, DML, VACUUM, REINDEX, schema migration, or database copy.
- Fingerprint all UA-0009 evidence before and after and prove it is identical.

## Cryptographic manifest and restricted no-argument launcher

Create a deterministic manifest builder that accepts no arbitrary paths. The manifest must bind:

- task ID and source provenance;
- every exact discovered input path and SHA-256;
- protected production paths and before hashes;
- exact allowlisted write roots and exact planned output paths;
- runner, launcher, verifier, and manifest-builder SHA-256 values;
- target mode `GATE_A_REPORT_PREVIEW_ONLY`;
- Gate A true and Gate B false.

The restricted no-argument launcher must load the manifest, verify its own expected identity through a non-circular binding design, verify the runner and every input hash, reject symlinks/path escapes/unlisted output, execute exactly once under an exclusive lock, and write a receipt containing manifest hash, code hashes, output hashes, and protected before/after hashes. It must expose no `--apply`, arbitrary-root, arbitrary-output, production, reload, or database-write option.

Document the exact one-line PythonAnywhere Bash command, but do not execute it in this GitHub task.

## Fail-closed checkpoints and evidence

Runtime Gate A must implement measured 20/40/60/80/100 checkpoints. A 100% marker means execution finished, not passed. Immutable milestone reports may be written only after the checkpoint's work completed.

Before the runtime terminal state:

- re-fingerprint all protected sources, live cards, generator files, CRM DB, UA-0009 evidence, and bounded live inventories;
- compute `UNEXPECTED PROTECTED CHANGES` exactly;
- prove `PRODUCTION WRITE: NO`;
- validate every generated local href/src and companion file;
- generate twice and prove byte-identical canonical outputs, then run the complete deterministic fixture/static validation at least 10 times;
- record real errors/blockers without replacing them with green defaults;
- do not claim public HTTP reachability unless a later authorized execution actually performed and recorded the check.

`AWAITING_GATE_B` is a possible runtime Gate A result only if every per-card result is PASS, every protected before/after hash matches, unexpected protected changes is zero, and every other Gate A check passes. Any one card FAIL/BLOCKED forces overall BLOCKED.

## Mandatory local test suite for the generated package

Tests must be fully offline and use temporary fixture roots only. They must be executable with one standard-library unittest command and include at least:

- real IDs UA-0001…UA-0008 accepted as required real-card codes;
- synthetic/demo substitution rejected without banning the real IDs;
- preflight/AST policy does not scan its own field names into a false positive;
- exact one purchase anchor accepted; zero/two rejected;
- exactly one canonical diag and track href per card;
- real existing tracking URL is preserved;
- truthful diagnostics/tracking empty states are present and actually checked;
- one per-card failure blocks overall `AWAITING_GATE_B`;
- bounded discovery includes `/home/Carix/crm.db`, `master_card.py`, `stranica.py`, `yadro.py`, and all minimum HTML candidates;
- missing UA-0001…UA-0008 source blocks with no synthetic fallback;
- SQLite opens read-only/query-only and no mutating SQL is available;
- traversal, absolute unlisted output, symlink, and hard-link escape rejected;
- manifest/input/runner tamper rejected;
- output writes remain inside the report namespace;
- protected hashes and UA-0009 evidence unchanged;
- repeat output is byte-identical and 10 repetitions pass;
- imports cause no network, database, process, thread, or filesystem mutation;
- no production/reload/process-control capability exists.

All Python deliverables must compile. The package's own full unittest suite must pass before `READY_FOR_GATE_A_EXECUTION`; otherwise report BLOCKED.

## Deliverables

Return complete reviewable files, replacing the unsafe package under `cloud/ua_cards_unified/`:

- `cloud/ua_cards_unified/runner.py`
- `cloud/ua_cards_unified/preflight.py`
- `cloud/ua_cards_unified/manifest_builder.py`
- `cloud/ua_cards_unified/launcher.py`
- `cloud/ua_cards_unified/verifier.py`
- `cloud/ua_cards_unified/common.py`
- `cloud/ua_cards_unified/tests/test_gate_a.py`
- `cloud/ua_cards_unified/OPERATOR_INSTRUCTIONS.md`
- `cloud/ua_cards_unified/TEST_MATRIX.md`
- `cloud/ua_cards_unified/cloud_report_021.md`
- `cloud/latest_status.md`
- `cloud/owner_reply.md`

Status/report rules:

- State truthfully that this GitHub round only authored and statically checked code.
- State `PRODUCTION_TOUCHED: NO`, `CRM_TOUCHED: NO`, and `UA_0009_SAFE_TO_PUBLISH: NO`.
- Use `READY_FOR_GATE_A_EXECUTION` only if the complete offline suite passes; otherwise `BLOCKED`.
- Explain in Russian that no owner upload is required and that Production remains untouched.
