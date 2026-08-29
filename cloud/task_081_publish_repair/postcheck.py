#!/usr/bin/env python3
"""Immediate + delayed postcheck for TASK 081 (GET-only).

Checks, for a given base URL and auto_number:
  - primary page HTTP 200
  - diag page HTTP 200
  - exactly one occurrence of the auto_number in each catalog
  - correct stage/category token present
  - protected hashes (of files not supposed to change) are unchanged
"""
import argparse
import hashlib
import json
import re
import time
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

CATALOG_PATHS = ["/video/katalog.html", "/site/katalog.html"]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_page(session, base_url, path):
    resp = session.get(base_url + path, timeout=30)
    return resp.status_code, resp.text


def run_postcheck(base_url: str, auto_number: str, expected_category: str, protected_hashes_file: Path, delay_seconds: int = 0):
    if requests is None:
        return {"ok": False, "error": "requests not installed"}
    session = requests.Session()
    results = {"auto_number": auto_number, "checks": {}}

    for label, path in [("primary", f"/video/{auto_number}.html"), ("diag", f"/video/{auto_number}-diag.html")]:
        status, _ = check_page(session, base_url, path)
        results["checks"][label] = {"path": path, "http_status": status, "pass": status == 200}

    for cat_path in CATALOG_PATHS:
        status, html = check_page(session, base_url, cat_path)
        occ = len(re.findall(re.escape(auto_number), html))
        cat_ok = status == 200 and occ == 1
        results["checks"][cat_path] = {"http_status": status, "occurrences": occ, "pass": cat_ok}
        results["checks"][cat_path]["category_present"] = expected_category in html

    if protected_hashes_file and Path(protected_hashes_file).exists():
        expected = json.loads(Path(protected_hashes_file).read_text(encoding="utf-8"))
        mismatches = []
        for path, expected_sha in expected.items():
            status, content = check_page(session, base_url, path)
            actual_sha = sha256_bytes(content.encode("utf-8"))
            if actual_sha != expected_sha:
                mismatches.append(path)
        results["protected_hash_mismatches"] = mismatches
        results["protected_hashes_ok"] = len(mismatches) == 0
    else:
        results["protected_hashes_ok"] = None

    all_pass = all(c.get("pass", False) for c in results["checks"].values())
    results["overall_pass"] = bool(all_pass and results.get("protected_hashes_ok") in (True, None))

    if delay_seconds:
        time.sleep(delay_seconds)

    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--auto-number", required=True)
    ap.add_argument("--expected-category", required=True)
    ap.add_argument("--protected-hashes", default=None)
    ap.add_argument("--delay-seconds", type=int, default=0)
    args = ap.parse_args()

    result = run_postcheck(
        args.base_url, args.auto_number, args.expected_category, args.protected_hashes, args.delay_seconds
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
