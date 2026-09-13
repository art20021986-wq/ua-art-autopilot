# Allocator: isolated PythonAnywhere gate

This package runs the frozen 26 allocator tests. It contains **no production
source files**, makes no deployment changes, and does not start CRM or publish
cards. Root performs upload/execution only through the already approved route.

**Actual server result: PASS on 2026-09-09, run 08:23:43 UTC.** Python 3.10.12,
26 tests, zero failures/errors/skips, 6.6821 seconds, three guarded children,
zero forbidden operations. All three production source snapshots retained
their bytes and metadata. No application top-level modules were imported.
[Server result](evidence/allocator-server-result.json), SHA-256
`dab0dc0dae7ad15fc2c857ffdd5832829b9c0e142d88608d2d0c19610d57469b`.

Package: `allocator-server-gate-v2.zip`  
SHA-256: `0d5ac01b7e6836e0a66851a6b981a81167f199860592f1d1ada32340bb810d92`

Version 2 supersedes the unexecuted server package v1. It normalizes SQLite
audit filenames with `os.fsdecode(os.fspath(...))`, including bytes and bytes
URIs observed on PythonAnywhere. Its child processes receive only the fixed
PATH, locale, and stage TMPDIR environment; inherited secrets/settings are not
passed to them, and the audit guard verifies that environment.

Required exclusive staging directory:
`/home/Carix/spec_allocator_gate_20260909`

After checking the ZIP hash and extracting its five reviewed relative members
into the new stage, run:

```sh
python3.10 -I -B /home/Carix/spec_allocator_gate_20260909/cloud/spec_auto10_restore/allocator_server_gate.py
```

The normal server entrypoint requires Python 3.10, the exact staging directory,
and `/home/Carix` as its read-only source directory. It verifies the package
manifest, then reads only the three approved source files below. Their expected
whole-file SHA-256 values are fixed in the runner and manifest. A mismatch stops
the run. Captured bytes are copied into the isolated stage for the tests; the
production application modules are never imported.

| Read-only input | Expected SHA-256 |
| --- | --- |
| `/home/Carix/cars_schema.py` | `1dd5d950eb4514901ca51911b4c5f89481263956ceea28f30e1fa2888cdd8d73` |
| `/home/Carix/db.py` | `b732a5c731d85cb4c9b1cfddb2fc20961b75230d64e29563a5b5ac328d62c086` |
| `/home/Carix/ai_filter.py` | `7dfd84497c6d3823cd7df54834cb18aecdbc645544ca9709a88c6363a2d35cb6` |

Parent and child audit guards reject network operations and writes outside the
stage. Reads outside the stage are restricted to stdlib/library files and the
three exact source paths in the parent. Temporary databases, lock files, source
copies, child scripts, working directories, and reports stay inside the stage.
The three subprocesses required by the frozen concurrency test execute only its
exact reviewed script under the same guards; other commands are refused.
Children do not receive permission to read the production source paths.

The Python audit hooks cover these trusted, reviewed Python paths. They are not
a security sandbox for hostile native extensions or arbitrary substituted code.

## Required result

The runner prints the location of its new `run-.../allocator-gate-result.json`
and `allocator-tests.log`. Acceptance requires all of:

- `status: PASS`, 26 tests, zero failures/errors/skips.
- Zero outside reads, outside writes, network events, or forbidden processes;
  exactly three permitted guarded child processes.
- No imported `db`, `cars_schema`, `ai_filter`, or `team_bot` application modules.
- Original source bytes, size, modification time, inode, and device identical
  before and after the tests.
- Package file hashes matching the reviewed manifest.

An early source or manifest mismatch is a stop, never a successful gate result.
No service reload, database migration, queue mutation, HALT change, or live
publication is part of this command.

## Local preparation evidence

The identical ZIP was extracted into an isolated local stage and run with
Python 3.12 against the previously captured, hash-identical source copies:
26/26 PASS, zero skips; 0.451 seconds; all forbidden-operation counts zero;
three guarded subprocesses. Input copies retained their bytes and modification
times. This preparation run is **not** a PythonAnywhere or live-source result.
Actual server execution is recorded separately above; the local result is retained as preparation evidence.

A separate focused check allowed a bytes filename, bytes SQLite URI, and bytes
`:memory:` database inside the gate, while rejecting both a bytes production
database path and its bytes URI before SQLite could open them. Its two expected
denials are reported separately from the 26-test acceptance counters.

The local-only `UA_ALLOCATOR_GATE_LOCAL_PREFLIGHT=1` switch permits a different
staging path for this preparation run. It does not change source hash pins,
guards, tests, or the fixed Python 3.10 requirement when the required server
stage is used.
