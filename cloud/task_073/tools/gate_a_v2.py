"""
cloud/task_073/tools/gate_a_v2.py

Real, GET-only Gate A for CRM-UNIFIED-CATALOG-001 v1.0 (TASK 073).

This module never writes to PythonAnywhere. It fetches live source files via
the PythonAnywhere GET-only Files API, applies the point transforms from
patcher_v2.py to in-memory copies only, compiles the candidates, and never
claims PASS unless every check in this run actually passed.

If PYTHONANYWHERE_API_TOKEN / PYTHONANYWHERE_USERNAME are not present, this
module refuses to fabricate a live result and reports
mode=BLOCKED_NO_CREDENTIALS. Only run_offline_selftest() (against synthetic
fixtures) can run without credentials, and its result is always labelled
OFFLINE_SELFTEST, never LIVE_PASS.
"""
from __future__ import annotations

import ast
import json
import os
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional

try:
    from . import patcher_v2 as patcher
except ImportError:  # pragma: no cover - direct script execution
    import patcher_v2 as patcher


class ConfigurationError(RuntimeError):
    pass


PA_API_BASE = "https://www.pythonanywhere.com/api/v0"


@dataclass
class GateAResult:
    live_credentials_present: bool
    mode: str
    checks: Dict[str, str] = field(default_factory=dict)
    passed: bool = False
    notes: List[str] = field(default_factory=list)


class PythonAnywhereReadOnlyClient:
    """GET-only client. No write/consoles/tasks endpoints are ever called."""

    def __init__(self, username: str, token: str, base_url: str = PA_API_BASE):
        self.username = username
        self.token = token
        self.base_url = base_url

    def _get(self, path: str) -> bytes:
        url = f"{self.base_url}/user/{self.username}/files/path/{path}"
        req = urllib.request.Request(url, headers={"Authorization": f"Token {self.token}"}, method="GET")
        with urllib.request.urlopen(req, timeout=20) as resp:
            if resp.getcode() != 200:
                raise ConfigurationError(f"unexpected status {resp.getcode()} for {path}")
            return resp.read()

    def fetch_text(self, remote_path: str) -> str:
        return self._get(remote_path).decode("utf-8")


def _load_credentials() -> Optional[PythonAnywhereReadOnlyClient]:
    token = os.environ.get("PYTHONANYWHERE_API_TOKEN")
    username = os.environ.get("PYTHONANYWHERE_USERNAME")
    if not token or not username:
        return None
    return PythonAnywhereReadOnlyClient(username=username, token=token)


def run_live_fetch_and_transform(client: PythonAnywhereReadOnlyClient, remote_dir: str) -> Dict[str, "patcher.PatchResult"]:
    """GET the live sources, apply the point transforms to in-memory copies
    only, and return the results. Never writes anything back."""
    results = {}
    konteyner_src = client.fetch_text(f"{remote_dir}/konteyner.py")
    r1 = patcher.transform_ekran_add_inner_actions(konteyner_src)
    r2 = patcher.transform_gde_mashina_remove_outer(r1.source)
    results["konteyner.py"] = r2

    cars_ui_src = client.fetch_text(f"{remote_dir}/cars_ui.py")
    r3 = patcher.transform_stage_menu_remove_outer(cars_ui_src)
    r4 = patcher.transform_toggle_publish_respect_ok(r3.source)
    results["cars_ui.py"] = r4

    for module_name in ("stranica.py", "master_card.py", "yadro.py"):
        src = client.fetch_text(f"{remote_dir}/{module_name}")
        r = patcher.transform_seo068_drop_stale_precondition(src)
        results[module_name] = r

    return results


def compile_check(source: str) -> None:
    ast.parse(source)
    compile(source, "<candidate>", "exec")


def run_offline_selftest(fixtures: Dict[str, str]) -> GateAResult:
    """Runs the full point-transform + compile matrix against synthetic
    fixtures bundled with the test suite. Never touches PythonAnywhere."""
    result = GateAResult(live_credentials_present=False, mode="OFFLINE_SELFTEST")
    try:
        konteyner_src = fixtures["konteyner.py"]
        r1 = patcher.transform_ekran_add_inner_actions(konteyner_src)
        compile_check(r1.source)
        r1_again = patcher.transform_ekran_add_inner_actions(r1.source)
        if r1_again.changed:
            raise AssertionError("inner-action insertion is not idempotent")
        result.checks["INNER_ACTIONS_IDEMPOTENT"] = "PASS"

        r2 = patcher.transform_gde_mashina_remove_outer(r1.source)
        compile_check(r2.source)
        outer_count = r2.source.count("sea_loaded") + r2.source.count("sea_transit")
        if outer_count != 0:
            raise AssertionError(f"expected 0 outer occurrences after strip, found {outer_count}")
        result.checks["OUTER_DUPLICATES_ZERO"] = "PASS"

        cars_ui_src = fixtures["cars_ui.py"]
        r3 = patcher.transform_stage_menu_remove_outer(cars_ui_src)
        compile_check(r3.source)
        r4 = patcher.transform_toggle_publish_respect_ok(r3.source)
        compile_check(r4.source)
        if "ROLLBACK_ON_PUBLISH_FAIL_073" not in r4.source:
            raise AssertionError("toggle_publish rollback guard missing")
        result.checks["TOGGLE_PUBLISH_ROLLBACK_PRESENT"] = "PASS"

        seo_src = fixtures["stranica.py"]
        r5 = patcher.transform_seo068_drop_stale_precondition(seo_src)
        compile_check(r5.source)
        if "SEO068_DIAGNOSTIC_TARGET_MISSING" in r5.source:
            raise AssertionError("stale precondition still present")
        result.checks["SEO068_STALE_PRECONDITION_REMOVED"] = "PASS"

        result.passed = True
    except Exception as exc:
        result.passed = False
        result.notes.append(f"OFFLINE_SELFTEST_FAILURE: {exc}")
    return result


def run(remote_dir: str = "/home/uaartlogistics/mysite") -> GateAResult:
    client = _load_credentials()
    if client is None:
        return GateAResult(
            live_credentials_present=False,
            mode="BLOCKED_NO_CREDENTIALS",
            passed=False,
            notes=[
                "PYTHONANYWHERE_API_TOKEN / PYTHONANYWHERE_USERNAME not present in this environment.",
                "Real Gate A V2 must be executed by the Codex-run GitHub Actions workflow with the secret.",
                "This module refuses to fabricate a LIVE PASS without real GET evidence.",
            ],
        )
    result = GateAResult(live_credentials_present=True, mode="LIVE_GET_ONLY")
    try:
        transformed = run_live_fetch_and_transform(client, remote_dir)
        for name, patch_result in transformed.items():
            compile_check(patch_result.source)
            result.checks[name] = "COMPILE_PASS"
        result.passed = True
    except Exception as exc:
        result.passed = False
        result.notes.append(f"LIVE_GATE_A_FAILURE: {exc}")
    return result


if __name__ == "__main__":
    outcome = run()
    print(json.dumps({
        "mode": outcome.mode,
        "passed": outcome.passed,
        "checks": outcome.checks,
        "notes": outcome.notes,
    }, indent=2, ensure_ascii=False))
