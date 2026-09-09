# Runtime package and the missing code admission

`prepare_runtime_package.py` assembles a private, inert source archive. It never
imports the private application, installs files, changes permissions on the live
server, starts a process or grants authority. Only its redacted manifest belongs
in the public repository; the archive contains private application source.

## Exact compatibility result

The existing `code_handoff_v4.py` admits only the original complete17 manifest
whose file SHA-256 is
`14f42086fc8bc94aefc4e4c83bda50e01107c30d2ad893c00d658f60d0c64fff`.
It requires exactly 17 target files plus that manifest and checks each original
candidate SHA. Its admission pins have not been changed.

The new four-file CRM transformation was prepared from those exact source files;
its base pins match the original complete17 bundle. It is therefore a compatible
source transformation of that bundle, but **it is not an admissible input to the
old installer**. Keeping the old manifest fails the four changed-file checks;
replacing the manifest fails `EXACT_COMPLETE17_MANIFEST_REQUIRED` immediately.
Adding the runtime package or bootstrap also violates the old exact file set.

| Group | Exact scope |
|---|---|
| Existing modules retained | 13 of the original 17, with their original candidate hashes |
| Existing modules transformed | 4: `db.py`, `cars_ui.py`, `spec_publication.py`, `ua_additional_spec.py` |
| New explicit entrypoint | 1: `spec_rebuild10_bootstrap.py` |
| New runtime Python package | Transitive local imports from `bootstrap.py`, the generated entrypoint and the explicitly included approved collector module `source_provisioning.py`, including `__init__.py`; filenames and count are in the manifest |
| Runtime registry | 1: `spec_rebuild10/sources.json` |

The first source snapshot, `20260909-r1`, contained 27 files: 13 + 4 + 1 + 8
runtime Python files + 1 registry. It predates the pending public-sync entrypoint
wiring and explicit collector-module inclusion and is not the final install
candidate. Regeneration must include `sync.py` through the entrypoint import
closure and `source_provisioning.py`, producing a new version and new hashes.
Old snapshots are never silently overwritten.

The final current snapshot is **20260909-r2**, with **29 files**: 13 unchanged,
4 transformed,1 entrypoint,10 runtime Python modules and1 source registry.
Its redacted exact manifest is `evidence/runtime-package-r2.json`. It includes
both automatic spec synchronization and source provisioning. This is an inert
source archive; code admission and a real installation controller remain pending.

## What the preparer verifies

1. Exact complete17 base manifest, all 17 original source hashes and scope.
2. Exact four bridge input pins and transformed candidate hashes.
3. Current bootstrap runtime pins against the assembled candidate; exact generated
   entrypoint bytes against the current `prepare_bootstrap.py` constant. A stale
   generated entrypoint is rejected and must be regenerated explicitly.
4. Python 3.10 grammar and compilation of every packaged Python source, without
   executing those sources. The source registry must parse as JSON.
5. Regular bounded source files without symlinks or hardlinks. All inputs are
   reread after capture and after packaging; concurrent source changes abort.
6. A deterministic archive with exact target names, hashes, groups and counts.
   Databases, pages, media, runtime plans and a deployment controller are separate
   artifacts and are not collected by this helper.

Outputs are `runtime-package.tar.gz`, `runtime-manifest.json` and
`runtime-package-redacted.json` inside a new private version directory. The last
file contains hashes and target filenames, not application source or vehicle
data. `new_code_installer_available=false` and `code_handoff_v4_compatible=false`
are explicit; assembling a package does not close either gate.

## Concrete remaining admission and installation steps

1. Finish runtime sources and regenerate the explicit bootstrap. Produce a new
   stable archive and pin that exact version in the reviewed execution plan.
2. Capture current live preconditions for **every target in the new manifest**,
   including absence or existing hash of `spec_rebuild10/`, its files and the
   bootstrap entrypoint. The old 17-file capture cannot attest new targets.
   Retain the three existing dependency pins for `catalog_design_golden.html`,
   `catalog_design_guard.py` and `stranica.py`.
3. Implement and review a separate code-admission/installer revision for the new
   exact manifest and expanded target set. It must journal new-directory creation
   and removal, preserve file modes, borrow the live FenceLease, make durable
   backups, verify readback and conditionally roll back without overwriting
   foreign changes. Do not mutate v4 pins or bypass v4 by copying extra files.
4. Bind code installation and the separate 32-page/new-store/year-cell data
   transaction to the same authorized pause/drain session, with an explicit
   combined failure/recovery policy. Two independent successful local receipts
   alone do not establish an accepted combined installation.
5. Connect the controller's startup invocation: call `install_runtime(controller)`
   **before** `cars_ui.register` asks for the configured worker. Merely placing the
   bootstrap file on disk does not call it. The controller must supply verified
   current authority, loaded modules, HTTPS transport, existing supervisor and
   the exact CRM/specification database paths. No default controller is bundled.
6. Verify the actual loaded code and new-store binding before enabling the worker.
   Obtain public readback for all 16 cards, preserve the owner's manual sequence
   for UA-0017 then UA-0018, and close the applicable Gate B only from those actual
   results. Full supplier acceptance remains a separate ten-source evidence gate.

Whole-holder process death still requires the separately authenticated fence
reacquisition/recovery controller. Neither this package nor the data installer
archives a stale intent or manufactures a new lease.

```bash
PYTHONPATH=rebuild-work python -m cloud.spec_rebuild10.prepare_runtime_package \
  --base-dir private-runtime/complete-candidate17-v3 \
  --bridge-dir private-runtime/rebuild10-crm-candidate-v2 \
  --bootstrap-dir private-runtime/rebuild10-bootstrap-candidate-v1 \
  --module-dir rebuild-work/cloud/spec_rebuild10 \
  --output-dir private-runtime/rebuild10-runtime-package-NEW \
  --version NEW
```

Use the current regenerated bootstrap directory for the final package; the
example path identifies the initial snapshot input, not authorization to install.
