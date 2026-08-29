#!/usr/bin/env python3
"""Fail-closed PythonAnywhere installer and publisher for TASK 083."""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import fcntl
import hashlib
import importlib
import json
import os
import pathlib
import shutil
import sqlite3
import sys
import tempfile
import traceback
import uuid
from typing import Any


CONTRACT_ID = "UA-0012-UA-0013-PUBLISH-TRANSACTION-001-V1.0"
ROOT = pathlib.Path("/home/Carix")
REMOTE = ROOT / "autopilot_inbox/cloud/task_083_publish_transaction"
BACKUPS = REMOTE / "backups"
LAST_BACKUP = REMOTE / "last_successful_install.json"
LOCK = ROOT / ".task083_publish_install.lock"
PUBLISHER = ROOT / "publikaciya.py"
CARS_UI = ROOT / "cars_ui.py"
MASTER_CARD = ROOT / "master_card.py"
DB = ROOT / "crm.db"
TARGETS = ("UA-0012", "UA-0013")
INBOX = {
    ROOT / "publish_transaction_guard.py": REMOTE / "publish_transaction_guard.py",
    ROOT / "catalog_stage_guard_core.py": REMOTE / "catalog_stage_guard_core.py",
}
MANAGED_CODE = (PUBLISHER, CARS_UI, MASTER_CARD, *INBOX.keys())
RECEIPTS = {
    "install": REMOTE / "install_receipt.json",
    "postcheck": REMOTE / "postcheck_receipt.json",
    "rollback": REMOTE / "rollback_receipt.json",
}
PUB_START = "# UA-0012-UA-0013-PUBLISH-TRANSACTION-001-V1.0:PUBLISHER:START"
PUB_END = "# UA-0012-UA-0013-PUBLISH-TRANSACTION-001-V1.0:PUBLISHER:END"
UI_START = "# UA-0012-UA-0013-PUBLISH-TRANSACTION-001-V1.0:UI:START"
UI_END = "# UA-0012-UA-0013-PUBLISH-TRANSACTION-001-V1.0:UI:END"
MASTER_START = "# UA-0012-UA-0013-PUBLISH-TRANSACTION-001-V1.0:MASTER_CARD:START"
MASTER_END = "# UA-0012-UA-0013-PUBLISH-TRANSACTION-001-V1.0:MASTER_CARD:END"
DIAG_LEGACY = "Открыть комплексную диагностику"
DIAG_CONTRACT = "Открыть: Комплексная диагностика"
MAX_FILE = 40 * 1024 * 1024


class InstallError(RuntimeError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(path: pathlib.Path) -> bytes:
    data = path.read_bytes()
    if len(data) > MAX_FILE:
        raise InstallError("FILE_TOO_LARGE:" + str(path))
    return data


def atomic(path: pathlib.Path, data: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        dir=path.parent, prefix="." + path.name + ".", suffix=".task083.tmp", delete=False
    )
    temp = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    atomic(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())


def strip_marker(source: str, start: str, end: str) -> str:
    import re

    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end) + r"\s*", re.S)
    return pattern.sub("", source)


def publisher_wrapper() -> str:
    return r'''
# UA-0012-UA-0013-PUBLISH-TRANSACTION-001-V1.0:PUBLISHER:START
_UA083_BASE_PUBLISH = _UA9_BASE_PUBLISH

def opublikovat(kod, proba=False):
    from publish_transaction_guard import publish_one as _ua083_publish_one
    return _ua083_publish_one(_UA083_BASE_PUBLISH, kod, proba=proba)

def obnovit_katalog():
    from publish_transaction_guard import rebuild_catalog as _ua083_rebuild_catalog
    return _ua083_rebuild_catalog()
# UA-0012-UA-0013-PUBLISH-TRANSACTION-001-V1.0:PUBLISHER:END
'''


