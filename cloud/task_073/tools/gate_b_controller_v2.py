"""
cloud/task_073/tools/gate_b_controller_v2.py

Manual-only Gate B controller. workflow_dispatch invokes this with an
approval token that must exactly equal
CRM-UNIFIED-CATALOG-001-V1.0-APPROVED. Claude/Cloud never runs this against
production; only Codex, after Gate A V2 PASS, executes it.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

try:
    from . import gate_b_installer_v2 as installer_mod
    from . import postcheck_v2 as postcheck
except ImportError:  # pragma: no cover - direct script execution
    import gate_b_installer_v2 as installer_mod
    import postcheck_v2 as postcheck

REQUIRED_APPROVAL_TOKEN = "CRM-UNIFIED-CATALOG-001-V1.0-APPROVED"


class ApprovalError(RuntimeError):
    pass


class GateBFailure(RuntimeError):
    pass


@dataclass
class GateBReport:
    approved: bool
    steps: List[Dict[str, str]] = field(default_factory=list)
    final_status: str = "NOT_RUN"
    rollback_performed: bool = False


class GateBController:
    def __init__(
        self,
        write_set: List[installer_mod.WriteSetEntry],
        base_url: str,
        auto_number: str,
        revision_marker: str,
        preflight_fn: Callable[[], bool],
        dry_run_fn: Callable[[], bool],
        reload_fn: Callable[[], bool],
        exclusive_window_fn: Callable[[], bool],
    ):
        self.write_set = write_set
        self.base_url = base_url
        self.auto_number = auto_number
        self.revision_marker = revision_marker
        self.preflight_fn = preflight_fn
        self.dry_run_fn = dry_run_fn
        self.reload_fn = reload_fn
        self.exclusive_window_fn = exclusive_window_fn
        self.report = GateBReport(approved=False)

    def _step(self, name: str, ok: bool, detail: str = "") -> None:
        self.report.steps.append({"step": name, "status": "PASS" if ok else "FAIL", "detail": detail})
        if not ok:
            raise GateBFailure(f"{name} failed: {detail}")

    def run(self, approval_token: str, delay_seconds: float = 60.0, sleep_fn=time.sleep) -> GateBReport:
        if approval_token != REQUIRED_APPROVAL_TOKEN:
            raise ApprovalError("approval token mismatch; refusing before secrets/write")
        self.report.approved = True

        installer: Optional[installer_mod.AtomicInstaller] = None
        try:
            self._step("EXCLUSIVE_WINDOW", self.exclusive_window_fn())
            self._step("PREFLIGHT_SHA_MATCH", self.preflight_fn())
            self._step("SHADOW_DRY_RUN", self.dry_run_fn())

            installer = installer_mod.AtomicInstaller(self.write_set)
            manifest = installer.install()
            self._step("ATOMIC_INSTALL", manifest.committed, "write set committed")

            self._step("SERVICE_RELOAD", self.reload_fn())

            verify = postcheck.immediate_and_delayed_verify(
                self.base_url, self.auto_number, self.revision_marker,
                delay_seconds=delay_seconds, sleep_fn=sleep_fn,
            )
            self._step("IMMEDIATE_VERIFY", verify["immediate"].ok, verify["immediate"].reason)
            self._step("DELAYED_VERIFY", verify["delayed"].ok, verify["delayed"].reason)

            self.report.final_status = "PASS"
            return self.report
        except GateBFailure as exc:
            self.report.final_status = f"FAIL: {exc}"
            if installer is not None:
                try:
                    installer.rollback()
                    self.report.rollback_performed = True
                    self.report.steps.append({"step": "AUTOMATIC_ROLLBACK", "status": "PASS", "detail": "write set restored"})
                except Exception as rb_exc:
                    self.report.steps.append({"step": "AUTOMATIC_ROLLBACK", "status": "FAIL", "detail": str(rb_exc)})
            raise
        except Exception as exc:
            self.report.final_status = f"FAIL: unexpected {exc}"
            if installer is not None:
                try:
                    installer.rollback()
                    self.report.rollback_performed = True
                except Exception:
                    pass
            raise


if __name__ == "__main__":
    print(json.dumps({"info": "gate_b_controller_v2 is invoked programmatically by the manual workflow"}))
