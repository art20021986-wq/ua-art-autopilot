"""Sanity test proving controller.py never fabricates PASS without real live
evidence present (i.e. it correctly fails closed when only fixtures exist).
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


def test_controller_blocks_without_live_evidence(tmp_path):
    evidence_dir = HERE / "evidence"
    live_report = evidence_dir / "live_audit_report.json"
    pre_existing = live_report.exists()
    if pre_existing:
        # Do not disturb any real evidence file if present; skip destructive check.
        return
    proc = subprocess.run([sys.executable, str(HERE / "controller.py")], capture_output=True, text=True)
    assert proc.returncode in (1, 2)
    assert "PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL" not in proc.stdout
