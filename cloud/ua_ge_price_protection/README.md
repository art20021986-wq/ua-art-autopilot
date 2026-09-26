# UA/GE PRICE PROTECTION

Permanent regression protection for UA-ART-GE-UA-MARKET-PRICE-001 FINAL v5.0,
section 26. This package contains no deployment, database migration, Telegram
delivery, credential, or control-plane activation code.

`python3 -I -B cloud/ua_ge_price_protection/gate.py` runs the real renderer,
CRM hook, outbox, v5 runtime, authority binding, publication fence, installer,
and gate rejection tests. Required suites cannot disappear silently. All new
public regression files in the reviewed packages are included automatically.
Each test file runs in its own Python process, matching the canonical execution
contract's isolation. Failures, errors, skips, expected failures, empty suites, source drift, symlinks,
or alternate import artifacts make the exit status nonzero. Fixtures execute
with temporary storage and without inherited application credentials.

The JSON result deliberately distinguishes `software_status: PASS` from
`live_preview_status: NOT_RUN` and always states `production_authorized: false`.
Private captured-page/source tests belong to the actual full Preview. They are
never counted as passed by this software gate.

## Canonical enforcement

The active forward Production path is the reusable `uaart_critical.yml` workflow.
Its validation job runs software protection before a validation attestation is
created. Its preparation job checks the bound full Preview before PREPARING and
backup. Its fresh OPEN runner repeats software protection and Preview binding
before the step receives the PythonAnywhere Production credential. These are
ordinary required steps without `continue-on-error` or conditional bypasses.
Candidate source trees must match the validated commit before Python executes.

`uaart_maintenance.yml` also runs software protection under its existing daily
schedule and manual trigger. Existing workflow events and the exact nine-workflow
inventory remain intact. FAST and STANDARD stay restricted to non-Production.
Backup validation and monitoring are read-only. The transaction watchdog and
CRITICAL rollback paths retain their existing authority checks and are not
blocked by a failing new-release regression when restoring a prior backup.

## Full Preview evidence binding

`verify_preview.py` is an additional verifier, not an observation producer or an
authorization issuer. Invoke it only after the existing canonical mode, request,
claim and transaction checks. It verifies the request's exact byte hash and the
already authorized Gate A/manifest hash chain.

For changes to CRM, DB logic, card/home/catalog generation, price code, language
assets, autopilot or publication workflows, the hash-bound Gate A must include:

```json
{
  "price_protection_preview_path": "cloud/current-release/preview-gate.json",
  "preview_gate_sha256": "SHA256_OF_THE_EXACT_PREVIEW_FILE"
}
```

The canonical change manifest supplies `install_files_sha256` for Stage 3, or
`price_protection_candidate_sha256` for a future relevant release. The value must
equal the actual Preview's `candidate_manifest_sha256`.

The Preview uses the installer's existing exact
`TASK088-FINAL-V5-PREVIEW-GATE-1` contract and `PREVIEW_CHECKS` set. It must bind the
same task, complete published-code inventory, cars/audit/published DB hashes,
schema, system inventory, and candidate manifest. Every required check must be
PASS and its observation time must be within the preceding 30 minutes. The new
`source_files_sha256` field must exactly equal that field from the software gate's
report for the current candidate. All Python in the five reviewed package roots
and both changed workflow files participate in this closure.

The final candidate software report is `SOFTWARE_GATE_FINAL_CANDIDATE.json`:
298 tests passed without failures, errors or skips. The separate private-source
report records 83 further tests against captured deployment sources. These are
381 automated software checks, not a claim of live Preview or Production PASS.

The verifier reports `evidence_binding: PASS` only when these references agree.
It never claims to have performed browser or live DB checks. The actual Preview
producer must perform those checks; the installer/deployer must still revalidate
current DB, file preimages and writer exclusion. A changed path outside the price
components reports NOT_APPLICABLE and acquires no new live price-proof requirement.

## Activation status

The code and workflow edits are a reviewable candidate. The current canonical
control-plane exact workflow SHA, runtime manifest and mode/activation pins still
refer to the earlier runtime. They are intentionally not changed here. Their
normal authenticated update and a successful real workflow run are required
before describing this protection as active in Production. No branch-protection
settings, secrets, approval records, HALT state, or running services are modified.
