"""Compatibility entrypoint for TASK 081.

The first-round fixture-only patcher was intentionally retired after the
fresh live audit showed that it changed incompatible function signatures.
All imports are redirected to the exact, SHA-gated production transform in
``patcher_v2``.  Direct CLI mutation is disabled; use the reviewed Gate A / B
workflows so backup, shadow execution, and rollback cannot be skipped.
"""

from patcher_v2 import *  # noqa: F401,F403


if __name__ == "__main__":
    raise SystemExit(
        "DIRECT_PATCH_DISABLED: use task081_publish_repair_live_audit_v2 "
        "and the separately approved TASK081_GATE_B_V2 workflow"
    )