def ui_wrapper() -> str:
    return r'''
# UA-0012-UA-0013-PUBLISH-TRANSACTION-001-V1.0:UI:START
def _ua083_publish_preimage(card):
    return {name: card.get(name) for name in ("published", "status", "publish_pending")}


def _ua083_restore_publish_preimage(cid, preimage, actor_id):
    try:
        for field in ("published", "status", "publish_pending"):
            current = card_of(cid) or {}
            if current.get(field) != preimage.get(field):
                db.update_card_field("cars", int(cid), field, preimage.get(field), actor_id)
        final = card_of(cid) or {}
        return all(final.get(field) == preimage.get(field)
                   for field in ("published", "status", "publish_pending"))
    except Exception as exc:
        log.error("TASK083: не удалось восстановить preimage %s: %s", cid, exc)
        return False


async def toggle_publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await _v168_ack(q,)
    cid = int(q.data.split(":")[-1])
    card = card_of(cid)
    actor_id = q.from_user.id
    preimage = _ua083_publish_preimage(card)
    novoe = 0 if card.get("published") else 1
    back = InlineKeyboardMarkup([[InlineKeyboardButton(
        "← Вернуться к карточке", callback_data="car_open:%d" % cid)]])

    if novoe:
        miss = S.missing_required(card)
        if miss:
            await q.message.reply_text(
                "Для показа клиентам не хватает: %s" % ", ".join(miss),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Дозаполнить", callback_data="car_edit:%d" % cid)],
                    [InlineKeyboardButton("← Вернуться к карточке",
                                          callback_data="car_open:%d" % cid)]]))
            raise ApplicationHandlerStop

    try:
        import asyncio as _ua083_asyncio
        import publikaciya as _ua083_publisher

        db.update_card_field("cars", cid, "published", novoe, actor_id)
        if novoe:
            ok, detail = await _ua083_asyncio.to_thread(
                _ua083_publisher.opublikovat, card.get("auto_number"))
            success_text = "Машина видна клиентам в каталоге."
        else:
            ok, detail = await _ua083_asyncio.to_thread(_ua083_publisher.obnovit_katalog)
            success_text = "Машина скрыта от клиентов."
        if ok is not True:
            restored = _ua083_restore_publish_preimage(cid, preimage, actor_id)
            text = str(detail or "Публикация не прошла проверку.")
            if not restored:
                text += " КРИТИЧНО: состояние CRM не удалось восстановить автоматически."
            await q.message.reply_text(text, reply_markup=back)
            raise ApplicationHandlerStop
        await q.message.reply_text(success_text, reply_markup=back)
        raise ApplicationHandlerStop
    except ApplicationHandlerStop:
        raise
    except Exception as exc:
        restored = _ua083_restore_publish_preimage(cid, preimage, actor_id)
        log.exception("TASK083 publication exception for car %s", cid)
        text = "Публикация отменена: %s. Выполнен откат." % exc
        if not restored:
            text += " КРИТИЧНО: состояние CRM не удалось восстановить автоматически."
        await q.message.reply_text(text, reply_markup=back)
        raise ApplicationHandlerStop
# UA-0012-UA-0013-PUBLISH-TRANSACTION-001-V1.0:UI:END
'''


def patch_publisher(source: str) -> str:
    base = strip_marker(source, PUB_START, PUB_END).rstrip() + "\n"
    tree = ast.parse(base)
    functions = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    assignments = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments.add(target.id)
    if "_UA9_BASE_PUBLISH" not in assignments:
        raise InstallError("PUBLISHER_BASE_ANCHOR_MISSING")
    if functions.count("_ua9_sobrat_katalog") != 1 or functions.count("opublikovat") < 1:
        raise InstallError("PUBLISHER_STRUCTURE_UNEXPECTED")
    candidate = base + publisher_wrapper().lstrip()
    compile(candidate, str(PUBLISHER), "exec")
    if candidate.count(PUB_START) != 1 or candidate.count(PUB_END) != 1:
        raise InstallError("PUBLISHER_MARKER_COUNT")
    return candidate


def patch_cars_ui(source: str) -> str:
    base = strip_marker(source, UI_START, UI_END).rstrip() + "\n"
    tree = ast.parse(base)
    toggles = [
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "toggle_publish"
    ]
    registers = [
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "register"
    ]
    if not toggles or len(registers) != 1:
        raise InstallError("CARS_UI_STRUCTURE_UNEXPECTED")
    register_source = ast.get_source_segment(base, registers[0]) or ""
    if "toggle_publish" not in register_source or "car_pub:" not in register_source:
        raise InstallError("CARS_UI_HANDLER_ANCHOR_MISSING")
    candidate = base + ui_wrapper().lstrip()
    compile(candidate, str(CARS_UI), "exec")
    if candidate.count(UI_START) != 1 or candidate.count(UI_END) != 1:
        raise InstallError("CARS_UI_MARKER_COUNT")
    return candidate


def patch_master_card(source: str) -> str:
    """Keep the generator compatible with its own case-sensitive validator."""
    base = strip_marker(source, MASTER_START, MASTER_END).rstrip() + "\n"
    anchors = base.count(DIAG_LEGACY) + base.count(DIAG_CONTRACT)
    if anchors < 1:
        raise InstallError("MASTER_DIAGNOSTICS_TEXT_ANCHOR_MISSING")
    base = base.replace(DIAG_LEGACY, DIAG_CONTRACT)
    candidate = base + "\n%s\n%s\n" % (MASTER_START, MASTER_END)
    compile(candidate, str(MASTER_CARD), "exec")
    if candidate.count(MASTER_START) != 1 or candidate.count(MASTER_END) != 1:
        raise InstallError("MASTER_MARKER_COUNT")
    if DIAG_LEGACY in candidate or candidate.count(DIAG_CONTRACT) != anchors:
        raise InstallError("MASTER_DIAGNOSTICS_TEXT_READBACK")
    return candidate


