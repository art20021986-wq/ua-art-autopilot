# Atomic Build Contract (Task 092)

## Pipeline (must be implemented as a single script/tool, not multiple independent scripts)

1. **lock** — acquire a publication lock so no writer runs concurrently with a build.
2. **canonical data** — load the single canonical registry (CRM export or equivalent) as the only data input.
3. **schema validation** — validate every record against `canonical_data_schema.json`.
4. **field-level validation** — VIN uniqueness/format, ID uniqueness, stage enum, media file existence and non-zero size, date parseability.
5. **build temp dir** — render homepage, catalog, and every card into an isolated temp directory. No file in the live production tree is touched during this step.
6. **build-manifest.json** — record a single `build_id` (e.g. content hash + timestamp) and list every generated file with its hash, plus source data hash used.
7. **data tests** — run `data_invariants_checklist.md` programmatically against the temp build.
8. **link tests** — verify every internal link/asset reference in the temp build resolves to an existing file inside the temp build.
9. **visual tests** — run the viewport matrix from `visual_test_matrix.md` against a local static server pointed at the temp build.
10. **canary** — publish the temp build to a canary location (local package or isolated canary URL) that is NOT the production path.

## Hard rule

Every artifact produced in one build run (homepage.html, catalog.html, every card_UA-XXXX.html) must embed the same single `build_id`. If any two artifacts in the same release disagree on `build_id`, the release is FAIL and must not proceed to canary, let alone production.

## Production phase

Explicitly out of scope for this task round. Production publish only occurs after a separate, explicit owner command, per the task's own instruction and per repository policy ("Never touch UA ART production directly from Claude/Cloud").
