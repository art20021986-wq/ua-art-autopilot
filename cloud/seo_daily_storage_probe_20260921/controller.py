#!/usr/bin/env python3
from __future__ import annotations
import html
import json
import os
import pathlib
import re
import urllib.request
from datetime import datetime, timezone

TASK_ID = "SEO-DAILY-STORAGE-PROBE-20260921"
ROOT = pathlib.Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "cloud/seo_daily_storage_probe_20260921/evidence.json"
RECEIPT = ROOT / "state/receipts/SEO-DAILY-STORAGE-PROBE-20260921.json"
URL = "https://www.pythonanywhere.com/user/Carix/files/home/Carix/"

def atomic_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)

def to_bytes(value: float, unit: str) -> int:
    unit = unit.lower()
    factor = {"mib": 1024**2, "mb": 1000**2, "gib": 1024**3, "gb": 1000**3}[unit]
    return int(round(value * factor))

def parse_quota(body: bytes, final_url: str, status: int) -> dict:
    if status != 200 or "/login/" in final_url:
        raise RuntimeError("PYTHONANYWHERE_FILES_VIEW_NOT_AUTHENTICATED")
    if len(body) > 2_000_000:
        raise RuntimeError("PYTHONANYWHERE_FILES_VIEW_TOO_LARGE")
    text = html.unescape(body.decode("utf-8", "replace"))
    visible = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))
    match = re.search(
        r"(?:File storage:\s*)?(\d+(?:\.\d+)?)%\s*full\s*[–—-]\s*"
        r"(\d+(?:\.\d+)?)\s*(MiB|MB|GiB|GB)\s*of your\s*"
        r"(\d+(?:\.\d+)?)\s*(MiB|MB|GiB|GB)\s*quota",
        visible, re.I,
    )
    if not match:
        raise RuntimeError("PYTHONANYWHERE_STORAGE_QUOTA_NOT_FOUND")
    used = to_bytes(float(match.group(2)), match.group(3))
    total = to_bytes(float(match.group(4)), match.group(5))
    if total <= 0 or used < 0 or used > total:
        raise RuntimeError("PYTHONANYWHERE_STORAGE_QUOTA_RANGE")
    free = total - used
    return {
        "task_id": TASK_ID,
        "target_environment": "production",
        "read_only": True,
        "measured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "measurement": "authenticated PythonAnywhere Files storage DOM quota; GET only",
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "http_status": status,
        "authenticated_files_view": True,
    }

def main() -> int:
    token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
    if not token:
        raise RuntimeError("PYTHONANYWHERE_API_TOKEN_MISSING")
    request = urllib.request.Request(
        URL,
        headers={
            "Authorization": "Token " + token,
            "User-Agent": "ua-art-seo-storage-probe/20260921",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read(2_000_001)
        value = parse_quota(body, response.geturl(), int(response.status))
    atomic_json(EVIDENCE, value)
    receipt = {
        "task_id": TASK_ID,
        "status": "FINISHED",
        "task_class": "STANDARD",
        "target_environment": "shadow",
        "tests": "PASS",
        "read_only": True,
        "production_write": False,
        "evidence_path": "cloud/seo_daily_storage_probe_20260921/evidence.json",
    }
    atomic_json(RECEIPT, receipt)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
