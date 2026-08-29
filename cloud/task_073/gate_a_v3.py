"""
TASK_073 ROUND 4 - gate_a_v3.py

Read-only Gate A orchestrator. Uses the PythonAnywhere "Files" API in
GET-only mode to fetch live source, compares full-file SHA256 against
cloud/task_073/evidence/live_probe.json, applies the point transforms from
patcher_v3.py in memory, compiles the result, and exercises
bundle_publisher_v3 in dry-run mode against a temporary filesystem tree.
Production is never written by this module.

Running this module against real PythonAnywhere requires:
  PYTHONANYWHERE_API_TOKEN   (secret, GET-only scope is sufficient)
  PYTHONANYWHERE_USERNAME    (e.g. Carix)

Without those two environment variables the module fails closed with
GATE_A_V3_BLOCKED_NO_CREDENTIALS and performs no network access.
"""
from __future__ import annotations

import ast
import json
import os
import sys
import tempfile
import shutil
from dataclasses import dataclass, field
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(__file__))

import patcher_v3  # noqa: E402
import bundle_publisher_v3 as bp  # noqa: E402

LIVE_PROBE_PATH = os.path.join(os.path.dirname(__file__), "evidence", "live_probe.json")

PA_USERNAME_ENV = "PYTHONANYWHERE_USERNAME"
PA_TOKEN_ENV = "PYTHONANYWHERE_API_TOKEN"
PA_API_HOST_ENV = "PYTHONANYWHERE_API_HOST"


class GateAV3Error(RuntimeError):
    pass


@dataclass
class GateACheck:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class GateAReport:
    checks: List[GateACheck] = field(default_factory=list)
    blocked_reason: Optional[str] = None

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append(GateACheck(name, passed, detail))

    @property
    def all_passed(self) -> bool:
        return bool(self.checks) and all(c.passed for c in self.checks)

    def summary_text(self) -> str:
        lines = []
        for check in self.checks:
            status = "PASS" if check.passed else "FAIL"
            suffix = (" - " + check.detail) if check.detail else ""
            lines.append("{}: {}{}".format(check.name, status, suffix))
        return "\n".join(lines)


class PythonAnywhereReadOnlyClient:
    """Minimal GET-only PythonAnywhere Files API client. No POST/PATCH/DELETE
    method exists on this class by design; Gate A must never write."""

    def __init__(self, username: str, token: str, api_host: str = "www.pythonanywhere.com"):
        self.username = username
        self.token = token
        self.api_host = api_host

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": "Token {}".format(self.token)}

    def get_file_text(self, remote_path: str) -> str:
        import requests  # local import so offline/unit tests need no dependency

        url = "https://{host}/api/v0/user/{user}/files/path{path}".format(
            host=self.api_host, user=self.username, path=remote_path
        )
        response = requests.get(url, headers=self._headers(), timeout=30)
        if response.status_code != 200:
            raise GateAV3Error("GET {} returned {}".format(remote_path, response.status_code))
        return response.text


