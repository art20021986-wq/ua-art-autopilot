# TEST_MATRIX — CRM-SPEED-001 admin-media transform (TASK 027 correction)

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

All tests live in `cloud/crm_speed_optimization/test_cars_ui_transform.py`
and exercise `cloud/crm_speed_optimization/cars_ui_transform.py` purely
offline (no network, no PythonAnywhere, no CRM, no bot process).

| # | Test | Scenario | Expected status |
|---|------|----------|------------------|
| 1 | test_direct_simple_media_call_transforms_cleanly | Direct sync/awaited reply_photo/reply_video with open() argument, entry route itself | OK, text-only, no `open(` remains |
| 2 | test_reachable_private_helper_exclusive_to_admin_transforms_cleanly | Private helper called only by one admin route contains one direct media call | OK, rewritten cleanly (renamed from misleading `..._blocks`; same fixture/semantics) |
| 3 | test_shared_helper_with_external_caller_blocks | Same helper also called by a customer/public function outside admin reach | BLOCKED (shared_helper_called_by) |
| 4 | test_media_group_count_and_async_await_ok | Awaited reply_media_group with a 2-element literal list | OK, text mentions `2 item`, `await` preserved |
| 5 | test_open_call_outside_media_expression_blocks | open() used outside any media-send expression | BLOCKED (unresolved_callable:open) |
| 6 | test_getattr_dynamic_dispatch_blocks | getattr(message,'reply_photo')(...) | BLOCKED |
| 7 | test_attribute_alias_assignment_blocks | `fn = message.reply_photo; fn(...)` | BLOCKED (attribute_alias_reference) |
| 8 | test_lambda_wrapped_media_call_blocks | Media call wrapped in a lambda inside a callback list | BLOCKED |
| 9 | test_callback_container_media_reference_blocks | Media method stored in a dict/list callback container | BLOCKED |
| 10 | test_return_alias_of_media_method_blocks | `return message.reply_photo` (unbound alias returned) | BLOCKED (attribute_alias_reference) |
| 11 | test_side_effectful_media_argument_helper_blocks | Media call argument is a call to an arbitrary helper with side effects (not open/download/thumbnail) | BLOCKED (unsafe_media_argument_side_effect) |
| 12 | test_protected_customer_function_untouched_when_not_reachable | Customer function with its own reply_photo, not reachable from admin entry | OK overall; customer function byte-for-byte unaffected (protected-hash check) |
| 13 | test_missing_entry_point_blocks | Entry point name not present in module | BLOCKED (missing_entry_points) |
| 14 | test_candidate_compiles_for_all_ok_cases | Two entry routes, each with a clean direct media call | OK, candidate compiles |

## Root-cause regression coverage

Tests #1 and #2 are the two tests the controller reported FAILING
(status BLOCKED instead of OK) against commit
6e0ddb846f88eb4d36d0df36b69ed7f8b4fc437e. Neither test was deleted,
skipped, or weakened. Test #2 was renamed from
`test_nested_helper_media_call_blocks` to
`test_reachable_private_helper_exclusive_to_admin_transforms_cleanly`
because its old name asserted the wrong (buggy) expected outcome; the
fixture and executed code path are preserved.

## Controller execution status

Claude/Cloud does not execute code against Production, CRM, or
PythonAnywhere and does not itself run the mandatory 10 consecutive
full green controller passes. This package is submitted for the
controller to run:

1. `python -m py_compile cloud/crm_speed_optimization/cars_ui_transform.py cloud/crm_speed_optimization/test_cars_ui_transform.py`
2. `python -m unittest cloud/crm_speed_optimization/test_cars_ui_transform.py -v`, repeated 10 consecutive times, all green, before this package can move past READY_FOR_CONTROLLER_REVIEW.

Each test scenario above was manually traced against the corrected
`scan_reachable_call_graph` / `transform_cars_ui` logic line by line to
confirm the expected status before submission, but this is not a
substitute for the controller's independent execution.