def db_state() -> dict[str, Any]:
    connection = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        rows = [dict(row) for row in connection.execute(
            "SELECT * FROM cars WHERE published=1 ORDER BY auto_number, id"
        ).fetchall()]
        targets = {str(row["auto_number"]): dict(row) for row in connection.execute(
            "SELECT * FROM cars WHERE auto_number IN (?,?) ORDER BY auto_number", TARGETS
        ).fetchall()}
    finally:
        connection.close()
    if quick != "ok":
        raise InstallError("CRM_QUICK_CHECK:" + quick)
    normalized = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode()
    evidence = {}
    for code in TARGETS:
        row = targets.get(code)
        if not row:
            raise InstallError("TARGET_DB_ROW_MISSING:" + code)
        status = str(row.get("status") or "")
        stage = 2 if status.startswith("sea_") else 0
        if row.get("published") != 1 or stage != 2:
            raise InstallError("TARGET_DB_STATE_CHANGED:%s:%s:%s" % (
                code, row.get("published"), status))
        if not row.get("photos") or not row.get("vin") or not row.get("price_uah"):
            raise InstallError("TARGET_REQUIRED_DATA_MISSING:" + code)
        evidence[code] = {
            "id": row.get("id"), "published": 1, "status": status, "stage": 2,
            "category": "more", "review_status": row.get("review_status"),
            "publish_pending": row.get("publish_pending"),
        }
    return {"quick_check": quick, "published_rows": len(rows), "sha256": sha(normalized),
            "targets": evidence}


def create_backup() -> pathlib.Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = BACKUPS / (stamp + "-" + uuid.uuid4().hex[:12])
    manifest: dict[str, Any] = {}
    for path in (*MANAGED_CODE, DB):
        exists = path.is_file()
        item: dict[str, Any] = {"path": str(path), "exists": exists,
                               "restore": path in MANAGED_CODE}
        if exists:
            data = read(path)
            target = root / "files" / path.relative_to(ROOT)
            atomic(target, data, path.stat().st_mode & 0o777)
            item.update({"sha256": sha(data), "mode": path.stat().st_mode & 0o777})
        manifest[str(path)] = item
    atomic_json(root / "manifest.json", manifest)
    return root


def restore_code(backup_root: pathlib.Path) -> dict[str, Any]:
    backup_root = backup_root.resolve()
    if backup_root == BACKUPS or BACKUPS not in backup_root.parents:
        raise InstallError("BACKUP_PATH_INVALID")
    manifest = json.loads((backup_root / "manifest.json").read_text(encoding="utf-8"))
    changed = []
    for path in MANAGED_CODE:
        item = manifest.get(str(path))
        if not item or not item.get("restore"):
            raise InstallError("BACKUP_ENTRY_MISSING:" + str(path))
        if item.get("exists"):
            data = read(backup_root / "files" / path.relative_to(ROOT))
            if not path.is_file() or read(path) != data:
                atomic(path, data, int(item.get("mode") or 0o644))
                changed.append(str(path))
        elif path.exists():
            path.unlink()
            changed.append(str(path))
    return {"backup_root": str(backup_root), "changed_paths": changed}


def import_fresh():
    sys.path.insert(0, str(ROOT))
    for name in (
        "publish_transaction_guard", "catalog_stage_guard_core",
        "publikaciya", "stranica", "master_card", "yadro",
    ):
        sys.modules.pop(name, None)
    importlib.invalidate_caches()
    publisher = importlib.import_module("publikaciya")
    guard = importlib.import_module("publish_transaction_guard")
    return publisher, guard


def install_code() -> tuple[pathlib.Path, dict[str, str]]:
    candidates = {
        PUBLISHER: patch_publisher(PUBLISHER.read_text(encoding="utf-8")),
        CARS_UI: patch_cars_ui(CARS_UI.read_text(encoding="utf-8")),
        MASTER_CARD: patch_master_card(MASTER_CARD.read_text(encoding="utf-8")),
    }
    for destination, source in INBOX.items():
        data = read(source)
        compile(data.decode("utf-8"), destination.name, "exec")
    backup = create_backup()
    try:
        for destination, source in INBOX.items():
            data = read(source)
            if not destination.is_file() or read(destination) != data:
                atomic(destination, data, destination.stat().st_mode & 0o777 if destination.exists() else 0o644)
        for path, source in candidates.items():
            data = source.encode()
            if read(path) != data:
                atomic(path, data, path.stat().st_mode & 0o777)
        for path in MANAGED_CODE:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        if PUBLISHER.read_text(encoding="utf-8").count(PUB_START) != 1:
            raise InstallError("PUBLISHER_INSTALL_READBACK")
        if CARS_UI.read_text(encoding="utf-8").count(UI_START) != 1:
            raise InstallError("CARS_UI_INSTALL_READBACK")
        if MASTER_CARD.read_text(encoding="utf-8").count(MASTER_START) != 1:
            raise InstallError("MASTER_CARD_INSTALL_READBACK")
        return backup, {str(path): sha(read(path)) for path in MANAGED_CODE}
    except Exception:
        restore_code(backup)
        raise


