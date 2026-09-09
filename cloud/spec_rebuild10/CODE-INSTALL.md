# Exact r2 source installer and combined transaction

`code_install.py` is the separately versioned admission and installer
`UA-ART-SPEC-REBUILD10-CODE-INSTALL-1`. It admits only runtime r2: manifest
`2605ca1a08207e94a77747b984930c07947bce8b3ee271a6454d06c9a702de40`, archive
`46a20d282cd3114eb49364a4a6b662a09a2074f58ee837c3c1982f46c416933f`.
The archive contains exactly29 source/registry files and its embedded manifest.
Admission verifies every member, byte count, digest and Python3.10 grammar;
source is neither extracted indiscriminately nor imported. The old complete17
installer and its admission pins are unchanged.

The new installer pins the unchanged reviewed FenceLease to
`199a8744b3dd335899adcac92c52e30c462d7b471898d6b94a7ba944b9f05b85` and the
Python3.10-compatible data installer to
`72c7f6a26725bcb2170da2207c753e441eb11baa8f1be2b1be139d3c947e1173`.
It borrows the live holder's existing descriptors in the same process/thread.
It never reopens a flock, closes borrowed descriptors, changes HALT, starts or
stops processes, calls the network, or clears stale persistent intent.

## Exact plan and authority

```python
from cloud.spec_rebuild10.code_install import (
    make_install_plan, make_combined_plan, CombinedInstall,
)

code_plan = make_install_plan(
    session, runtime_package_dir, exact_29_before_hashes,
    coordination_plan_sha256=reviewed_coordination_plan_sha256,
    fence_sha256=reviewed_fence_sha256,
)
combined_plan = make_combined_plan(code_plan, reviewed_data_plan)
operation = CombinedInstall(
    held_real_lease, runtime_package_dir, data_payload_dir, combined_plan,
    verify_window=trusted_controller.verify_window,
)
receipt = operation.apply()
```

These are library interfaces for a separately reviewed controller, not a bundled
production launcher. Creating plans grants no authority. The exact29 before
hashes/absences, three unchanged shell dependencies, source hashes, data manifest,
main/run/nonce/epoch/session and coordination plan are bound into the combined
plan. Fresh callbacks receive that entire combined plan and explicit child phase.
Only a validated combined challenge is translated to the exact child operation;
the callback cannot authorize independent child plans by accident. No verifier
has a positive default. Authority requires current independently authenticated
permission, pause and termination/drain of all prior writers, including WSGI.
Synthetically returning the expected dictionary proves no production authority.

Fresh target, source, dependency, holder and directory checks precede writes.
Account quota is independently required:70% warning,80% heavy-install stop,
90% emergency stop; filesystem free bytes supplement account quota. Sources and
backups are private. No actual VIN, CRM row or private application source belongs
in the public plan/report.

## Code durability and return

All29 targets receive durable backup records, including explicit absences,
mode and mtime; existing files get fsynced byte backups before any code mutation.
The only new application directory is `spec_rebuild10/`. Its creation intent and
actual inode are journaled; removal has its own durable intent. Existing parent
inodes are pinned. New files use mode0600 and the new directory mode0700; existing
file modes are retained. Rollback restores saved original modes and mtimes.
These are the metadata captured at execution, not inferred live metadata from a
private copy.

Each replacement has durable write intent and temporary-file inode evidence.
Previously absent targets use exclusive link publication instead of overwriting
an unexpected target; recovery recognizes its recorded two-link interruption.
Existing files use atomic replacement. The entire29-file set, all backup bytes,
all three dependencies, staged files and every new-directory entry are validated
before any compensation. Foreign content, symlinks, unknown links and directory
replacement stop recovery. Journals are append-only, fsynced, plan-bound and
validated without silently truncating a torn tail.

`rollback_only()` is conditional and can be resumed using durable state.
`read_terminal()` verifies current state, and `finalize_terminal()` repairs only
a missing receipt following a durable terminal event. Repeating apply never
reinstalls within the same session.

A crash between mkdir and the durable inode record cannot establish directory
ownership and therefore requires independent recovery review. A crash before a
staged file obtains durable inode evidence likewise does not authorize its
removal. Whole-holder death requires the separately authenticated recovery route
to obtain a real lease for the original session; the installer cannot manufacture
one. Unknown outcomes remain paused, with durable state preserved.

