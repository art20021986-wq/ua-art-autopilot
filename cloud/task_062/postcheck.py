#!/usr/bin/env python3
"""Read-only post-restart verification for CRM-VOICE-FILL-001."""
from __future__ import annotations

import hashlib
import json
import pathlib
import sqlite3


BASE = pathlib.Path("/home/Carix")
SAFE = BASE / "autopilot_inbox" / "cloud" / "task_062"
INSTALL = SAFE / "install_receipt.json"
OUT = SAFE / "postcheck.json"


def sha_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def site_hashes():
    result = {}
    for root in (BASE / "video", BASE / "site"):
        for name in ("index.html", "katalog.html") + tuple("UA-%04d.html" % n for n in range(1, 11)):
            path = root / name
            if path.exists() and path.is_file() and not path.is_symlink():
                result[str(path)] = sha_file(path)
    return result


def db_state():
    connection = sqlite3.connect("file:/home/Carix/crm.db?mode=ro", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        quick = connection.execute("PRAGMA quick_check").fetchone()[0]
        count = connection.execute("SELECT count(*) FROM cars").fetchone()[0]
        rows = connection.execute(
            "SELECT * FROM cars WHERE auto_number IN ('UA-0009','UA0009')"
        ).fetchall()
        row_hash = hashlib.sha256(
            json.dumps([dict(row) for row in rows], ensure_ascii=False,
                       sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return {"quick_check": quick, "cars_count": count,
                "ua0009_rows": len(rows), "ua0009_state_sha256": row_hash}
    finally:
        connection.close()


def main():
    install = json.loads(INSTALL.read_text(encoding="utf-8"))
    current = db_state()
    files = install.get("files") or {}
    code_ok = all(
        pathlib.Path(path).is_file() and sha_file(pathlib.Path(path)) == metadata.get("after")
        for path, metadata in files.items()
    )
    result = {
        "task_id": "task_062", "contract_id": "CRM-VOICE-FILL-001",
        "status": "BLOCKED", "mode": "READ_ONLY_POST_RESTART",
        "production_write": False, "crm_db_write": False, "site_write": False,
        "code_readback": code_ok,
        "db_quick_check": current.get("quick_check"),
        "db_hash_unchanged": sha_file(BASE / "crm.db") == install.get("crm_db_sha256_after"),
        "site_unchanged": digest(site_hashes()) == install.get("site_state_sha256_after"),
        "card_count_unchanged": current.get("cars_count") == (
            install.get("readonly_after") or {}).get("cars_count"),
        "ua0009_unchanged": current.get("ua0009_state_sha256") == (
            install.get("readonly_after") or {}).get("ua0009_state_sha256"),
        "ua0009_rows": current.get("ua0009_rows"),
    }
    checks = (
        result["code_readback"], result["db_quick_check"] == "ok",
        result["db_hash_unchanged"], result["site_unchanged"],
        result["card_count_unchanged"], result["ua0009_unchanged"],
    )
    result["status"] = "PASS" if all(checks) else "BLOCKED"
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(json.dumps({"status": result["status"], "production_write": False}))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
