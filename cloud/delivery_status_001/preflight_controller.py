"""Read live source through GET only and validate candidates on the Actions runner."""

import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import urllib.parse
import urllib.request

from integration_patch import SOURCE_SHA256, build_candidate


TASK_ID = os.environ.get("UAART_TASK_ID", "DELIVERY-STATUS-PREFLIGHT-20260927")
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def get(token, route):
    request = urllib.request.Request(BASE + route, headers={"Authorization": "Token " + token})
    with urllib.request.urlopen(request, timeout=30) as response:
        content = response.read(4 * 1024 * 1024 + 1)
    if len(content) > 4 * 1024 * 1024:
        raise RuntimeError("RESPONSE_SIZE")
    return content


def main():
    if (not re.fullmatch(r"DELIVERY-STATUS-PREFLIGHT-[0-9]{8}(?:-R[1-9][0-9]*)?", TASK_ID)
            or os.environ.get("UAART_TASK_CLASS") != "STANDARD"):
        raise RuntimeError("TASK_IDENTITY")
    run_id = os.environ.get("UAART_RUN_ID", "")
    if not re.fullmatch(r"[0-9]+", run_id):
        raise RuntimeError("RUN_ID")
    request = ROOT / os.environ["UAART_REQUEST_PATH"]
    if hashlib.sha256(request.read_bytes()).hexdigest() != os.environ["UAART_REQUEST_SHA256"]:
        raise RuntimeError("REQUEST_SHA")
    receipt_name = "state/receipts/" + TASK_ID + ".json"
    if os.environ["UAART_RECEIPT_PATH"] != receipt_name:
        raise RuntimeError("RECEIPT_IDENTITY")
    token = os.environ["PYTHONANYWHERE_API_TOKEN"]
    quota = json.loads(get(token, "cpu/"))
    evidence = {
        "task_id": TASK_ID, "run_id": run_id,
        "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "cpu": quota, "production_written": False, "full_acceptance": False,
    }
    print("CPU_EVIDENCE=" + json.dumps(evidence, sort_keys=True), flush=True)
    try:
        sources = {name: get(token, "files/path/home/Carix/" + urllib.parse.quote(name))
                   for name in SOURCE_SHA256}
        candidate = build_candidate(sources, (HERE / "delivery_status.py").read_text())
        golden = get(token, "files/path/home/Carix/catalog_design_golden.html").decode()
        with tempfile.TemporaryDirectory() as temporary:
            source_root = Path(temporary)
            for name, content in sources.items():
                (source_root / name).write_bytes(content)
            with patch.dict(os.environ, {"DELIVERY_SOURCE_ROOT": str(source_root)}):
                suite = unittest.defaultTestLoader.loadTestsFromNames([
                    "test_delivery_status", "verify_catalog_integration", "verify_crm_integration",
                    "verify_worker_integration", "test_status_migration",
                ])
                result = unittest.TextTestRunner(verbosity=1).run(suite)
                if not result.wasSuccessful():
                    raise RuntimeError("INTEGRATION_TESTS_FAILED")
                evidence["tests_passed"] = result.testsRun
                import verify_catalog_integration as catalog_tests
                with patch.object(catalog_tests, "GOLDEN", golden):
                    suite = unittest.defaultTestLoader.loadTestsFromTestCase(catalog_tests.CatalogIntegrationTest)
                    result = unittest.TextTestRunner(verbosity=1).run(suite)
                    if not result.wasSuccessful():
                        raise RuntimeError("LIVE_GOLDEN_TESTS_FAILED")
                    evidence["live_golden_tests_passed"] = result.testsRun
        evidence["candidate_sha256"] = {name: hashlib.sha256(content).hexdigest()
                                         for name, content in candidate.items()}
        evidence["source_sha256"] = SOURCE_SHA256
        evidence["status"] = "PASS"
    except Exception as error:
        evidence.update(status="FAIL", error_type=type(error).__name__, error=str(error)[:200])
        raise
    finally:
        (HERE / "preflight_evidence.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
        print("PREFLIGHT_EVIDENCE=" + json.dumps(evidence, sort_keys=True), flush=True)
        success = evidence.get("status") == "PASS"
        receipt = {
            "task_id": TASK_ID, "task_class": "STANDARD", "run_id": run_id,
            "status": "FINISHED" if success else "FAILED", "target_environment": "shadow",
            "observation_environment": "production_read_only",
            "request_sha256": os.environ["UAART_REQUEST_SHA256"],
            "tests": "PASS" if success else "FAIL", "unexpected_changes": 0,
            "production_required": False, "production_touched": False,
            "rollback_ready": True, "rollback_reason": "GET only; candidates tested in a disposable runner directory",
            "full_acceptance": False,
        }
        target = ROOT / receipt_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(receipt, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