def run_install() -> dict[str, Any]:
    before = db_state()
    backup, code_hashes = install_code()
    transaction = None
    try:
        publisher, guard = import_fresh()
        if not hasattr(publisher, "_UA083_BASE_PUBLISH"):
            raise InstallError("ACTIVE_PUBLISH_WRAPPER_MISSING")
        ok, message, transaction = guard.publish_batch(
            publisher._UA083_BASE_PUBLISH, TARGETS, proba=False
        )
        if ok is not True:
            raise InstallError("BATCH_PUBLICATION_FAILED:" + message)
        after = db_state()
        if before["sha256"] != after["sha256"]:
            raise InstallError("CRM_ROWS_CHANGED")
        verification = guard.verify_bundle(TARGETS)
        pointer = {
            "contract_id": CONTRACT_ID,
            "code_backup": str(backup),
            "transaction_backup": transaction.get("backup_root"),
            "codes": list(TARGETS),
        }
        atomic_json(LAST_BACKUP, pointer)
        return {
            "contract_id": CONTRACT_ID, "status": "PASS", "mode": "INSTALL",
            "production_write": True, "crm_write": False, "runtime_llm_tokens": 0,
            "code_backup": str(backup), "transaction_backup": transaction.get("backup_root"),
            "code_sha256": code_hashes, "db_before": before, "db_after": after,
            "transaction": transaction, "verification": verification,
            "rollback": None,
        }
    except Exception:
        rollback: dict[str, Any] = {}
        if transaction and transaction.get("backup_root"):
            try:
                _, guard = import_fresh()
                rollback["transaction"] = guard.rollback_backup(
                    transaction["backup_root"], TARGETS
                )
            except Exception as exc:
                rollback["transaction_error"] = type(exc).__name__ + ":" + str(exc)
        rollback["code"] = restore_code(backup)
        raise InstallError("INSTALL_ROLLED_BACK:" + json.dumps(rollback, ensure_ascii=False))


def run_postcheck() -> dict[str, Any]:
    state = db_state()
    publisher, guard = import_fresh()
    if not hasattr(publisher, "_UA083_BASE_PUBLISH"):
        raise InstallError("ACTIVE_PUBLISH_WRAPPER_MISSING")
    verification = guard.verify_bundle(TARGETS)
    return {
        "contract_id": CONTRACT_ID, "status": "PASS", "mode": "POSTCHECK",
        "read_only": True, "production_write": False, "crm_write": False,
        "runtime_llm_tokens": 0, "db": state, "verification": verification,
        "markers": {
            "publisher": PUBLISHER.read_text(encoding="utf-8").count(PUB_START),
            "cars_ui": CARS_UI.read_text(encoding="utf-8").count(UI_START),
            "master_card": MASTER_CARD.read_text(encoding="utf-8").count(MASTER_START),
        },
    }


def run_rollback() -> dict[str, Any]:
    if not LAST_BACKUP.is_file():
        raise InstallError("LAST_BACKUP_POINTER_MISSING")
    pointer = json.loads(LAST_BACKUP.read_text(encoding="utf-8"))
    if pointer.get("contract_id") != CONTRACT_ID or tuple(pointer.get("codes") or ()) != TARGETS:
        raise InstallError("LAST_BACKUP_POINTER_INVALID")
    _, guard = import_fresh()
    transaction = guard.rollback_backup(pointer["transaction_backup"], TARGETS)
    code = restore_code(pathlib.Path(pointer["code_backup"]))
    return {
        "contract_id": CONTRACT_ID, "status": "PASS", "mode": "ROLLBACK",
        "production_write": True, "crm_write": False,
        "transaction": transaction, "code": code,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=sorted(RECEIPTS))
    args = parser.parse_args()
    receipt: dict[str, Any]
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "a+") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            if args.mode == "install":
                receipt = run_install()
            elif args.mode == "postcheck":
                receipt = run_postcheck()
            else:
                receipt = run_rollback()
        except Exception as exc:
            receipt = {
                "contract_id": CONTRACT_ID, "status": "FAIL", "mode": args.mode.upper(),
                "errors": [type(exc).__name__ + ":" + str(exc)],
                "traceback_tail": traceback.format_exc()[-6000:],
                "runtime_llm_tokens": 0,
            }
        atomic_json(RECEIPTS[args.mode], receipt)
    return 0 if receipt.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
