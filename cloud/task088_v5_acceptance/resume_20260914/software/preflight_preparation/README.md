# Actual read-only preflight package

The unchanged repository builder produced the content-addressed archive in `actual_package_1650/` from the exact authenticated server observation `server/install_1650.json`. Its 1,282,938 bytes have SHA256 `7f0bf4c31088350fed169366e46e19f04ef85bca00238f23bd56c8c7342f1806`; the reported observation time is 2026-09-14T16:50:36.435375+00:00. No observation fields were synthesized or rewritten.

The actual raw Stage2 receipt is `state/receipts/TASK088-GE-PRICE-CRM-STAGE2.json`, 1,689 bytes, SHA256 `d0b731b93a73da0d041a1af6e987f0e6634823001a2461bc882c927a588faae7`. This is the raw-file hash required by the builder; the normalized JSON hash is separately recorded in `PREPARATION.json`. The receipt authorizes Stage3 prerequisites and pins the same `cars_ui.py` bytes as the actual observer and retained capture. It is not a new Stage3 activation receipt.

The actual routing input is `cloud/task088_v5_acceptance/route_observations.json`, 2,230 bytes, SHA256 `91688089f048d7181fb719a533f90f028c736aa9146dd55ea14350b69bee9e35`. Its five source pins match the retained capture and the authenticated 15:57 readback. The four home-root pins also match the complete 16:50 install observation. The static `/video/` mapping matches the authenticated hosting/readback observations. Its original 06:30 timestamp is preserved. The unchanged preflight rechecks all five current live files before and after candidate preparation; routing evidence does not prove writer exclusion.

`PREPARATION.json` lists all 17 archive code names, their exact repository mappings, SHA256 and sizes. Fifteen are explicitly enumerated in the v2 software PASS source manifest. `owner_policy.py` and `price_publication.py` are outside that manifest's enumerated directories; their current bytes instead match the recorded immutable repository HEAD blobs. This distinction is retained. All 17 archive code files were independently compared byte-for-byte with the current mapped repository files and compiled without execution.

The builder was called locally in a fresh `python3 -I -B` process after adding only the exact reviewed repository `cloud/task088_price_sync` directory to `sys.path`, checking its builder/engine/package pins, and validating the actual observation SHA and prerequisites. Direct isolated execution of the builder script would omit its sibling import directory. No live root module directory was imported. The preflight itself must run in a new process, which avoids inheriting any builder imports.

`ACTUAL_PACKAGE_METADATA.json` records the actual build result. The ZIP has 18 flat members: 17 code files and `preflight_bundle.json`. Its filename uses the first 16 characters of the bundle hash; the full archive hash is different and is pinned independently. `ACTUAL_PACKAGE_READBACK.json` records all member hashes and exact input bindings. The archive contains reviewed repository code plus hash/count inventory, authenticated quota and the existing public Stage2 receipt; no private captured Python source or CRM database was copied into it.

The old repository `cloud/task088_price_sync/preflight_bundle.json` has an obsolete contract and was not used. The existing `stage_preflight.py` downloads that fixed repository path and therefore does not deliver this generated archive. The new evidence-only `stage_preflight_archive.py` validates the full supplied archive hash, inner bundle hash, exact 18-member set, CRC, all code hashes, syntax and quota/build freshness in memory before writing anything. It opens ancestors without following symlinks and creates only a new `task088_price_sync_<id>` directory below the existing approved private parent, using directory mode 0700, exclusive file creation at 0600, fsync and complete byte readback. It prints the next command and does not execute preflight. Failed or existing destinations are never overwritten or silently reused.

After uploading the exact runner and ZIP to the approved private cloud directory, confirm their server hashes against `STAGER_INDEPENDENT_REVIEW.json` and `ACTUAL_PACKAGE_METADATA.json`. The exact staging invocation is:

```bash
python3.10 -I -B /home/Carix/autopilot_inbox/cloud/stage_preflight_archive.py --archive /home/Carix/autopilot_inbox/cloud/uaart_price_sync_preflight_27234daf72b5e275.zip --expected-archive-sha256 9ed05a24792193ead1af70ad582130c0d02ae4d6115a6ed57bbf7442cf0ff8f1 --expected-bundle-sha256 27234daf72b5e27588a5360ae93b3253228657210e8b9159e23e67fc5d77483f --staging-id pr114-20260914-1650-27234daf
```

Only after actual staging succeeds, start this separate process:

```bash
python3.10 -I -B /home/Carix/autopilot_inbox/cloud/task088_price_sync_pr114-20260914-1650-27234daf/preflight.py --output-id preflight-pr114-20260914-1650-27234daf --expected-bundle-sha256 27234daf72b5e27588a5360ae93b3253228657210e8b9159e23e67fc5d77483f
```

The embedded authenticated quota expires at **2026-09-14T17:11:42.701Z**. Execution after that boundary requires a genuinely fresh authenticated quota and a new valid observation/package where necessary; do not rewrite old timestamps. Preserve real stdout, exit code and the private report's exact hash.

The preflight reads live sources, protected public files and a read-only SQLite connection, and creates a private online database backup, separate schema-test copy and candidates only in its new private output directory. Keep those candidate/database files private: they may contain private production data. The safe result sought at this boundary is `candidate_verification: PASS`, `protected_system_readback: PASS` and the schema-test success marker, with no additional blockers. The unchanged preflight deliberately appends `CANONICAL_CONTROL_BRIDGE_GATE_B_AND_ACTIVATION_NOT_RUN`, so even that result remains **status BLOCKED, exit 1, Gate B NOT_CREATED**. Preserve that meaning; it is not complete production acceptance or activation. Any additional blocker or candidate failure remains a real unresolved gate.

No server staging, UI action, live preflight, Git mutation, deployment, recovery action or production Gate creation was performed by this preparation subtask. This report describes preparation and local archive validation only.
