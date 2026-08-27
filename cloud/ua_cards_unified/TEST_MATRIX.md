# Test Matrix — UA Cards Unified Gate A (TASK 021)

| Requirement | Test(s) |
|---|---|
| Real IDs UA-0001..UA-0008 accepted as required real-card codes | `TestRealIdentifiers.test_real_ids_ua0001_to_ua0008_accepted` |
| Synthetic/demo substitution rejected without banning real IDs | `TestRealIdentifiers.test_synthetic_ids_rejected_without_banning_real_ids` |
| Preflight/AST policy does not scan its own field names into a false positive | `TestPreflightSelfScanSafety.test_preflight_refuses_to_scan_its_own_source`, `test_preflight_does_not_false_positive_on_field_names` |
| Exactly one purchase anchor accepted; zero/two rejected | `TestPurchaseAnchorDetection.*` |
| Exactly one canonical diag/track href and actual companion files per card | `TestDiagTrackInsertion.test_single_diag_and_track_href_per_card`, `TestFullPipeline.test_all_real_cards_pass_but_overall_blocked_pending_ua0009` |
| Real existing tracking URL preserved / truthful empty state | `TestTrackingCompanionState.*`, `TestDiagTrackInsertion.test_unrelated_content_preserved` |
| Structural insertion ignores script-text decoys | `TestDiagTrackInsertion.test_script_decoy_does_not_move_structural_insertion` |
| One per-card failure blocks overall AWAITING_GATE_B | `TestOverallStatusLogic.test_one_card_failure_blocks_overall`, `TestFullPipeline.test_missing_one_real_card_forces_blocked` |
| Bounded discovery includes crm.db, master_card.py, stranica.py, yadro.py, and all minimum HTML candidates | `TestBoundedDiscovery.*` |
| Missing UA-0001..UA-0008 source blocks with no synthetic fallback | `TestBoundedDiscovery.test_missing_real_source_blocks_with_no_synthetic_fallback`, `TestFullPipeline.test_missing_one_real_card_forces_blocked` |
| SQLite opens read-only/query-only, no mutating SQL available | `TestSqliteReadOnly.test_readonly_connection_rejects_write` |
| Traversal, absolute unlisted output, symlink, hard-link/non-regular escape rejected before side effects | `TestSafeWriterBoundaries.*`, `TestBoundedDiscovery.test_symlinked_candidate_parent_escape_is_rejected` |
| Manifest/input/runner tamper rejected | `TestManifestAndTamperDetection.*` |
| Output writes remain inside the report namespace | `TestSafeWriterBoundaries.test_write_inside_allowed_root_succeeds`, `test_write_outside_allowed_root_rejected` |
| Protected hashes and UA-0009 evidence unchanged | `TestSqliteReadOnly.test_ua0009_evidence_fingerprint_unchanged`, `TestFullPipeline.test_protected_hashes_unchanged_after_run` |
| Repeat output byte-identical, 10 complete repetitions pass | `TestFullPipeline.test_repeat_output_byte_identical_10_times`, `test_full_preview_bundle_byte_identical_10_runs` |
| Imports cause no network/database/process/thread/filesystem mutation | `TestNoNetworkNoMutationOnImport.test_import_has_no_side_effects` |
| No production/reload/process-control capability; no-argument entrypoint really executes the bound Gate A once | `TestNoProductionCapability.*` |

Run command:
```
python3 -m unittest discover -s cloud/ua_cards_unified/tests -t cloud
```

Controller result: **41/41 PASS in each of 10 full-suite runs (410/410 total)**; Python compile PASS. This verifies readiness only and is not a claim that PythonAnywhere Gate A ran.
