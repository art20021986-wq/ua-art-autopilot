#!/usr/bin/env python3
"""Collect and validate a fresh read-only PythonAnywhere capacity measurement."""
from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import sys


HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TASK068_CONTROLLER = ROOT / "cloud/task_068_ferry_vin/controller.py"
REMOTE_ROOT = "/home/Carix/autopilot_inbox/cloud/task_068_ferry_vin"
REMOTE_SCRIPT = REMOTE_ROOT + "/task109_storage_probe.py"
REMOTE_RECEIPT = REMOTE_ROOT + "/task109_storage_probe.json"
LOCAL_EVIDENCE = ROOT / "state/storage/TASK109-CONTAINER-TRACK-INLINE.json"


def api_quota_probe(api, module) -> dict:
    """Try the two account-scoped read-only quota resources, sanitizing output."""
    results = []
    for resource in ("files/quota/", "quota/"):
        item = {"resource": resource}
        try:
            status, body = api.request(
                "GET", module.BASE + resource,
                allowed=(200, 400, 401, 403, 404, 405),
            )
            item["http_status"] = int(status)
            if status == 200:
                parsed = json.loads(body.decode("utf-8"))
                if isinstance(parsed, dict):
                    item["quota_fields"] = {
                        str(key): value
                        for key, value in parsed.items()
                        if re.search(r"quota|storage|space|used|free|total|limit", str(key), re.I)
                        and isinstance(value, (str, int, float, bool, type(None)))
                    }
        except Exception as exc:
            item["error"] = type(exc).__name__ + ":" + str(exc)
        results.append(item)
    return {"read_only": True, "resources": results}


def load_api_module():
    spec = importlib.util.spec_from_file_location("task068_api_for_task109_probe", TASK068_CONTROLLER)
    if spec is None or spec.loader is None:
        raise RuntimeError("TASK068_API_SPEC")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate(value: dict) -> None:
    required = {"target_environment", "read_only", "measured_at", "total_bytes", "used_bytes", "free_bytes"}
    if not required.issubset(value):
        raise RuntimeError("PROBE_FIELDS")
    if value["target_environment"] != "production" or value["read_only"] is not True:
        raise RuntimeError("PROBE_SCOPE")
    total, used, free = (int(value[key]) for key in ("total_bytes", "used_bytes", "free_bytes"))
    if total <= 0 or min(used, free) < 0 or used > total or free > total:
        raise RuntimeError("PROBE_RANGE")
    if abs(total - used - free) > max(1024 * 1024, total // 100):
        raise RuntimeError("PROBE_INCONSISTENT")
    if free < 134217728:
        raise RuntimeError("PROBE_INSUFFICIENT_FREE_SPACE")


def main() -> int:
    module = load_api_module()
    api = module.API()
    payload = (HERE / "storage_probe_remote.py").read_bytes()
    compile(payload.decode("utf-8"), "storage_probe_remote.py", "exec")
    try:
        api.upload(REMOTE_SCRIPT, payload)
        if api.read(REMOTE_SCRIPT) != payload:
            raise RuntimeError("PROBE_UPLOAD_READBACK")
        command = "cd %s && python3.10 task109_storage_probe.py" % REMOTE_ROOT
        value = api.run_remote(command, "task109 read-only production storage probe", REMOTE_RECEIPT, seconds=300)
        value.setdefault("diagnostics", {})["pythonanywhere_api_quota"] = api_quota_probe(api, module)
        validate(value)
        LOCAL_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        module.atomic_text(LOCAL_EVIDENCE, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    finally:
        for path in (REMOTE_SCRIPT, REMOTE_RECEIPT):
            try:
                api.delete_file(path)
            except Exception:
                pass
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