## Combined failure order

The combined coordinator has its own plan, journal and terminal receipts. Source
installation precedes data installation; the website is never disabled by this
library. Execution is allowed only in the externally proven maintenance window.
Placing new source files on disk does not prove that any running process loaded
them. This library does not claim a zero-downtime live deployment.

| Point of interruption | Durable interpretation | Allowed recovery |
|---|---|---|
| Before any application write | Originals remain authoritative | Verify complete original state; retain session journal |
| Partial or complete code, data not begun | Code may be mixed; data must remain original | Preflight both domains, then conditionally return code |
| Data in progress, including uncertain SQL commit | Code is installed; data outcome must be read from files and full CRM rows | Keep pause; preflight all code/data/CRM/backup/dependency domains |
| Both local installations complete | Local files and data read back | Still no worker startup, loaded-runtime proof or Gate B |
| Recovery interrupted | Mixed state may persist under pause | Revalidate the whole set and resume conditional recovery |

The combined path explicitly suppresses the data installer's automatic rollback:
no compensation may precede the combined preflight. Explicit combined recovery
restores **data first**, verifies every original data image, protected legacy DB,
draft and all18 CRM rows, and only then returns code. If data cannot be verified
original, code rollback never begins. A later foreign write or lost authority
halts recovery; the result is not described as atomic success. This order and
persistent pause prevent an unverified mixed state from being approved to run.

`COMBINED_LOCAL_INSTALLED` and `COMBINED_ROLLED_BACK_READBACK` are local results.
All receipts state `runtime_loaded_verified=false`, `tasks_resumed=false`,
`unpause_authorized=false`, `overall_gate_b=NOT_EVALUATED`. Real controller startup,
loaded code/store binding, fresh public readback for all16 cards and applicable
Gate B remain separate gates. UA-0017 then UA-0018 stay owner-manual only.

## Isolated tests and actual private copy

```text
SPEC_CODE_PACKAGE=/stage/runtime SPEC_CODE_DEPENDENCIES=/stage/code-before \
PYTHONPATH=/stage \
python -m unittest cloud.spec_rebuild10.tests.test_code_install -q
```

The31 focused tests use the unchanged real FenceLease on isolated lock inodes,
the exact private29-file r2 afterimages and explicit synthetic authority. Their
old code and32-page/18-row data fixtures are synthetic. The private package and
three dependencies are required; missing private inputs cause an explicit skip,
which is not a passing actual-fixture gate. They cover payload admission, borrowed
fds, fresh authority, quota, target/dependency/directory drift, backups, torn
journals, partial source replacement, link publication interruption, metadata
restoration, receipts, and combined failure/recovery order.

The relocatable helper additionally exercises actual private32 HTML and CRM/store
inputs, exclusively within a fresh temporary copy:

```python
from cloud.spec_rebuild10.tests.test_code_install import actual_private_cycle

result = actual_private_cycle(
    '/stage/snapshot', '/stage/payload', '/stage/runtime', '/stage/code-before',
    before_source_dir='/stage/code-before',
    before_observation='/stage/code-before/before-manifest.json',
)
```

With both before inputs, it verifies the observed13 present source files,
16 absent targets and three dependencies before copying; the report identifies
exact observed before **bytes**. Metadata is only that of the private input copies.
Without both optional before inputs, the report explicitly labels synthetic code
preimages. Authority always remains `SYNTHETIC_ISOLATED_TEST_ONLY`. The helper
returns only redacted evidence, validates29 postimages and32 pages plus all18
CRM rows, returns them, removes the new runtime directory/store, and never imports
application modules. It does not establish live writer exclusion or loaded code.
Run this exact final revision on actual target Python3.10 before claiming target
compatibility; local newer-Python checks alone are insufficient.

Target verification completed on Python3.10.12 at16:09:58 UTC on9 September2026:
31 new code/coordinator tests +25 data regressions =56/56 PASS, no failures,
errors or skips. The exact observed code plus actual32-page/18-row combined
cycle also passed. `evidence/target-stage-r3.json` has the exact server receipt
SHA256 `b455185a96e8d0f48c0f3fc0a758acf34bfe02775f3f6429250fc71c7b61b3d2`.
The server file was read in full through its authenticated editor and its
reconstructed bytes matched the checksum printed by the completed driver.
No production launch or loaded-runtime claim follows from this receipt.
