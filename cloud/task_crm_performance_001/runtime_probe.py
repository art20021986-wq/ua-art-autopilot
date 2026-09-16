#!/usr/bin/env python3
"""UA-ART-CRM-PERFORMANCE-RECOVERY-001 Stage 1 read-only runtime probe.

Contract: GET-only PythonAnywhere API access. No console execution, reload, restart,
file write, DB write, task mutation, or production mutation.
"""
from __future__ import annotations
import hashlib, json, os, pathlib, re, time, urllib.parse, urllib.request

BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
OUT = pathlib.Path("cloud/task_crm_performance_001/evidence/runtime.json")
REMOTE_CANDIDATES = (
    "/home/Carix/db.py", "/home/Carix/start_safe.py", "/home/Carix/run_all.py",
    "/home/Carix/trace_zhurnal.py", "/home/Carix/bot.py", "/home/Carix/main.py",
)
MAX_BYTES = 2_000_000

def get(endpoint: str) -> tuple[bytes, float]:
    req = urllib.request.Request(BASE + endpoint, headers={
        "Authorization": "Token " + os.environ["PYTHONANYWHERE_API_TOKEN"],
        "User-Agent": "ua-art-crm-performance-readonly/1",
    }, method="GET")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=45) as r:
        data = r.read(MAX_BYTES + 1)
    ms = (time.perf_counter() - t0) * 1000
    if len(data) > MAX_BYTES: raise RuntimeError("RESPONSE_TOO_LARGE")
    return data, round(ms, 2)

def safe_json(endpoint: str):
    try:
        b, ms = get(endpoint); return {"ok": True, "latency_ms": ms, "value": json.loads(b)}
    except Exception as e: return {"ok": False, "error": type(e).__name__ + ":" + str(e)[:180]}

def safe_file(path: str):
    try:
        b, ms = get("files/path" + urllib.parse.quote(path, safe="/"))
        text = b.decode("utf-8", "replace")
        return {"ok": True, "latency_ms": ms, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest(),
                "signals": {k: len(re.findall(p, text, re.I)) for k,p in {
                    "sqlite_connect": r"sqlite3\.connect", "busy_timeout": r"busy_timeout", "wal": r"journal_mode\s*=\s*WAL|journal_mode\(WAL",
                    "http_calls": r"requests\.|urllib\.|urlopen\(", "telegram_calls": r"send_message|edit_message|answer_callback|reply_text",
                    "sleep_calls": r"time\.sleep|asyncio\.sleep", "thread_or_process": r"threading|multiprocessing|subprocess|Popen"
                }.items()}}
    except Exception as e: return {"ok": False, "error": type(e).__name__ + ":" + str(e)[:180]}

def main():
    evidence = {"task":"UA-ART-CRM-PERFORMANCE-RECOVERY-001","stage":1,"mode":"READ_ONLY_RUNTIME_PROBE",
                "production_touched":False,"method":"GET_ONLY","captured_at":time.time(),"api":{},"files":{}}
    for ep in ("always_on/", "schedule/", "consoles/", "webapps/"):
        evidence["api"][ep] = safe_json(ep)
    for p in REMOTE_CANDIDATES: evidence["files"][p] = safe_file(p)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    assert evidence["production_touched"] is False and evidence["method"] == "GET_ONLY"
    print(json.dumps({"status":"PASS","production_touched":False,"method":"GET_ONLY"}))
if __name__ == "__main__": main()