def load_live_probe() -> Dict:
    if not os.path.isfile(LIVE_PROBE_PATH):
        raise GateAV3Error("live_probe.json evidence file missing: {}".format(LIVE_PROBE_PATH))
    with open(LIVE_PROBE_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def credentials_available() -> bool:
    return bool(os.environ.get(PA_USERNAME_ENV)) and bool(os.environ.get(PA_TOKEN_ENV))


def build_client() -> PythonAnywhereReadOnlyClient:
    username = os.environ[PA_USERNAME_ENV]
    token = os.environ[PA_TOKEN_ENV]
    host = os.environ.get(PA_API_HOST_ENV, "www.pythonanywhere.com")
    return PythonAnywhereReadOnlyClient(username, token, host)


def verify_sha(label: str, text: str, expected_sha: Optional[str], report: GateAReport) -> bool:
    actual = patcher_v3.sha256_text(text)
    if expected_sha is None:
        report.add("sha_anchor:{}".format(label), False, "no expected sha recorded in evidence")
        return False
    ok = actual == expected_sha
    report.add("sha_anchor:{}".format(label), ok, "expected={} actual={}".format(expected_sha, actual))
    return ok


def run_transform_stage(sources: Dict[str, str], report: GateAReport) -> Dict[str, str]:
    patched: Dict[str, str] = dict(sources)

    result = patcher_v3.transform_gde_mashina_exclude_outer(patched["konteyner.py"])
    report.add("transform_gde_mashina_exclude_outer", result.changed, result.after_sha256)
    patched["konteyner.py"] = result.source

    ekran_anchor = sources.get("_ekran_rows_anchor", "")
    if ekran_anchor:
        result = patcher_v3.transform_ekran_add_inner_actions(patched["konteyner.py"], ekran_anchor)
        report.add("transform_ekran_add_inner_actions", result.changed, result.after_sha256)
        patched["konteyner.py"] = result.source

    result = patcher_v3.transform_stage_menu_exclude_outer(patched["cars_ui.py"])
    report.add("transform_stage_menu_exclude_outer", result.changed, result.after_sha256)
    patched["cars_ui.py"] = result.source

    old_block = sources.get("_toggle_publish_old_block")
    new_block = sources.get("_toggle_publish_new_block")
    if old_block and new_block:
        result = patcher_v3.transform_toggle_publish_respect_ok(patched["cars_ui.py"], old_block, new_block)
        report.add("transform_toggle_publish_respect_ok", result.changed, result.after_sha256)
        patched["cars_ui.py"] = result.source

    for name in ("stranica.py", "master_card.py", "yadro.py"):
        if name not in patched:
            continue
        result = patcher_v3.transform_seo068_drop_stale_precondition(patched[name])
        report.add("transform_seo068_drop_stale_precondition:{}".format(name), result.changed, result.after_sha256)
        patched[name] = result.source

    return patched


def compile_check_all(sources: Dict[str, str], report: GateAReport) -> None:
    for name, text in sources.items():
        if not name.endswith(".py"):
            continue
        try:
            ast.parse(text, filename=name)
            report.add("compile:{}".format(name), True)
        except SyntaxError as exc:
            report.add("compile:{}".format(name), False, str(exc))


def dry_run_publish_matrix(report: GateAReport) -> None:
    tmp_dir = tempfile.mkdtemp(prefix="task073_gatea_")
    try:
        video_dir = os.path.join(tmp_dir, "video")
        os.makedirs(video_dir, exist_ok=True)

        all_numbers = ["UA-{:04d}".format(i) for i in range(1, 11)] + ["UA-0011"]

        targets = bp.CardTargets(
            auto_number="UA-0011",
            primary_path=os.path.join(video_dir, "UA-0011.html"),
            diag_path=os.path.join(video_dir, "UA-0011-diag.html"),
            catalog_path=os.path.join(video_dir, "katalog.html"),
        )
        result = bp.publish_card(targets, all_numbers, existing_diag_text=None, proba=False)
        report.add("dry_run_publish_ua0011", result.ok, result.message)

        result_repeat = bp.publish_card(targets, all_numbers, existing_diag_text=None, proba=False)
        with open(targets.catalog_path, "r", encoding="utf-8") as fh:
            catalog_text = fh.read()
        exact_once = catalog_text.count('href="UA-0011.html"') == 1
        report.add("dry_run_idempotent_repeat", result_repeat.ok and exact_once)

        future_targets = bp.CardTargets(
            auto_number="UA-9913",
            primary_path=os.path.join(video_dir, "UA-9913.html"),
            diag_path=os.path.join(video_dir, "UA-9913-diag.html"),
            catalog_path=os.path.join(video_dir, "katalog.html"),
        )
        future_numbers = all_numbers + ["UA-9913"]
        future_result = bp.publish_card(future_targets, future_numbers, existing_diag_text=None, proba=False)
        report.add("dry_run_future_card_placeholder", future_result.ok, future_result.message)

        bad_targets = bp.CardTargets(
            auto_number="UA-BAD",
            primary_path=os.path.join(video_dir, "UA-BAD.html"),
            diag_path=os.path.join(video_dir, "UA-BAD-diag.html"),
            catalog_path=os.path.join(video_dir, "katalog.html"),
        )
        original_render = bp.render_primary_html
        try:
            bp.render_primary_html = lambda auto_number: "<html>no identity or cta here</html>"
            fail_result = bp.publish_card(bad_targets, future_numbers, existing_diag_text=None, proba=False)
            report.add("dry_run_false_success_rejected", fail_result.ok is False)
            report.add(
                "dry_run_false_success_no_orphan_file",
                not os.path.exists(bad_targets.primary_path),
            )
        finally:
            bp.render_primary_html = original_render
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def run_gate_a(report: Optional[GateAReport] = None) -> GateAReport:
    report = report or GateAReport()

    if not credentials_available():
        report.blocked_reason = "GATE_A_V3_BLOCKED_NO_CREDENTIALS"
        return report

    probe = load_live_probe()
    client = build_client()

    remote_map = probe.get("remote_paths", {})
    expected_sha = probe.get("full_file_sha256", {})

    sources: Dict[str, str] = {}
    for label, remote_path in remote_map.items():
        text = client.get_file_text(remote_path)
        verify_sha(label, text, expected_sha.get(label), report)
        sources[label] = text

    if not report.all_passed:
        report.blocked_reason = "GATE_A_V3_SHA_DRIFT"
        return report

    ekran_anchor = probe.get("ekran_rows_anchor")
    if ekran_anchor:
        sources["_ekran_rows_anchor"] = ekran_anchor
    old_block = probe.get("toggle_publish_old_block")
    new_block = probe.get("toggle_publish_new_block")
    if old_block:
        sources["_toggle_publish_old_block"] = old_block
    if new_block:
        sources["_toggle_publish_new_block"] = new_block

    patched = run_transform_stage(sources, report)
    compile_check_all(patched, report)
    dry_run_publish_matrix(report)

    return report


if __name__ == "__main__":
    final_report = run_gate_a()
    print(final_report.summary_text())
    if final_report.blocked_reason:
        print("BLOCKED: {}".format(final_report.blocked_reason))
        sys.exit(2)
    sys.exit(0 if final_report.all_passed else 1)
