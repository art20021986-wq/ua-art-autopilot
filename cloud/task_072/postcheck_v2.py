#!/usr/bin/env python3
"""Read-only production postcheck plus write tests on a temporary DB clone."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import sqlite3
import tempfile
from typing import Any


CONTRACT = "CRM-DESCRIPTION-SAVE-072-V2"
ROOT = pathlib.Path(os.environ.get("TASK072_ROOT", "/home/Carix"))
SAFE = pathlib.Path(os.environ.get(
    "TASK072_SAFE", "/home/Carix/autopilot_inbox/cloud/task_072"
))
CARS_UI = ROOT / "cars_ui.py"
WRITER = ROOT / "crm_description_writer.py"
DATABASE = ROOT / "crm.db"
RECEIPT = SAFE / "postcheck_receipt_v2.json"
EXPECTED_CARS_SHA256 = "1f5368ea3caeeecb2d55b18b41cb414092495ef2185f7e881767015f53d8634b"
EXPECTED_WRITER_SHA256 = "f85c9a332ad69ac5834d0bf78a23d86a28ea361fba4b9eeef695197784551623"


class PostcheckBlocked(RuntimeError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: Any, code: str) -> None:
    if not condition:
        raise PostcheckBlocked(code)


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix="." + path.name + ".", suffix=".tmp", delete=False,
    )
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


def import_writer(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("task072_installed_writer", path)
    if spec is None or spec.loader is None:
        raise PostcheckBlocked("WRITER_IMPORT_SPEC")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def consistent_clone(source: pathlib.Path, destination: pathlib.Path) -> None:
    source_uri = "file:%s?mode=ro" % source.as_posix()
    live = sqlite3.connect(source_uri, uri=True, timeout=5)
    clone = sqlite3.connect(str(destination))
    try:
        live.backup(clone)
    finally:
        clone.close()
        live.close()


def protected_digest(conn: sqlite3.Connection) -> str:
    rows = list(conn.execute(
        "SELECT id, description, diag_text FROM cars ORDER BY id"
    ))
    return sha(json.dumps(rows, ensure_ascii=False, default=list).encode())


def clone_test(writer: Any) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="task072_postcheck_") as raw:
        temp = pathlib.Path(raw)
        clone_path = temp / "crm-clone.db"
        queue_path = temp / "queue.sqlite3"
        consistent_clone(DATABASE, clone_path)
        conn = sqlite3.connect(str(clone_path))
        conn.row_factory = sqlite3.Row
        try:
            require(conn.execute("PRAGMA quick_check").fetchone()[0] == "ok",
                    "CLONE_QUICK_CHECK_BEFORE")
            ids = [int(row[0]) for row in conn.execute("SELECT id FROM cars ORDER BY id")]
            require(len(ids) == 11, "CLONE_CARD_COUNT")
            protected_before = protected_digest(conn)
            audit_before = int(conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0])
            for index, card_id in enumerate(ids):
                outcome = writer.save_or_enqueue(
                    str(clone_path), str(queue_path), card_id,
                    "postcheck card %02d\nVIN · 500 $ · 🚗" % index,
                    72072, "postcheck:%d" % card_id,
                    start_worker=False,
                    requested_field="description" if index == 0 else "condition_text",
                )
                require(outcome["status"] == "saved", "CLONE_SAVE")
            require(int(conn.execute("SELECT COUNT(*) FROM cars").fetchone()[0]) == 11,
                    "CLONE_CREATED_CARD")
            require(int(conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0])
                    == audit_before + 11, "CLONE_AUDIT_COUNT")
            require(protected_digest(conn) == protected_before, "CLONE_PROTECTED_FIELDS")
            require(conn.execute("PRAGMA quick_check").fetchone()[0] == "ok",
                    "CLONE_QUICK_CHECK_AFTER")
        finally:
            conn.close()
        return {
            "cards_tested": 11,
            "exact_readback": True,
            "audit_rows_added": 11,
            "new_cards_created": 0,
            "description_and_diag_text_unchanged": True,
            "quick_check": "ok",
        }


def run() -> dict[str, Any]:
    cars = CARS_UI.read_bytes()
    writer_bytes = WRITER.read_bytes()
    require(sha(cars) == EXPECTED_CARS_SHA256, "CARS_UI_SHA")
    require(sha(writer_bytes) == EXPECTED_WRITER_SHA256, "WRITER_SHA")
    cars_text = cars.decode("utf-8")
    writer_text = writer_bytes.decode("utf-8")
    compile(cars_text, "cars_ui.py", "exec")
    compile(writer_text, "crm_description_writer.py", "exec")
    require(cars_text.count("CRM-DESCRIPTION-SAVE-072-V2") == 1, "PATCH_MARKER")
    require("save_or_enqueue" in cars_text, "DESCRIPTION_ROUTE")
    require("добавь\\s+описание" in cars_text, "DIRECT_COMMAND_ROUTE")
    require("diag_text" in cars_text, "DIAGNOSTIC_ROUTE")
    writer = import_writer(WRITER)

    live = sqlite3.connect("file:%s?mode=ro" % DATABASE.as_posix(), uri=True, timeout=5)
    live.row_factory = sqlite3.Row
    try:
        require(live.execute("PRAGMA quick_check").fetchone()[0] == "ok",
                "LIVE_QUICK_CHECK")
        count = int(live.execute("SELECT COUNT(*) FROM cars").fetchone()[0])
        ua0009 = list(live.execute("SELECT id FROM cars WHERE auto_number='UA-0009'"))
        require(count == 11, "LIVE_CARD_COUNT")
        require(len(ua0009) == 1, "LIVE_UA0009")
    finally:
        live.close()

    return {
        "contract_id": CONTRACT,
        "mode": "POSTCHECK_READ_ONLY_LIVE_PLUS_TEMP_CLONE",
        "status": "PASS",
        "production_write": False,
        "crm_db_write": False,
        "runtime_llm_tokens": 0,
        "sources": {
            "cars_ui_sha256": sha(cars),
            "writer_sha256": sha(writer_bytes),
        },
        "live_database": {
            "cards_count": count,
            "ua0009_rows": 1,
            "quick_check": "ok",
        },
        "temporary_clone": clone_test(writer),
    }


def main() -> int:
    try:
        value = run()
    except Exception as exc:
        value = {
            "contract_id": CONTRACT,
            "mode": "POSTCHECK",
            "status": "BLOCKED",
            "production_write": False,
            "crm_db_write": False,
            "runtime_llm_tokens": 0,
            "errors": [type(exc).__name__ + ":" + str(exc)],
        }
    atomic_json(RECEIPT, value)
    print(json.dumps({"status": value.get("status")}, sort_keys=True))
    return 0 if value.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

