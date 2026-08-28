#!/usr/bin/env python3
"""Read-only Gate A against the exact current production source files."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import tempfile
import urllib.parse
import urllib.request

import repair_remote as repair


HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "evidence" / "source_shadow.json"
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/files/path"
MAX_BYTES = 8_000_000


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="", dir=path.parent,
        prefix="." + path.name + ".", suffix=".tmp", delete=False,
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def fetch(path: str) -> bytes:
    token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
    if not token:
        raise RuntimeError("PYTHONANYWHERE_TOKEN_MISSING")
    request = urllib.request.Request(
        BASE + urllib.parse.quote(path, safe="/"),
        headers={
            "Authorization": "Token " + token,
            "User-Agent": "ua-art-task068-source-shadow/1",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        value = response.read(MAX_BYTES + 1)
    if not value or len(value) > MAX_BYTES:
        raise RuntimeError("SOURCE_SIZE_INVALID:" + pathlib.PurePosixPath(path).name)
    return value


def main() -> int:
    result = {
        "contract_id": repair.CONTRACT,
        "status": "FAIL",
        "read_only": True,
        "production_write": False,
        "files": {},
        "protected": {},
        "errors": [],
        "llm_tokens": 0,
    }
    try:
        patchers = {
            repair.STRANICA_PATH: repair._patch_stranica,
            repair.YADRO_PATH: repair._patch_yadro,
            repair.MASTER_CARD_PATH: repair._patch_master_card,
        }
        observed = {}
        for path in patchers:
            raw = fetch(path)
            source = raw.decode("utf-8")
            name = pathlib.PurePosixPath(path).name
            observed[path] = (raw, source)
            result["files"][name] = {
                "sha256_before": sha(raw),
                "bytes_before": len(raw),
                "task068_marker_count": source.count(repair.FERRY_VIN_SOURCE_MARKER),
                "seo068_marker_count": source.count("# SEO-REHAB-GUARD-068-PRODUCTION-V1"),
                "task068_marker_position": source.find(repair.FERRY_VIN_SOURCE_MARKER),
                "seo068_marker_position": source.find("# SEO-REHAB-GUARD-068-PRODUCTION-V1"),
                "main_guard_position": source.rfind("if __name__"),
                "patch_evaluated": False,
            }

        for path, patcher in patchers.items():
            raw, source = observed[path]
            candidate = patcher(source, sha(raw))
            repair._validate_task068_source(candidate, path)
            guard = candidate.rfind("if __name__")
            marker = candidate.find(repair.FERRY_VIN_SOURCE_MARKER)
            if guard >= 0 and not marker < guard:
                raise RuntimeError("FILTER_ORDER_INVALID:" + pathlib.PurePosixPath(path).name)
            result["files"][pathlib.PurePosixPath(path).name].update({
                "sha256_after": sha(candidate.encode("utf-8")),
                "changed": candidate != source,
                "marker_before_main": guard < 0 or marker < guard,
                "seo_before_task068": (
                    candidate.find("# SEO-REHAB-GUARD-068-PRODUCTION-V1")
                    < candidate.find(repair.FERRY_VIN_SOURCE_MARKER)
                ),
                "patch_evaluated": True,
            })

        for path in (repair.CARS_UI_PATH, repair.DB_PATH,
                     repair.TEAM_BOT_PATH, repair.START_SAFE_PATH):
            raw = fetch(path)
            digest = sha(raw)
            name = pathlib.PurePosixPath(path).name
            result["protected"][name] = {
                "sha256_actual": digest,
                "sha256_expected": repair.EXPECTED_SHA[path],
                "matches_expected": digest == repair.EXPECTED_SHA[path],
            }
            if digest != repair.EXPECTED_SHA[path]:
                raise RuntimeError("PROTECTED_SOURCE_CHANGED:" + name)
            compile(raw.decode("utf-8"), path, "exec")
        repair._validate_cars_ui(fetch(repair.CARS_UI_PATH).decode("utf-8"))
        result["status"] = "PASS"
    except Exception as exc:
        result["errors"].append(type(exc).__name__ + ":" + str(exc))
    atomic_text(OUT, json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print("TASK068_SOURCE_SHADOW_%s" % result["status"])
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
