# Additional specification renderer

Approved task: `UA-ART-SPEC-REBUILD-10-001 v1.0`.

The renderer is a pure Python 3.10-compatible module. It performs no file writes,
network requests, CRM imports, job scheduling, publication, or process control.

## API

```python
from cloud.spec_rebuild10.render import render_block, compose_page, validate_page

fragment = render_block("UA-0001", facts, lang="uk")
candidate = compose_page(original_html, "UA-0001", facts, lang="uk")
receipt = validate_page(candidate, "UA-0001", facts,
                        previous=original_html, lang="uk")
```

`SpecError` means the candidate must not replace the last working page. The
caller owns the publication transaction, lock, backup, rollback, canonical
vehicle identity, authorization, and persisted fact provenance.

Supported facts use `key`, `value`, `label_uk`, `label_ru`, `unit`, `category`,
`source_id`, `source_url`, `verification_status`, and `is_visible`. Preserved
legacy fields `field_key`, `field_value`, `display_value`, `label`, and `label_ua`
are accepted. Missing verification rejects new facts. Accepted canonical store
verification (`verified`, `confirmed`, `official`, or an explicit manual fact)
is supported. Preserved legacy facts without verification require an explicit
`legacy_import` receipt with `fresh_verification=False`. Source resolver statuses
`MODEL_VERIFIED` and `VEHICLE_VERIFIED` are supported after canonical store
acceptance; the store verifies the source policy receipt. The renderer does not
independently verify factual truth. Verified Boolean equipment values render as
`Так`/`Ні` and `Да`/`Нет`, including a preserved false value.

## Visible behavior

- Ukrainian is the default. Russian is supported; `ua` is accepted as an alias
  for `uk`. All interface labels retain `data-ua`, `data-uk`, and `data-ru`.
- A visible native link says `Додаткова специфікація →` and targets
  `#additional-specification` on the same page.
- The specification is an expanded native section. Opening JavaScript is not
  required. Only optional source citations use native `details` disclosure.
- Exactly one potentially visible VIN is retained in the original technical
  table. Only narrowly recognized duplicate VIN markup is removed.
- An empty, hidden-only, or unverified-only set rejects publication. It never
  produces a successful-looking empty specification.

The source registry controls clickable external citations. Every active source
URL must pass `sources.validate_source_url`. Tracking URLs, unsafe protocols,
HTML, source-host mismatch, and credentials are rejected. Historical citations
are identified as preserved sources from the previous version, without active
links; their exact metadata remains in the canonical fact store. No source HTML,
remote scripts, advertising widgets, or iframes are imported into the block.

## Shell contract

The existing `<!--UA099_ADD_SPEC_START-->` and `<!--UA099_ADD_SPEC_END-->` markers
are retained as the exact owned range. Known legacy details blocks migrate to
the new native section. Duplicate, malformed, or unmarked specification blocks
fail closed. Initial insertion requires the unique existing delivery-stage
marker. Unknown layouts require explicit template review.

With `previous=...`, validation requires byte-identical HTML outside the owned
specification span and recognized duplicate VIN removals. External scripts,
stylesheets, and existing CSS are preserved in order and byte for byte. Missing
previously published field keys or reduced visible row count reject replacement.
The check intentionally does not authorize unrelated CRM or shell modifications.

For a normal, separately authorized CRM field edit, a distinct helper exists:

```python
receipt = validate_authorized_card_change(
    previous_html, candidate_html, uid, facts, exact_manifest, current_crm_row)
```

The manifest must contain exactly `uid`, `plan_id`, `action="publish"`,
`before_sha256`, `after_sha256`, `crm_row_sha256`, `shell_assets_sha256`,
`revision`, `facts_digest`, `render_facts_sha256`, and `authorization="PASS"`.
The helper verifies exact preimage, postimage, full CRM row, normalized rendered
fact payload, unchanged static assets, canonical specification, one VIN, no VIN
advertisement, and retained prior fields. `facts_digest(facts)` produces the
normalized rendering digest used in `render_facts_sha256`.

**The helper does not authenticate a manifest.** The runtime verifier must
authorize the exact business edit inside its active manual publication ticket,
bind canonical store digest/revision, and hold the publication transaction
through readback. A callback that merely echoes a request with `PASS` is valid
only as a synthetic test double and must never be a production authorization
mechanism. This helper cannot grant permission to arbitrary shell modifications.

Without a previous page, static assets must match the reviewed existing template
pin `a6a0fe686687ca04c00e697a72ee4a07957ac0afa96d37d53a9ff0146b0868ed`.
This is a template guard, not a substitute for the caller's vehicle identity,
data, lifecycle, and publication checks. A new shell requires an explicit review.

Visibility checks cover native markup and hidden ancestors. Computed CSS,
responsive layout, and click behavior still need browser acceptance on the
resulting preview and production readback. A future deployment bypassing the
guarded publisher cannot be made safe by a rendering function alone.

## Preserved helper provenance

`shell_guard.py` is an exact, unchanged vendor copy of:

`spec-work/cloud/spec_auto10_restore/runtime/card_shell.py`

SHA-256: `9d764eae5f73e8b75e8c863abb9c3ae8c3a44f0bd1fa2918a28a80e996556b0a`.

`GROUPS` and `UK_LABELS` reuse the existing task's reviewed label dictionaries
from `spec_auto10_restore/runtime/spec_publication.py`; rendering and composition
are implemented anew with relative package imports.

## Verification performed

`PYTHONPATH=rebuild-work python -m unittest discover -s rebuild-work/cloud/spec_rebuild10/tests -p 'test_render.py' -v`

Twenty-five checks passed: native anchor and expanded section, exactly one
VIN, exact shell preservation, repeated composition, disappearing fields,
unsafe source HTML/URLs/tracking, registry source mismatch, historical provenance,
no-fact rejection, marker ambiguity, legacy migration, language attributes,
conflicting fields, altered output, hidden parent, invalid URL port, exact
authorized full-card manifests, incorrect row/HTML/fact digests, static asset
changes, missing verification, and a worker → source policy → SQLite store →
renderer integration for model data and vehicle-specific false equipment.
Source documents and access grants in that integration are explicitly synthetic.

Read-only composition of private captured UA-0001 and UA-0010 templates also
passed: 43 and 25 visible preserved facts respectively, one VIN, no changes
outside allowed regions, and byte-identical repeated composition. No customer
HTML or VIN is embedded in the committed tests. These results are preparation
evidence, not a production publication receipt.
