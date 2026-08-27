# CRM-SPEED-001 test matrix

All tests in `test_crm_speed_gate_a.py` run fully offline against a synthetic fixture tree. No real `/home/Carix` path is read or written by the test suite.

| Area | Test | What it proves |
|---|---|---|
| Bounded input resolution | `test_resolve_inputs_ok` | All required inputs resolve with fingerprints when present |
| Bounded input resolution | `test_resolve_inputs_missing_blocks` | A missing required input produces a BLOCKED reason naming the file |
| Bounded input resolution | `test_resolve_inputs_rejects_symlink` | A symlinked required input is rejected, never followed |
| Backup evidence | `test_backup_verification_matches` / `_mismatch` | The safety backup archive hash is checked before anything proceeds |
| Safe writer | `test_safe_writer_rejects_traversal` | Writes cannot escape the isolated run directory |
| usercustomize.py | `test_transform_usercustomize_removes_forbidden_import` | Forbidden top-level imports of CRM/bot modules are removed |
| usercustomize.py | `test_transform_usercustomize_idempotent_on_clean_file` | An already-inert file is left byte-identical |
| start_safe.py / run_all.py | `test_transform_singleton_entry_requires_main_anchor` | Missing `if __name__ == '__main__':` anchor is BLOCKED, not guessed |
| start_safe.py / run_all.py | `test_transform_singleton_entry_injects_guard` | Guard is injected only inside the main block, compiles |
| start_safe.py / run_all.py | `test_singleton_guard_template_rejects_duplicate` | A second lock acquisition attempt is rejected, proving the singleton behavior actually works |
| avtoperedacha.py | `test_transform_avtoperedacha_requires_all_three_anchors` | Missing kolonki_cars/otpechatok/shag anchors is BLOCKED |
| avtoperedacha.py | `test_transform_avtoperedacha_removes_subprocess_and_adds_timeout` | subprocess-based rebuild is replaced by the bounded debounce queue call, sqlite3.connect gets an explicit timeout |
| samokontrol.py | `test_transform_samokontrol_adds_timeout` | Explicit short busy timeout is added to interactive reads |
| cars_ui.py | `test_transform_cars_ui_requires_all_four_anchors` | Missing any of the four admin routes is BLOCKED |
| cars_ui.py | `test_transform_cars_ui_removes_media_calls_and_keeps_storage_functions` | Static proof of zero reachable media-send calls in the four admin routes, while save/delete helpers remain intact |
| Debounce queue | `test_debounce_queue_collapses_burst` | Five rapid rebuild triggers collapse into exactly one executed rebuild |
| Determinism | `test_deterministic_repeat_ten_times` | Ten repeated transforms of the same input are byte-identical |
| End to end | `test_full_gate_a_run_pass_path` | A full synthetic run reaches GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL with production_write NO |
| End to end | `test_full_gate_a_run_blocked_when_missing_input` | Missing a required input fails the whole run closed, not partially |
| Repeatability | `test_repeated_gate_a_runs_are_safe` | The launcher can be run multiple times in a row without corrupting state |

Run with:

```
python3 -m unittest cloud/crm_speed_optimization/test_crm_speed_gate_a.py -v
```
