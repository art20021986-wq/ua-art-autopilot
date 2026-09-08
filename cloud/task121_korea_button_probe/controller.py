#!/usr/bin/env python3
"""Read-only live probe that computes exact candidate hashes for the Korea button."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping

import patcher


ROOT = pathlib.Path(__file__).resolve().parents[2]
TASK_ID = "TASK121-KOREA-BUTTON-PROBE"
RECEIPT_REL = "state/receipts/%s.json" % TASK_ID
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/files/path"
TARGETS = {
    "cars_ui.py": {
        "path": "/home/Carix/cars_ui.py",
        "expected": "2b1ef0bcfa700b7c87ccfb164b69b8ca173d460481936225e41344096c92062f",
        "patch": patcher.patch_cars_ui,
    },
    "konteyner.py": {
        "path": "/home/Carix/konteyner.py",
        "expected": "72c03a1b8ab14279b2a2adbc681e112594d88c766d2aae7cc40e08b8aa004230",
        "patch": patcher.patch_konteyner,
    },
    "cars_schema.py": {
        "path": "/home/Carix/cars_schema.py",
        "expected": "87f20a57248c3483ccb09955431cd840bb57bfdef6d2705e5fc048c201e14496",
        "patch": patcher.patch_schema,
    },
}
MAX_BYTES = 4 * 1024 * 1024


class ProbeError(RuntimeError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def safe_rel(value: str) -> str:
    path = pathlib.PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ProbeError("UNSAFE_PATH")
    return path.as_posix()


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False)
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def required(environment: Mapping[str, str]) -> dict[str, str]:
    names = (
        "PYTHONANYWHERE_API_TOKEN", "UAART_REQUEST_PATH", "UAART_REQUEST_SHA256",
        "UAART_TASK_ID", "UAART_TASK_CLASS", "UAART_RUN_ID", "UAART_RECEIPT_PATH",
    )
    values = {name: str(environment.get(name, "")).strip() for name in names}
    missing = [name for name in names if not values[name]]
    if missing:
        raise ProbeError("MISSING_ENV:" + ",".join(missing))
    if values["UAART_TASK_ID"] != TASK_ID or values["UAART_TASK_CLASS"].upper() != "STANDARD":
        raise ProbeError("TASK_IDENTITY")
    if safe_rel(values["UAART_RECEIPT_PATH"]) != RECEIPT_REL:
        raise ProbeError("RECEIPT_IDENTITY")
    request = ROOT / safe_rel(values["UAART_REQUEST_PATH"])
    if sha(request.read_bytes()) != values["UAART_REQUEST_SHA256"]:
        raise ProbeError("REQUEST_SHA")
    return values


def read_remote(token: str, path: str) -> bytes:
    quoted = urllib.parse.quote(path, safe="/")
    request = urllib.request.Request(
        BASE + quoted,
        headers={"Authorization": "Token " + token, "Accept": "application/octet-stream"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            value = response.read(MAX_BYTES + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise ProbeError("REMOTE_READ:" + type(exc).__name__) from exc
    if not value or len(value) > MAX_BYTES:
        raise ProbeError("REMOTE_SIZE")
    return value


def execute(environment: Mapping[str, str]) -> dict[str, Any]:
    values = required(environment)
    before: dict[str, bytes] = {}
    after: dict[str, bytes] = {}
    files: dict[str, Any] = {}
    for name, spec in TARGETS.items():
        payload = read_remote(values["PYTHONANYWHERE_API_TOKEN"], str(spec["path"]))
        before_sha = sha(payload)
        if before_sha != spec["expected"]:
            raise ProbeError("LIVE_PREIMAGE_MISMATCH:" + name)
        source = payload.decode("utf-8")
        candidate = spec["patch"](source).encode("utf-8")
        before[name] = payload
        after[name] = candidate
        files[name] = {
            "production_path": spec["path"],
            "before_sha256": before_sha,
            "after_sha256": sha(candidate),
            "before_bytes": len(payload),
            "after_bytes": len(candidate),
        }
    proof = patcher.verify(
        after["cars_ui.py"].decode("utf-8"),
        after["konteyner.py"].decode("utf-8"),
        after["cars_schema.py"].decode("utf-8"),
    )
    receipt = {
        "task_id": TASK_ID,
        "status": "FINISHED",
        "task_class": "STANDARD",
        "target_environment": "production_read_only",
        "tests": "PASS",
        "unexpected_changes": 0,
        "production_required": False,
        "read_only": True,
        "production_touched": False,
        "site_touched": False,
        "crm_vehicle_data_touched": False,
        "media_touched": False,
        "request_sha256": values["UAART_REQUEST_SHA256"],
        "run_id": values["UAART_RUN_ID"],
        "files": files,
        "proof": proof,
        "finished_at": now(),
    }
    atomic_json(ROOT / RECEIPT_REL, receipt)
    return receipt


def main() -> int:
    try:
        value = execute(os.environ)
    except Exception as exc:
        value = {
            "task_id": TASK_ID,
            "status": "FAILED",
            "task_class": "STANDARD",
            "production_required": False,
            "production_touched": False,
            "unexpected_changes": 0,
            "error": type(exc).__name__ + ":" + str(exc),
            "finished_at": now(),
        }
        atomic_json(ROOT / RECEIPT_REL, value)
        print(json.dumps(value, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
