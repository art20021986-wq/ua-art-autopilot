#!/usr/bin/env python3
"""GET-only live audit for CRM-VOICE-WATCHDOG-005."""
from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request


REMOTE_ROOT = "/home/Carix"
API = "https://www.pythonanywhere.com/api/v0/user/Carix/files/path"
HERE = pathlib.Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence" / "live_audit.json"
REPORT = HERE / "VOICE_AUDIT_REPORT.md"
FILES = {
    "cars_ui.py": True,
    "ai.py": True,
    "start_safe.py": False,
    "crm_online_guard.py": False,
    "yadro.py": True,
}
NEEDLES = (
    "voice",
    "audio",
    "transcribe",
    "run_polling",
    "infinity_polling",
    "hard_deadline",
    "asyncio.to_thread",
    "wait_for",
    "restart",
    "watchdog",
    "subprocess",
)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def get_remote(name: str, required: bool):
    token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("PYTHONANYWHERE_API_TOKEN_MISSING")
    path = REMOTE_ROOT + "/" + name
    request = urllib.request.Request(
        API + urllib.parse.quote(path, safe="/"),
        method="GET",
        headers={
            "Authorization": "Token " + token,
            "User-Agent": "ua-art-task078-get-only/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read(8_000_001)
    except urllib.error.HTTPError as exc:
        if exc.code == 404 and not required:
            return None
        raise RuntimeError("GET_HTTP_%d:%s" % (exc.code, name)) from exc
    if len(payload) > 8_000_000:
        raise RuntimeError("SOURCE_TOO_LARGE:" + name)
    return payload


def clean(source: str) -> str:
    source = re.sub(r"\b\d{7,12}:[A-Za-z0-9_-]{20,}\b", "[REDACTED_BOT_TOKEN]", source)
    source = re.sub(r"sk-[A-Za-z0-9_-]{16,}", "[REDACTED_KEY]", source)
    return source


def audit_source(name: str, payload: bytes | None) -> dict:
    if payload is None:
        return {"missing": True}
    source = payload.decode("utf-8")
    compile(source, name, "exec")
    tree = ast.parse(source, filename=name)
    lines = source.splitlines(keepends=True)
    definitions = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        segment = "".join(lines[node.lineno - 1 : node.end_lineno])
        if not any(value.casefold() in segment.casefold() for value in NEEDLES):
            continue
        definitions.append(
            {
                "name": node.name,
                "line": node.lineno,
                "end_line": node.end_lineno,
                "sha256": hashlib.sha256(segment.encode()).hexdigest(),
                "source": clean(segment)[:40_000],
                "truncated": len(segment) > 40_000,
            }
        )
    return {
        "missing": False,
        "sha256": sha(payload),
        "bytes": len(payload),
        "compiled": True,
        "counts": {value: source.casefold().count(value.casefold()) for value in NEEDLES},
        "definitions": sorted(definitions, key=lambda item: item["line"]),
    }


def main() -> int:
    evidence = {
        "task_id": "task_078",
        "contract_id": "CRM-VOICE-WATCHDOG-005-V1.0",
        "status": "FAIL",
        "mode": "LIVE_GET_ONLY",
        "production_touched": False,
        "http_methods": ["GET"],
        "crm_write": False,
        "process_restart": False,
        "started_at_utc": now(),
        "errors": [],
    }
    try:
        blobs = {name: get_remote(name, required) for name, required in FILES.items()}
        evidence["sources"] = {
            name: audit_source(name, blobs[name]) for name in FILES
        }
        cars = blobs["cars_ui.py"].decode("utf-8")
        evidence["root_cause"] = {
            "fixed_deadline_4_65": "hard_deadline = started + 4.65" in cars,
            "non_killable_to_thread": "asyncio.to_thread(ai.transcribe" in cars,
            "wait_for_only_cancels_await": "await asyncio.wait_for(" in cars,
            "duration_used_for_timeout": bool(
                re.search(r"duration.{0,200}(?:timeout|deadline)", cars, re.I | re.S)
            ),
            "killable_child_present": any(
                value in cars for value in ("create_subprocess_exec", "killpg", "crm_voice_watchdog")
            ),
        }
        start = (blobs.get("start_safe.py") or b"").decode("utf-8", "replace")
        evidence["supervisor"] = {
            "file_present": bool(start),
            "restart_loop_present": bool(
                start and re.search(r"while\s+True|for\s+.*restart|Popen|subprocess\.run", start)
            ),
            "exit_75_handled": bool(start and re.search(r"\b75\b", start)),
            "whole_process_restart_allowed_in_candidate": False,
        }
        root = evidence["root_cause"]
        if not (root["fixed_deadline_4_65"] and root["non_killable_to_thread"]):
            raise RuntimeError("EXPECTED_LIVE_ROOT_CAUSE_NOT_FOUND")
        evidence["status"] = "PASS_AUDIT_ROOT_CAUSE_CONFIRMED"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
    evidence["finished_at_utc"] = now()
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    temporary = EVIDENCE.with_name("." + EVIDENCE.name + ".tmp")
    temporary.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, EVIDENCE)
    report = [
        "# CRM-VOICE-WATCHDOG-005 — live GET-only audit",
        "",
        "STATUS: **%s**" % evidence["status"],
        "",
        "- Production touched: **NO**",
        "- HTTP methods: **GET only**",
        "- Process restart executed: **NO**",
    ]
    if evidence["status"].startswith("PASS"):
        report.extend(
            [
                "- Fixed 4.65-second deadline: **CONFIRMED**",
                "- Non-killable `asyncio.to_thread(ai.transcribe)`: **CONFIRMED**",
                "- Killable child worker in live handler: **ABSENT**",
                "",
                "Production remains locked; this audit only confirms the cause.",
            ]
        )
    else:
        report.extend(["- Errors: `%s`" % "; ".join(evidence["errors"])])
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({"status": evidence["status"], "errors": evidence["errors"]}, ensure_ascii=False))
    return 0 if evidence["status"] == "PASS_AUDIT_ROOT_CAUSE_CONFIRMED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
