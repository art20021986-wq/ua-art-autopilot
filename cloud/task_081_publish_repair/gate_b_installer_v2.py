#!/usr/bin/env python3
"""Fail-closed PythonAnywhere installer for TASK 081.

This program runs remotely only from the separately owner-approved Gate B.
It patches the five exact live modules, republishes only currently missing
published cards (bounded to at most five and always including UA-0013), and
rolls back code, pages, diagnostics, and both catalogs as one outer unit on
any failure.  crm.db is read-only throughout and must remain byte-identical.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile


HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import patcher_v2 as patcher  # noqa: E402


CONTRACT = "UA-0013-PUBLISH-REPAIR-001-V1.0"
ROOT = pathlib.Path(os.environ.get("TASK081_ROOT", "/home/Carix"))
SAFE = pathlib.Path(
    os.environ.get(
        "TASK081_SAFE", "/home/Carix/autopilot_inbox/cloud/task_081_publish_repair"
    )
)
BACKUP_PARENT = SAFE / "backups_v2"
LOCK_FILE = SAFE / ".task081-v2.lock"
DATABASE = ROOT / "crm.db"
CANARY = "UA-0013"
PUBLIC_DIRS = (ROOT / "video", ROOT / "site")
SHADOW_RECEIPT = SAFE / "shadow_receipt_v2.json"
INSTALL_RECEIPT = SAFE / "install_receipt_v2.json"
ROLLBACK_RECEIPT = SAFE / "rollback_receipt_v2.json"


class InstallBlocked(RuntimeError):
    pass


def require(condition, code: str) -> None:
    if not condition:
        raise InstallBlocked(code)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_bytes(path: pathlib.Path, limit: int = 50_000_000) -> bytes:
    value = path.read_bytes()
    require(len(value) <= limit, "FILE_TOO_LARGE:" + path.name)
    return value


def atomic_write(path: pathlib.Path, value: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix="." + path.name + ".",
        suffix=".tmp",
        delete=False,
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, value: dict) -> None:
    atomic_write(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
    )


@contextlib.contextmanager
def deployment_lock():
    SAFE.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def row_hash(row: sqlite3.Row) -> str:
    payload = {name: row[name] for name in sorted(row.keys())}
    return sha_bytes(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()
    )


def database_snapshot() -> dict:
    connection = sqlite3.connect("file:%s?mode=ro" % DATABASE.as_posix(), uri=True)
    connection.row_factory = sqlite3.Row
    try:
        quick = connection.execute("PRAGMA quick_check").fetchone()[0]
        rows = list(connection.execute("SELECT * FROM cars ORDER BY id"))
    finally:
        connection.close()
    require(quick == "ok", "DATABASE_QUICK_CHECK")
    numbers = [str(row["auto_number"] or "").upper() for row in rows]
    require(len(rows) >= 13, "DATABASE_CARD_COUNT:%d" % len(rows))
    require(len(numbers) == len(set(numbers)), "DATABASE_DUPLICATE_AUTO_NUMBER")
    canary_rows = [row for row in rows if str(row["auto_number"] or "").upper() == CANARY]
    require(len(canary_rows) == 1, "CANARY_ROW_COUNT:%d" % len(canary_rows))
    canary = canary_rows[0]
    require(str(canary["status"] or "") == "sea_loaded", "CANARY_STAGE_NOT_SEA_LOADED")
    require(int(canary["published"] or 0) == 1, "CANARY_NOT_PUBLISHED")
    published = [
        str(row["auto_number"] or "").upper()
        for row in rows
        if int(row["published"] or 0) == 1
    ]
    require(all(re.fullmatch(r"UA-[0-9]{4,}", value) for value in published),
            "PUBLISHED_ID_FORMAT")
    return {
        "quick_check": quick,
        "cards_count": len(rows),
        "published_numbers": published,
        "row_sha256": {
            str(row["auto_number"] or "").upper(): row_hash(row) for row in rows
        },
        "database_sha256": sha_bytes(read_bytes(DATABASE)),
        "canary": {
            "auto_number": CANARY,
            "status": str(canary["status"] or ""),
            "published": int(canary["published"] or 0),
            "publish_pending": int(canary["publish_pending"] or 0)
            if "publish_pending" in canary.keys()
            else None,
            "sea_container": str(canary["sea_container"] or "")
            if "sea_container" in canary.keys()
            else "",
        },
    }


def catalog_href_counts(path: pathlib.Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    counts = {}
    for identifier in re.findall(
        r"href=['\"](?:[^'\"]*/)?(UA-[0-9]{4,})\.html(?:[?#][^'\"]*)?['\"]",
        text,
        re.I,
    ):
        identifier = identifier.upper()
        counts[identifier] = counts.get(identifier, 0) + 1
    return counts


def repair_targets(database: dict) -> list[str]:
    video_counts = catalog_href_counts(ROOT / "video" / "katalog.html")
    missing = []
    for number in database["published_numbers"]:
        page_missing = any(
            not (directory / (number + ".html")).is_file()
            or not (directory / (number + "-diag.html")).is_file()
            for directory in PUBLIC_DIRS
        )
        if video_counts.get(number, 0) == 0 or page_missing:
            missing.append(number)
    require(CANARY in missing, "CANARY_GAP_NOT_PRESENT")
    require(1 <= len(missing) <= 5, "REPAIR_TARGET_BOUND:%d" % len(missing))
    return missing


def file_state(path: pathlib.Path) -> dict:
    if not path.exists():
        return {"exists": False, "sha256": None, "size": 0}
    value = read_bytes(path, 12_000_000)
    return {"exists": True, "sha256": sha_bytes(value), "size": len(value)}


def target_paths(targets: list[str]) -> list[pathlib.Path]:
    paths = []
    for directory in PUBLIC_DIRS:
        paths.append(directory / "katalog.html")
        for number in targets:
            paths.extend([directory / (number + ".html"), directory / (number + "-diag.html")])
            if directory.is_dir():
                paths.extend(sorted(directory.glob(number + "-[0-9a-f]*.html")))
    return sorted(set(paths), key=str)


def protected_pages_snapshot(targets: list[str]) -> dict:
    protected = {}
    for directory in PUBLIC_DIRS:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("UA-*.html")):
            if any(path.name.startswith(number) for number in targets):
                continue
            protected[str(path)] = sha_bytes(read_bytes(path, 8_000_000))
    return protected


def code_snapshot() -> dict:
    return {
        name: sha_bytes(read_bytes(ROOT / name, 8_000_000))
        for name in patcher.FULL_FILE_SHA256
    }


def full_snapshot() -> dict:
    database = database_snapshot()
    targets = repair_targets(database)
    return {
        "code_sha256": code_snapshot(),
        "database": database,
        "repair_targets": targets,
        "protected_pages_sha256": protected_pages_snapshot(targets),
        "target_state": {
            str(path): file_state(path) for path in target_paths(targets)
        },
    }


def build_candidates() -> dict[str, bytes]:
    sources = {
        name: read_bytes(ROOT / name, 8_000_000).decode("utf-8")
        for name in patcher.FULL_FILE_SHA256
    }
    values = patcher.build_candidates(sources, check_full_sha=True)
    return {name: value.encode("utf-8") for name, value in values.items()}


def parse_marker(stdout: str) -> dict:
    marker = "TASK081_RESULT="
    values = [line[len(marker) :] for line in stdout.splitlines() if line.startswith(marker)]
    require(len(values) == 1, "PUBLISH_RESULT_MARKER:%d" % len(values))
    return json.loads(values[0])


def run_publishers(targets: list[str], proba: bool, candidate_dir=None) -> dict:
    script = (
        "import json,publikaciya;"
        "targets=%r;results=[];"
        "[(lambda r:results.append({'auto_number':n,'ok':r[0],'message':r[1]}))"
        "(publikaciya.opublikovat(n,proba=%s)) for n in targets];"
        "print('TASK081_RESULT='+json.dumps({'results':results},ensure_ascii=False))"
        % (targets, "True" if proba else "False")
    )
    environment = os.environ.copy()
    if candidate_dir is not None:
        environment["PYTHONPATH"] = str(candidate_dir) + os.pathsep + str(ROOT)
        working = pathlib.Path(candidate_dir)
    else:
        environment["PYTHONPATH"] = str(ROOT)
        working = ROOT
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(working),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=900,
    )
    value = parse_marker(completed.stdout)
    value["returncode"] = completed.returncode
    value["stderr_tail"] = completed.stderr[-3000:]
    require(completed.returncode == 0, "PUBLISH_SUBPROCESS:%d" % completed.returncode)
    failures = [item for item in value.get("results") or [] if item.get("ok") is not True]
    require(not failures, "PUBLISH_FALSE:" + json.dumps(failures, ensure_ascii=False)[:1800])
    require(len(value.get("results") or []) == len(targets), "PUBLISH_RESULT_COUNT")
    return value


def validate_local_public(database: dict, repaired: list[str]) -> dict:
    output = {}
    for directory in PUBLIC_DIRS:
        require(directory.is_dir(), "PUBLIC_DIR_MISSING:" + str(directory))
        catalog = (directory / "katalog.html").read_text(encoding="utf-8")
        counts = catalog_href_counts(directory / "katalog.html")
        for number in database["published_numbers"]:
            require(counts.get(number, 0) == 1,
                    "CATALOG_HREF_COUNT:%s:%s:%d" % (
                        directory, number, counts.get(number, 0)))
        for number in repaired:
            primary = (directory / (number + ".html")).read_text(encoding="utf-8")
            diag = (directory / (number + "-diag.html")).read_text(encoding="utf-8")
            diag_pattern = re.compile(
                r"href=['\"](?:[^'\"]*/)?%s-diag\.html(?:[?#][^'\"]*)?['\"]"
                % re.escape(number),
                re.I,
            )
            require(number in primary and len(diag_pattern.findall(primary)) == 1,
                    "PRIMARY_LOCAL:%s:%s" % (directory, number))
            require(number in diag and "иагност" in diag.lower(),
                    "DIAG_LOCAL:%s:%s" % (directory, number))
        marker = 'data-ua-card="%s"' % CANARY
        position = catalog.find(marker)
        window = catalog[max(0, position - 500) : position + 1600]
        require(position >= 0 and 'data-ua-stage="2"' in window,
                "CANARY_CATALOG_STAGE:%s" % directory)
        canary_primary = (directory / (CANARY + ".html")).read_text(encoding="utf-8")
        require(
            'data-ua-stage-current="2"' in canary_primary
            or ('data-ua-stage="2"' in canary_primary and "На пароме" in canary_primary),
            "CANARY_PRIMARY_STAGE:%s" % directory,
        )
        output[str(directory)] = {
            "catalog_sha256": sha_bytes(catalog.encode()),
            "published_href_counts": {
                number: counts.get(number, 0) for number in database["published_numbers"]
            },
            "canary_stage": "sea_loaded/2/На пароме",
        }
    return output


def make_backup(before: dict) -> pathlib.Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = BACKUP_PARENT / stamp
    suffix = 0
    while backup.exists():
        suffix += 1
        backup = BACKUP_PARENT / (stamp + "-%d" % suffix)
    backup.mkdir(parents=True, mode=0o700)
    paths = [ROOT / name for name in patcher.FULL_FILE_SHA256] + target_paths(
        before["repair_targets"]
    )
    entries = {}
    for path in paths:
        state = file_state(path)
        entry = dict(state)
        entry["mode"] = (path.stat().st_mode & 0o777) if path.exists() else None
        entry["backup_name"] = None
        if path.exists():
            name = hashlib.sha256(str(path).encode()).hexdigest() + ".bak"
            shutil.copy2(path, backup / name)
            require(
                sha_bytes(read_bytes(backup / name, 12_000_000)) == state["sha256"],
                "BACKUP_SHA:" + str(path),
            )
            entry["backup_name"] = name
        entries[str(path)] = entry
    atomic_json(
        backup / "manifest.json",
        {
            "contract_id": CONTRACT,
            "created_at_utc": utc_now(),
            "entries": entries,
            "before": before,
        },
    )
    return backup


def restore_backup(backup: pathlib.Path) -> dict:
    resolved = backup.resolve()
    require(BACKUP_PARENT.resolve() in resolved.parents, "BACKUP_SCOPE")
    manifest = json.loads(read_bytes(resolved / "manifest.json", 4_000_000).decode())
    require(manifest.get("contract_id") == CONTRACT, "BACKUP_CONTRACT")
    for key, entry in manifest["entries"].items():
        path = pathlib.Path(key)
        if entry["exists"]:
            atomic_write(
                path,
                read_bytes(resolved / entry["backup_name"], 12_000_000),
                int(entry.get("mode") or 0o644),
            )
        elif path.exists():
            path.unlink()
    for key, entry in manifest["entries"].items():
        require(
            file_state(pathlib.Path(key))
            == {"exists": entry["exists"], "sha256": entry["sha256"], "size": entry["size"]},
            "ROLLBACK_TARGET:" + key,
        )
    after = full_snapshot()
    before = manifest["before"]
    require(after["code_sha256"] == before["code_sha256"], "ROLLBACK_CODE")
    require(after["database"] == before["database"], "ROLLBACK_DATABASE")
    require(
        after["protected_pages_sha256"] == before["protected_pages_sha256"],
        "ROLLBACK_PROTECTED",
    )
    require(after["target_state"] == before["target_state"], "ROLLBACK_PUBLIC_TARGETS")
    return {"backup_root": str(resolved), "verified": True, "after": after}


def shadow() -> dict:
    receipt = {
        "contract_id": CONTRACT,
        "mode": "SHADOW",
        "status": "BLOCKED",
        "production_write": False,
        "crm_db_write": False,
        "started_at_utc": utc_now(),
        "errors": [],
    }
    temporary = None
    try:
        with deployment_lock():
            before = full_snapshot()
            candidates = build_candidates()
            temporary = pathlib.Path(tempfile.mkdtemp(prefix="task081-shadow-", dir=SAFE))
            for name, value in candidates.items():
                atomic_write(temporary / name, value)
            receipt["publisher_probe"] = run_publishers(
                before["repair_targets"], True, temporary
            )
            after = full_snapshot()
            require(after == before, "SHADOW_CHANGED_PRODUCTION")
            receipt["before"] = before
            receipt["candidate_sha256"] = {
                name: sha_bytes(value) for name, value in candidates.items()
            }
            receipt["status"] = "PASS"
    except Exception as exc:  # noqa: BLE001
        receipt["errors"].append(type(exc).__name__ + ":" + str(exc))
    finally:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)
    receipt["finished_at_utc"] = utc_now()
    return receipt


def install() -> dict:
    receipt = {
        "contract_id": CONTRACT,
        "mode": "INSTALL",
        "status": "BLOCKED",
        "production_write": False,
        "crm_db_write": False,
        "started_at_utc": utc_now(),
        "errors": [],
        "rollback": None,
    }
    backup = None
    try:
        with deployment_lock():
            before = full_snapshot()
            candidates = build_candidates()
            backup = make_backup(before)
            receipt["backup_root"] = str(backup)
            receipt["before"] = before
            receipt["candidate_sha256"] = {
                name: sha_bytes(value) for name, value in candidates.items()
            }
            for name, value in candidates.items():
                path = ROOT / name
                atomic_write(path, value, path.stat().st_mode & 0o777)
            receipt["production_write"] = True
            for name, expected in receipt["candidate_sha256"].items():
                require(
                    sha_bytes(read_bytes(ROOT / name, 8_000_000)) == expected,
                    "INSTALL_CODE_READBACK:" + name,
                )
            receipt["publisher"] = run_publishers(before["repair_targets"], False)
            after_database = database_snapshot()
            require(after_database == before["database"], "INSTALL_DATABASE_CHANGED")
            require(
                protected_pages_snapshot(before["repair_targets"])
                == before["protected_pages_sha256"],
                "INSTALL_PROTECTED_CHANGED",
            )
            require(code_snapshot() == receipt["candidate_sha256"], "INSTALL_CODE_CHANGED")
            receipt["local_public"] = validate_local_public(
                after_database, before["repair_targets"]
            )
            receipt["after"] = {
                "code_sha256": code_snapshot(),
                "database": after_database,
                "protected_pages_sha256": protected_pages_snapshot(
                    before["repair_targets"]
                ),
                "target_state": {
                    str(path): file_state(path)
                    for path in target_paths(before["repair_targets"])
                },
            }
            receipt["status"] = "PASS"
    except Exception as exc:  # noqa: BLE001
        receipt["errors"].append(type(exc).__name__ + ":" + str(exc))
        if backup is not None and receipt["production_write"]:
            try:
                receipt["rollback"] = restore_backup(backup)
                receipt["status"] = "ROLLED_BACK"
            except Exception as rollback_exc:  # noqa: BLE001
                receipt["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc)
                )
                receipt["status"] = "BLOCKED"
    receipt["finished_at_utc"] = utc_now()
    return receipt


def explicit_rollback() -> dict:
    install_receipt = json.loads(read_bytes(INSTALL_RECEIPT, 6_000_000).decode())
    require(install_receipt.get("contract_id") == CONTRACT, "INSTALL_RECEIPT_CONTRACT")
    backup = pathlib.Path(str(install_receipt.get("backup_root") or ""))
    require(bool(str(backup)), "INSTALL_RECEIPT_BACKUP")
    with deployment_lock():
        details = restore_backup(backup)
    return {
        "contract_id": CONTRACT,
        "mode": "ROLLBACK",
        "status": "PASS",
        "production_write": True,
        "crm_db_write": False,
        **details,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--shadow", action="store_true")
    mode.add_argument("--install", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    SAFE.mkdir(parents=True, exist_ok=True)
    if args.shadow:
        value, path = shadow(), SHADOW_RECEIPT
    elif args.install:
        value, path = install(), INSTALL_RECEIPT
    else:
        try:
            value = explicit_rollback()
        except Exception as exc:  # noqa: BLE001
            value = {
                "contract_id": CONTRACT,
                "mode": "ROLLBACK",
                "status": "BLOCKED",
                "production_write": False,
                "crm_db_write": False,
                "errors": [type(exc).__name__ + ":" + str(exc)],
            }
        path = ROLLBACK_RECEIPT
    value["finished_at_utc"] = value.get("finished_at_utc") or utc_now()
    atomic_json(path, value)
    print(json.dumps({"status": value["status"], "errors": value.get("errors", [])},
                     ensure_ascii=False))
    return 0 if value["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
