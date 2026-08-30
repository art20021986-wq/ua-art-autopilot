#!/usr/bin/env python3
"""
TASK 094 — public verification checks (zero-LLM, deterministic).

Used by restore_controller.py both immediately and after a delay following any
write, per the mandatory two-pass public verification rule. This module never
writes anything; it only reads the public site and returns structured pass/fail
results. A script exit code alone is never treated as PASS by the caller.
"""
import re
import time
import urllib.request

HOME_URL_TEMPLATE = "https://ua-art.example-domain.invalid/video/index.html?cb={ts}"
CATALOG_URL_TEMPLATE = "https://ua-art.example-domain.invalid/video/katalog.html?cb={ts}"

EXPECTED_STAGE_ORDER = ["Kyiv", "Georgia", "Ferry", "Korea"]
EXPECTED_COUNTS = {"total": 13, "kyiv": 3, "georgia": 1, "ferry": 7, "korea": 2}
REQUIRED_IDS = [f"UA-{n:04d}" for n in range(1, 14)]


def _fetch(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "ua-art-verify/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def check_http_200_and_stage_order(base_url_template, real_domain):
    ts = int(time.time())
    url = base_url_template.format(ts=ts).replace(
        "ua-art.example-domain.invalid", real_domain
    )
    status, body = _fetch(url)
    result = {"url": url, "http_status": status, "ok": status == 200}
    if status != 200:
        return result

    positions = []
    for stage in EXPECTED_STAGE_ORDER:
        idx = body.find(stage)
        positions.append((stage, idx))
    result["stage_positions"] = positions
    found_all = all(idx != -1 for _stage, idx in positions)
    in_order = found_all and all(
        positions[i][1] < positions[i + 1][1] for i in range(len(positions) - 1)
    )
    result["stages_found"] = found_all
    result["stages_in_order"] = in_order

    mobile_marker_present = bool(
        re.search(r"image-above|stage-media[^>]*>.*?stage-text", body, re.S)
        or "vehicle-card-media" in body
    )
    result["mobile_vertical_marker_present"] = mobile_marker_present

    ids_found = {vid: (vid in body) for vid in REQUIRED_IDS}
    result["required_ids_found"] = ids_found
    result["all_required_ids_present"] = all(ids_found.values())

    result["pass"] = (
        result["ok"]
        and result["stages_found"]
        and result["stages_in_order"]
        and result["mobile_vertical_marker_present"]
        and result["all_required_ids_present"]
    )
    return result


def run_two_pass_check(real_domain, delay_seconds=90):
    first = check_http_200_and_stage_order(HOME_URL_TEMPLATE, real_domain)
    time.sleep(delay_seconds)
    second = check_http_200_and_stage_order(HOME_URL_TEMPLATE, real_domain)
    both_pass = bool(first.get("pass")) and bool(second.get("pass"))
    return {
        "immediate_check": first,
        "delayed_check": second,
        "delay_seconds": delay_seconds,
        "public_verification_pass": both_pass,
    }


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("usage: verification_checks.py <production-domain>", file=sys.stderr)
        sys.exit(2)
    out = run_two_pass_check(sys.argv[1])
    print(json.dumps(out, indent=2, ensure_ascii=False))
