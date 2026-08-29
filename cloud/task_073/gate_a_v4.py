"""TASK 073 ROUND 5 - gate_a_v4.py

Real, GET-only Gate A for the CRM-UNIFIED-CATALOG-001 V4 candidate.
Fetches the six live files from PythonAnywhere (Files API, GET only),
verifies full-file SHA anchors, applies patcher_v4 transforms in
memory, compiles the result, and writes a sanitized JSON evidence file.
Never writes to production. Fails closed if credentials are missing or
any SHA/pattern mismatch is found.
"""

import json
import os
import sys
import time

import patcher_v4 as pv4

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

FILES_API = "https://www.pythonanywhere.com/api/v0/user/{user}/files/path{path}"


def _headers(token):
    return {"Authorization": "Token %s" % token}


def fetch_file(session, username, token, remote_path, timeout=30):
    url = FILES_API.format(user=username, path=remote_path)
    resp = session.get(url, headers=_headers(token), timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError("GET_FAILED:%s:%s" % (remote_path, resp.status_code))
    return resp.content.decode("utf-8")


def run_gate_a(session=None, username=None, token=None):
    username = username or os.environ.get("PYTHONANYWHERE_USERNAME")
    token = token or os.environ.get("PYTHONANYWHERE_API_TOKEN")

    result = {
        "task": "task_073",
        "gate": "GATE_A_V4",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "production_writes": 0,
        "files_checked": [],
        "transforms": {},
        "status": None,
        "reason": None,
    }

    if not username or not token:
        result["status"] = "BLOCKED_NO_LIVE_CREDENTIALS"
        result["reason"] = "PYTHONANYWHERE_API_TOKEN or PYTHONANYWHERE_USERNAME missing"
        return result

    if session is None:
        if requests is None:
            result["status"] = "BLOCKED_NO_REQUESTS_LIB"
            result["reason"] = "requests library unavailable"
            return result
        session = requests.Session()

    sources = {}
    try:
        for filename in pv4.FULL_FILE_ANCHORS:
            remote_path = "/home/%s/%s" % (username, filename)
            content = fetch_file(session, username, token, remote_path)
            pv4.check_full_file_sha(filename, content)
            sources[filename] = content
            result["files_checked"].append({
                "file": filename,
                "sha256": pv4._sha256(content),
                "matches_anchor": True,
            })
    except pv4.DriftError as exc:
        result["status"] = "FAIL_SHA_DRIFT"
        result["reason"] = str(exc)
        return result
    except Exception as exc:
        result["status"] = "FAIL_FETCH"
        result["reason"] = str(exc)
        return result

    try:
        pv4.patch_konteyner(sources["konteyner.py"])
        pv4.patch_cars_ui(sources["cars_ui.py"])
        pv4.patch_seo068_stale_precondition("stranica.py", sources["stranica.py"])
        pv4.patch_seo068_stale_precondition("master_card.py", sources["master_card.py"])
        pv4.patch_seo068_stale_precondition("yadro.py", sources["yadro.py"])
        pv4.patch_publikaciya(sources["publikaciya.py"])
    except (pv4.DriftError, pv4.PatternError) as exc:
        result["status"] = "FAIL_TRANSFORM"
        result["reason"] = str(exc)
        return result
    except SyntaxError as exc:
        result["status"] = "FAIL_COMPILE"
        result["reason"] = str(exc)
        return result

    result["transforms"] = {f: "OK" for f in pv4.FULL_FILE_ANCHORS}
    result["status"] = "PASS_READY_FOR_APPROVED_GATE_B"
    result["reason"] = "All six live files matched anchors, transformed and compiled clean."
    return result


def main():
    result = run_gate_a()
    print(json.dumps(result, indent=2, sort_keys=True))
    out_path = os.environ.get("GATE_A_V4_EVIDENCE_PATH", "gate_a_v4_evidence.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, sort_keys=True)
    if result["status"] != "PASS_READY_FOR_APPROVED_GATE_B":
        sys.exit(1)


if __name__ == "__main__":
    main()
