#!/usr/bin/env python3
"""Fail-closed PythonAnywhere publisher for UA-0017 and UA-0018.

The script never patches runtime code.  It binds the two exact CRM rows,
creates SQLite and root-HTML backups, flips only the publication flags, then
uses the already-installed TASK083 transactional batch publisher.  Any local
failure restores the web preimage and the two CRM flag preimages.
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import contextlib
import datetime as dt
import fcntl
import gzip
import hashlib
import importlib
import inspect
import json
import os
import pathlib
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable, Mapping


TASK_ID = "TASK120-PUBLISH-UA-0017-UA-0018"
CONTRACT_ID = "UA-ART-PUBLISH-17-18-001-V1.0"
BACKUP_SCHEMA = "ua-art-task120-backup-v1"
BACKUP_INDEX_SCHEMA = "ua-art-task120-backup-index-v1"
RECEIPT_SCHEMA = "ua-art-task120-remote-receipt-v1"
TARGETS = ("UA-0017", "UA-0018")
EXPECTED_PUBLIC_IDS = tuple("UA-%04d" % value for value in range(1, 19))
EXPECTED_MEDIA_COUNTS = {
    "UA-0017": {"foto": 39, "video": 0},
    "UA-0018": {"foto": 36, "video": 1},
}
TARGET_BINDINGS = {
    "UA-0017": {
        "id": 26,
        "vin": "WAUZZZ4GXGN069684",
        "brand": "Audi",
        "model": "A6",
        "year": "2015",
        "fuel": "diesel",
        "engine_cc": 2967,
        "gearbox": "автомат",
        "drive": "полный",
        "mileage_km": 118000,
        "color": "серебристый",
        "price_uah": 23000,
        "review_status": "approved_owner",
        "status": "ge_waiting",
    },
    "UA-0018": {
        "id": 28,
        "vin": "KNAG541BBPA224823",
        "brand": "Kia",
        "model": "K5",
        "year": "2023",
        "fuel": "газ",
        "engine_cc": 1999,
        "gearbox": "Автомат",
        "drive": "передний",
        "mileage_km": 110000,
        "color": "Темный графит",
        "price_uah": 19900,
        "review_status": "approved_owner",
        "status": "ge_to_kyiv",
    },
}
AUDI_SOURCE_URL = (
    "https://press.audi.co.uk/assets/documents/original/"
    "17378-AudiUK00001705AudiA6andS6Saloonand.pdf"
)
KIA_SOURCE_URL = "https://www.kia.com/kr/vehicles/k5_bak_20231031/specification"


def _fact(
    field_key: str,
    label_ru: str,
    display_value: str,
    category: str,
    unit: str,
    domain: str,
    source_url: str,
) -> dict[str, Any]:
    return {
        "field_key": field_key,
        "label_ru": label_ru,
        "display_value": display_value,
        "category": category,
        "unit": unit,
        "confidence": 1.0,
        "evidence_count": 1,
        "visible": True,
        "manual": False,
        "source_domains": (domain,),
        "source_url": source_url,
    }


FACTS = {
    "UA-0017": (
        _fact("adblue_tank_l", "Объём бака AdBlue", "17", "capacity", "л", "press.audi.co.uk", AUDI_SOURCE_URL),
        _fact("body_height_mm", "Высота кузова", "1455", "dimensions", "мм", "press.audi.co.uk", AUDI_SOURCE_URL),
        _fact("body_length_mm", "Длина кузова", "4932", "dimensions", "мм", "press.audi.co.uk", AUDI_SOURCE_URL),
        _fact("body_width_mm", "Ширина кузова", "1874", "dimensions", "мм", "press.audi.co.uk", AUDI_SOURCE_URL),
        _fact("emissions_standard", "Экологический стандарт", "EU6", "ecology", "", "press.audi.co.uk", AUDI_SOURCE_URL),
        _fact("engine_cylinders", "Количество цилиндров", "6", "engine", "", "press.audi.co.uk", AUDI_SOURCE_URL),
        _fact("engine_displacement_cc", "Рабочий объём двигателя", "2967", "engine", "см³", "press.audi.co.uk", AUDI_SOURCE_URL),
        _fact("front_overhang_mm", "Передний свес", "925", "dimensions", "мм", "press.audi.co.uk", AUDI_SOURCE_URL),
        _fact("front_track_mm", "Передняя колея", "1627", "dimensions", "мм", "press.audi.co.uk", AUDI_SOURCE_URL),
        _fact("fuel_tank_l", "Объём топливного бака", "73", "capacity", "л", "press.audi.co.uk", AUDI_SOURCE_URL),
        _fact("height_with_roof_aerial_mm", "Высота с антенной на крыше", "1468", "dimensions", "мм", "press.audi.co.uk", AUDI_SOURCE_URL),
        _fact("luggage_capacity_l", "Объём багажника", "530", "capacity", "л", "press.audi.co.uk", AUDI_SOURCE_URL),
        _fact("rear_overhang_mm", "Задний свес", "1095", "dimensions", "мм", "press.audi.co.uk", AUDI_SOURCE_URL),
        _fact("rear_track_mm", "Задняя колея", "1618", "dimensions", "мм", "press.audi.co.uk", AUDI_SOURCE_URL),
        _fact("turning_circle_m", "Диаметр разворота", "11.9", "dimensions", "м", "press.audi.co.uk", AUDI_SOURCE_URL),
        _fact("valves_per_cylinder", "Клапанов на цилиндр", "4", "engine", "", "press.audi.co.uk", AUDI_SOURCE_URL),
        _fact("wheelbase_mm", "Колёсная база", "2912", "dimensions", "мм", "press.audi.co.uk", AUDI_SOURCE_URL),
        _fact("width_including_mirrors_mm", "Ширина с зеркалами", "2086", "dimensions", "мм", "press.audi.co.uk", AUDI_SOURCE_URL),
    ),
    "UA-0018": (
        _fact("body_length_mm", "Длина кузова", "4905", "dimensions", "мм", "www.kia.com", KIA_SOURCE_URL),
        _fact("body_width_mm", "Ширина кузова", "1860", "dimensions", "мм", "www.kia.com", KIA_SOURCE_URL),
        _fact("body_height_mm", "Высота кузова", "1445", "dimensions", "мм", "www.kia.com", KIA_SOURCE_URL),
        _fact("wheelbase_mm", "Колёсная база", "2850", "dimensions", "мм", "www.kia.com", KIA_SOURCE_URL),
        _fact("front_track_mm", "Передняя колея (16/17/18/19 дюймов)", "1633 / 1623 / 1618 / 1610", "dimensions", "мм", "www.kia.com", KIA_SOURCE_URL),
        _fact("rear_track_mm", "Задняя колея (16/17/18/19 дюймов)", "1640 / 1630 / 1625 / 1617", "dimensions", "мм", "www.kia.com", KIA_SOURCE_URL),
        _fact("max_power", "Максимальная мощность", "146 / 6000", "dynamics", "л.с. / об/мин", "www.kia.com", KIA_SOURCE_URL),
        _fact("max_torque", "Максимальный крутящий момент", "19.5 / 4200", "dynamics", "кгс·м / об/мин", "www.kia.com", KIA_SOURCE_URL),
        _fact("front_brakes", "Передние тормоза", "Вентилируемые дисковые", "brakes", "", "www.kia.com", KIA_SOURCE_URL),
        _fact("rear_brakes", "Задние тормоза", "Дисковые", "brakes", "", "www.kia.com", KIA_SOURCE_URL),
        _fact("front_suspension", "Передняя подвеска", "МакФерсон", "suspension", "", "www.kia.com", KIA_SOURCE_URL),
        _fact("rear_suspension", "Задняя подвеска", "Многорычажная", "suspension", "", "www.kia.com", KIA_SOURCE_URL),
    ),
}
EXPECTED_RUNTIME_HASHES = {
    "publikaciya.py": "fb7fa77277ebc3330c85ab3744c85ac7f084074a314866a5bf388a283f2622c0",
    "publish_transaction_guard.py": "ce6bd00338fbdc38b91f9554ea7baab3b8e921ffe6c1035aa4aba0186e2b549d",
    "catalog_design_guard.py": "51127bbc2be949e1d37f7b6995c0e5a7a32a497c8436139322ce5b0fea308d60",
    "stranica.py": "42aa5fc9db162e59fcf36b7ee9b2002360205827023786a65cf2205ab16066cc",
    "master_card.py": "f64e0b82b11bfd6089509510e5b131a91b03d40bed97b16075ab2ec60da380ce",
    "yadro.py": "1e92a22a3fc485ea2cfe3d00a50586e872b3f6e4f628923b2ab9744534406992",
    "ua_additional_spec.py": "a04bb9fe565379a02e2c4e1b7c055821ecd63fb3e7c84138e5fe949ac032d259",
    "vin_spec_service.py": "247943e514f34dc37265791bf56fd36e58bcbaa8b2064285544733b1afc42bae",
    "catalog_design_golden.html": "34fb82b9ec1bc66b76fccbbaad9b440d01ea4d60fe5c195954e88251442ecdd0",
}
UID_RE = re.compile(r"^UA-[0-9]{4}$")
RUN_RE = re.compile(r"^[a-z0-9][a-z0-9-]{11,79}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_HTML_BYTES = 40 * 1024 * 1024
MAX_PHOTO_BYTES = 20 * 1024 * 1024
MAX_VIDEO_BYTES = 20 * 1024 * 1024
TASK083_EVIDENCE_NAME = "task083-publication.json"
PUBLISH_STARTED_NAME = "publish-started.json"
MEDIA_INTENT_NAME = "media-commit-intent.json"
POSTIMAGE_NAME = "task120-postimage.json"


class Task120Error(RuntimeError):
    pass


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"__bytes_b64__": base64.b64encode(value).decode("ascii")}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _test_root() -> pathlib.Path | None:
    raw = os.environ.get("UAART_TASK120_TEST_ROOT", "").strip()
    if not raw:
        return None
    if os.environ.get("UAART_TASK120_ALLOW_TEST_ROOT") != "1":
        raise Task120Error("TEST_ROOT_NOT_AUTHORIZED")
    path = pathlib.Path(raw)
    if not path.is_absolute() or path == pathlib.Path("/"):
        raise Task120Error("TEST_ROOT_INVALID")
    return path.resolve(strict=True)


ROOT = _test_root() or pathlib.Path("/home/Carix")
REMOTE_DIR = ROOT / "autopilot_inbox/cloud/task_068_ferry_vin"
BACKUP_ROOT = ROOT / "rezerv_publikacii/TASK120"
DB = ROOT / "crm.db"
SITE_ROOTS = (ROOT / "site", ROOT / "video")
PUBLISH_LOCK = ROOT / ".ua_art_publish_transaction.lock"
SELF = pathlib.Path(__file__).resolve()


def _safe_backup_root(*, create: bool) -> pathlib.Path:
    current = ROOT
    for part in ("rezerv_publikacii", "TASK120"):
        current = current / part
        if os.path.lexists(str(current)):
            info = current.lstat()
            if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise Task120Error("BACKUP_ROOT_UNSAFE:" + str(current))
        elif create:
            current.mkdir(mode=0o700)
            _fsync_dir(current.parent)
        else:
            raise Task120Error("BACKUP_ROOT_MISSING")
    if current != BACKUP_ROOT:
        raise Task120Error("BACKUP_ROOT_IDENTITY")
    return current


def _assert_under(path: pathlib.Path, root: pathlib.Path) -> pathlib.Path:
    path = path.resolve()
    root = root.resolve()
    if path != root and root not in path.parents:
        raise Task120Error("PATH_OUT_OF_SCOPE:" + str(path))
    return path


def _lexical_under(root: pathlib.Path, relative: str) -> pathlib.Path:
    """Return an in-root lexical path without ever resolving a symlink."""
    pure = pathlib.PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or str(pure) != relative:
        raise Task120Error("RELATIVE_PATH_INVALID:" + relative)
    root_info = root.lstat()
    if not stat.S_ISDIR(root_info.st_mode) or root.is_symlink():
        raise Task120Error("ROOT_PATH_UNSAFE:" + str(root))
    current = root
    for part in pure.parts[:-1]:
        current = current / part
        if os.path.lexists(str(current)):
            info = current.lstat()
            if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise Task120Error("PARENT_PATH_UNSAFE:" + str(current))
    return root.joinpath(*pure.parts)


def _read_regular(path: pathlib.Path, maximum: int) -> tuple[bytes, os.stat_result]:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or path.is_symlink() or before.st_nlink != 1:
        raise Task120Error("UNSAFE_FILE:" + str(path))
    if before.st_size < 0 or before.st_size > maximum:
        raise Task120Error("FILE_SIZE:" + str(path))
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise Task120Error("FILE_RACE:" + str(path))
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining > 0:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            if not block:
                break
            chunks.append(block)
            remaining -= len(block)
        value = b"".join(chunks)
    finally:
        os.close(descriptor)
    after = path.lstat()
    if (
        len(value) != before.st_size
        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    ):
        raise Task120Error("FILE_RACE:" + str(path))
    return value, before


def _stream_regular_state(path: pathlib.Path) -> dict[str, Any]:
    """Hash an arbitrarily-sized regular file without retaining it in memory."""
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or path.is_symlink() or before.st_nlink != 1:
        raise Task120Error("UNSAFE_FILE:" + str(path))
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    digest = hashlib.sha256()
    size = 0
    try:
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise Task120Error("FILE_RACE:" + str(path))
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            size += len(block)
            digest.update(block)
    finally:
        os.close(descriptor)
    after = path.lstat()
    if (
        size != before.st_size
        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    ):
        raise Task120Error("FILE_RACE:" + str(path))
    return {
        "exists": True,
        "sha256": digest.hexdigest(),
        "size": size,
        "mode": stat.S_IMODE(before.st_mode),
    }


def _fsync_dir(path: pathlib.Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic(path: pathlib.Path, value: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=path.parent, delete=False)
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_live(path: pathlib.Path, value: bytes, mode: int) -> None:
    """Atomic live write with one intent-recognizable crash residue name."""
    temporary = path.with_name("." + path.name + ".task120.tmp")
    if os.path.lexists(str(temporary)):
        raise Task120Error("LIVE_TEMP_PREEXISTING:" + str(temporary))
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        view = memoryview(value)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise Task120Error("LIVE_TEMP_WRITE")
            view = view[written:]
        os.fsync(descriptor)
        os.fchmod(descriptor, mode)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    _fsync_dir(path.parent)


def _atomic_json(path: pathlib.Path, value: Mapping[str, Any]) -> None:
    _atomic(path, _canonical(dict(value)), 0o600)


_HELD_LOCKS: set[str] = set()


@contextlib.contextmanager
def _exclusive(path: pathlib.Path):
    key = str(path.resolve())
    if key in _HELD_LOCKS:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        _HELD_LOCKS.add(key)
        yield
    finally:
        _HELD_LOCKS.discard(key)
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _connect(path: pathlib.Path, *, readonly: bool) -> sqlite3.Connection:
    if readonly:
        connection = sqlite3.connect(
            "file:%s?mode=ro" % path, uri=True, timeout=30.0
        )
        connection.execute("PRAGMA query_only=ON")
    else:
        connection = sqlite3.connect(str(path), timeout=30.0, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=30000")
    return connection


def _quick_check(path: pathlib.Path) -> str:
    with _connect(path, readonly=True) as connection:
        row = connection.execute("PRAGMA quick_check").fetchone()
    return str(row[0]) if row else "missing"


def _assert_atomic_journal_modes(connection: sqlite3.Connection) -> dict[str, str]:
    """Require rollback-journal modes that support the attached DB transaction."""
    allowed = {"delete", "truncate", "persist"}
    result: dict[str, str] = {}
    for schema, label in (("main", "MAIN"), ("ua120_spec", "SPEC")):
        row = connection.execute("PRAGMA %s.journal_mode" % schema).fetchone()
        mode = str(row[0] if row else "").lower()
        if mode not in allowed:
            raise Task120Error("%s_JOURNAL_NOT_ATOMIC:%s" % (label, mode or "missing"))
        result[schema] = mode
    return result


def _spec_db() -> pathlib.Path:
    expected = (ROOT / "vin_specs_task111_v3.db").resolve(strict=True)
    configured = os.environ.get("UA_ART_SPEC_DB", "").strip()
    if configured:
        try:
            configured_path = pathlib.Path(configured).resolve(strict=True)
        except Exception as exc:
            raise Task120Error("SPEC_DB_CONFIG_INVALID") from exc
        if configured_path != expected:
            raise Task120Error("SPEC_DB_CONFIG_DRIFT")
    _assert_under(expected, ROOT)
    _read_regular(expected, 1024 * 1024 * 1024)
    return expected


def _table_names(connection: sqlite3.Connection) -> list[str]:
    return [
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]


def _database_digest(
    path: pathlib.Path,
    *,
    normalized_flags: Mapping[str, Mapping[str, Any]] | None = None,
    normalized_specs: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    """Content digest with only TASK120's expected deltas normalized away."""
    digest = hashlib.sha256()
    with _connect(path, readonly=True) as connection:
        if str(connection.execute("PRAGMA quick_check").fetchone()[0]) != "ok":
            raise Task120Error("SQLITE_QUICK_CHECK:" + str(path))
        schemas = connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master "
            "WHERE sql IS NOT NULL ORDER BY type,name"
        ).fetchall()
        digest.update(_canonical([list(row) for row in schemas]))
        for table in _table_names(connection):
            quoted = '"' + table.replace('"', '""') + '"'
            columns = [str(row[1]) for row in connection.execute("PRAGMA table_info(%s)" % quoted)]
            rows = connection.execute("SELECT rowid,* FROM %s ORDER BY rowid" % quoted).fetchall()
            normalized_rows = []
            for raw in rows:
                item = {key: _json_value(raw[key]) for key in raw.keys()}
                if table == "cars" and normalized_flags:
                    uid = str(item.get("auto_number") or "").strip().upper()
                    if uid in normalized_flags:
                        item["published"] = normalized_flags[uid].get("published")
                        item["publish_pending"] = normalized_flags[uid].get("publish_pending")
                if table in {
                    "additional_specification", "additional_specification_meta"
                } and normalized_specs:
                    uid = str(item.get("car_uid") or "").strip().upper()
                    before = normalized_specs.get(uid)
                    if before is not None and before.get("state") == "EMPTY":
                        # These rows did not exist in the backup and are the
                        # only permitted sidecar insertion made by TASK120.
                        continue
                normalized_rows.append(item)
            digest.update(_canonical({"table": table, "columns": columns, "rows": normalized_rows}))
    return digest.hexdigest()


def _sqlite_backup(source: pathlib.Path, destination: pathlib.Path) -> dict[str, Any]:
    if destination.exists():
        raise Task120Error("BACKUP_EXISTS:" + str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = _connect(source, readonly=True)
    destination_connection = sqlite3.connect(str(destination), timeout=30.0)
    try:
        if str(source_connection.execute("PRAGMA quick_check").fetchone()[0]) != "ok":
            raise Task120Error("BACKUP_SOURCE_INVALID:" + str(source))
        source_connection.backup(destination_connection)
        destination_connection.commit()
        if str(destination_connection.execute("PRAGMA quick_check").fetchone()[0]) != "ok":
            raise Task120Error("BACKUP_COPY_INVALID:" + str(destination))
    finally:
        destination_connection.close()
        source_connection.close()
    os.chmod(destination, 0o600)
    value, _ = _read_regular(destination, 1024 * 1024 * 1024)
    return {
        "stored": str(destination.relative_to(destination.parents[1])),
        "size": len(value),
        "sha256": _sha(value),
        "logical_digest": _database_digest(destination),
    }


def _car_columns(connection: sqlite3.Connection) -> set[str]:
    return {str(row[1]) for row in connection.execute("PRAGMA table_info(cars)")}


def _rows_by_uid(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    placeholders = ",".join("?" for _ in TARGETS)
    rows = connection.execute(
        "SELECT * FROM cars WHERE UPPER(TRIM(auto_number)) IN (%s) ORDER BY auto_number,id"
        % placeholders,
        TARGETS,
    ).fetchall()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        uid = str(item.get("auto_number") or "").strip().upper()
        if uid in result:
            raise Task120Error("TARGET_UID_DUPLICATE:" + uid)
        result[uid] = item
    if set(result) != set(TARGETS):
        raise Task120Error("TARGET_ROWS_MISSING:" + ",".join(sorted(set(TARGETS) - set(result))))
    return result


def _json_media_list(value: Any, uid: str, column: str) -> list[dict[str, str]]:
    if value in (None, "", []):
        raw: Any = []
    elif isinstance(value, str):
        try:
            raw = json.loads(value)
        except Exception as exc:
            raise Task120Error("MEDIA_JSON_INVALID:%s:%s" % (uid, column)) from exc
    else:
        raw = value
    if not isinstance(raw, list):
        raise Task120Error("MEDIA_JSON_NOT_LIST:%s:%s" % (uid, column))
    result: list[dict[str, str]] = []
    for item in raw:
        if (
            type(item) is not dict
            or set(item) != {"file_id", "tag"}
            or not isinstance(item["file_id"], str)
            or not isinstance(item["tag"], str)
        ):
            raise Task120Error("MEDIA_JSON_ITEM:%s:%s" % (uid, column))
        file_id = item["file_id"].strip()
        tag = item["tag"].strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,256}", file_id):
            raise Task120Error("MEDIA_FILE_ID_INVALID:%s:%s" % (uid, column))
        result.append({"file_id": file_id, "tag": tag})
    if len({item["file_id"] for item in result}) != len(result):
        raise Task120Error("MEDIA_FILE_ID_DUPLICATE:%s:%s" % (uid, column))
    return result


def _media_plan(
    connection: sqlite3.Connection,
    rows: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    tables = {
        str(row[0]) for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if "media" not in tables:
        raise Task120Error("MEDIA_TABLE_MISSING")
    required = {
        "id", "car_id", "auto_number", "vid", "file_id", "status", "tag",
        "poryadok", "put", "razmer", "mime",
    }
    columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(media)")}
    if not required.issubset(columns):
        raise Task120Error("MEDIA_SCHEMA_MISSING:" + ",".join(sorted(required - columns)))
    plan: dict[str, list[dict[str, Any]]] = {}
    for uid in TARGETS:
        car = rows[uid]
        listed = {
            "foto": _json_media_list(car.get("photos"), uid, "photos"),
            "video": _json_media_list(car.get("videos"), uid, "videos"),
        }
        expected_counts = EXPECTED_MEDIA_COUNTS[uid]
        if {key: len(value) for key, value in listed.items()} != expected_counts:
            raise Task120Error("CAR_MEDIA_COUNT:%s" % uid)
        database_rows = [
            dict(row) for row in connection.execute(
                "SELECT * FROM media WHERE car_id=? OR UPPER(TRIM(COALESCE(auto_number,'')))=? "
                "ORDER BY CASE vid WHEN 'foto' THEN 0 WHEN 'video' THEN 1 ELSE 2 END,poryadok,id",
                (int(car["id"]), uid),
            ).fetchall()
        ]
        if len(database_rows) != sum(expected_counts.values()):
            raise Task120Error("MEDIA_ROW_COUNT:%s" % uid)
        output: list[dict[str, Any]] = []
        for kind in ("foto", "video"):
            kind_rows = [item for item in database_rows if str(item.get("vid")) == kind]
            if len(kind_rows) != expected_counts[kind]:
                raise Task120Error("MEDIA_KIND_COUNT:%s:%s" % (uid, kind))
            for index, (record, source) in enumerate(zip(kind_rows, listed[kind]), 1):
                if (
                    int(record.get("car_id") or 0) != int(car["id"])
                    or str(record.get("auto_number") or "").strip().upper() != uid
                    or int(record.get("poryadok") or 0) != index
                    or str(record.get("file_id") or "") != source["file_id"]
                    or str(record.get("tag") or "").strip() != source["tag"]
                    or str(record.get("status") or "") != "pending"
                    or record.get("put") not in (None, "")
                    or record.get("razmer") is not None
                    or record.get("mime") not in (None, "")
                ):
                    raise Task120Error("MEDIA_ROW_BINDING:%s:%s:%d" % (uid, kind, index))
                if kind == "video" and (uid != "UA-0018" or source["tag"] != "вертик"):
                    raise Task120Error("MEDIA_VIDEO_TAG:%s:%d" % (uid, index))
                output.append(
                    {
                        "uid": uid,
                        "car_id": int(car["id"]),
                        "row_id": int(record["id"]),
                        "kind": kind,
                        "order": index,
                        "tag": source["tag"],
                        "file_id": source["file_id"],
                    }
                )
        plan[uid] = output
    return plan


def _public_media_plan(
    plan: Mapping[str, Iterable[Mapping[str, Any]]],
) -> dict[str, Any]:
    return {
        uid: {
            "counts": {
                kind: sum(1 for item in plan[uid] if item["kind"] == kind)
                for kind in ("foto", "video")
            },
            "rows": [
                {
                    "row_id": int(item["row_id"]),
                    "kind": str(item["kind"]),
                    "order": int(item["order"]),
                    "tag": str(item["tag"]),
                    "file_id_sha256": _sha(str(item["file_id"]).encode("utf-8")),
                }
                for item in plan[uid]
            ],
        }
        for uid in TARGETS
    }


def _media_destinations(
    plan: Mapping[str, Iterable[Mapping[str, Any]]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for uid in TARGETS:
        for item in plan[uid]:
            if item["kind"] == "foto":
                relative = "video/foto/%s/%03d.jpg" % (uid, int(item["order"]))
                maximum = MAX_PHOTO_BYTES
            else:
                relative = "video/%s.mp4" % uid
                maximum = MAX_VIDEO_BYTES
            result[relative] = {"item": dict(item), "maximum": maximum}
    return result


def _is_target_video_name(name: str, uid: str) -> bool:
    lowered = name.casefold()
    prefix = uid.casefold()
    return (
        ".mp4" in lowered
        and (
            lowered == prefix + ".mp4"
            or lowered.startswith(prefix + "-")
            or lowered.startswith(prefix + ".mp4.")
        )
    )


def _target_video_candidates(uid: str) -> list[pathlib.Path]:
    root = ROOT / "video"
    result: list[pathlib.Path] = []
    for candidate in root.iterdir():
        name = candidate.name
        if _is_target_video_name(name, uid):
            if candidate.is_symlink() or not candidate.is_file():
                raise Task120Error("TARGET_VIDEO_PATH_UNSAFE:" + name)
            result.append(candidate)
    return sorted(result)


def _renderer_video_paths(uid: str) -> list[pathlib.Path]:
    """Mirror master_card.video_fajly_mashiny before it can deduplicate."""
    root = ROOT / "video"
    result: list[pathlib.Path] = []
    for directory, names, files in os.walk(root, followlinks=False):
        directory_text = str(pathlib.Path(directory)).replace(os.sep, "/")
        if any(marker in directory_text for marker in ("/preview", "/archive", "/stage")):
            names[:] = []
            continue
        for name in sorted(files):
            if (
                name.startswith(".")
                or not name.casefold().endswith((".mp4", ".mov", ".m4v", ".webm"))
                or not name.startswith(uid)
            ):
                continue
            path = pathlib.Path(directory) / name
            _read_regular(path, MAX_VIDEO_BYTES)
            result.append(path)
    return sorted(result)


def _assert_renderer_video_state(*, materialized: bool) -> dict[str, list[str]]:
    actual = {
        uid: [str(path.relative_to(ROOT)) for path in _renderer_video_paths(uid)]
        for uid in TARGETS
    }
    allowed_18 = ["video/UA-0018.mp4"] if materialized else []
    if actual["UA-0017"] or actual["UA-0018"] != allowed_18:
        raise Task120Error("RENDERER_VIDEO_SCOPE:" + json.dumps(actual, sort_keys=True))
    return actual


def _media_inventory(
    plan: Mapping[str, Iterable[Mapping[str, Any]]],
) -> dict[str, Any]:
    destinations = _media_destinations(plan)
    allowed = set(destinations)
    directories: dict[str, Any] = {}
    for uid in TARGETS:
        folder = ROOT / "video/foto" / uid
        relative = str(folder.relative_to(ROOT))
        if os.path.lexists(str(folder)):
            info = folder.lstat()
            if not stat.S_ISDIR(info.st_mode) or folder.is_symlink():
                raise Task120Error("MEDIA_DIRECTORY_UNSAFE:" + uid)
            directories[relative] = {"exists": True, "mode": stat.S_IMODE(info.st_mode)}
            for child in folder.iterdir():
                child_relative = str(child.relative_to(ROOT))
                if child_relative not in allowed:
                    raise Task120Error("UNEXPECTED_TARGET_MEDIA:" + child_relative)
        else:
            directories[relative] = {"exists": False}
    for uid in TARGETS:
        for child in _target_video_candidates(uid):
            relative = str(child.relative_to(ROOT))
            if relative not in allowed:
                raise Task120Error("UNEXPECTED_TARGET_MEDIA:" + relative)
    entries: dict[str, Any] = {}
    for relative, details in destinations.items():
        path = _lexical_under(ROOT, relative)
        if os.path.lexists(str(path)):
            value, info = _read_regular(path, int(details["maximum"]))
            entries[relative] = {
                "exists": True,
                "sha256": _sha(value),
                "size": len(value),
                "mode": stat.S_IMODE(info.st_mode),
            }
        else:
            entries[relative] = {"exists": False}
    return {"directories": directories, "entries": entries}


def _protected_media_digest(ignored_relatives: Iterable[str] = ()) -> str:
    digest = hashlib.sha256()
    ignored = set(ignored_relatives)
    photo_root = ROOT / "video/foto"
    if not photo_root.is_dir() or photo_root.is_symlink():
        raise Task120Error("PHOTO_ROOT_UNSAFE")
    paths: list[pathlib.Path] = []
    for directory, names, files in os.walk(photo_root, followlinks=False):
        parent = pathlib.Path(directory)
        relative_parent = parent.relative_to(photo_root)
        if relative_parent.parts and relative_parent.parts[0] in TARGETS:
            names[:] = []
            continue
        for name in names:
            candidate = parent / name
            if candidate.is_symlink():
                raise Task120Error("PROTECTED_MEDIA_SYMLINK:" + str(candidate))
        paths.extend(parent / name for name in files)
    for candidate in (ROOT / "video").iterdir():
        relative = str(candidate.relative_to(ROOT))
        if relative in ignored:
            continue
        if ".mp4" not in candidate.name.casefold():
            continue
        if not any(_is_target_video_name(candidate.name, uid) for uid in TARGETS):
            paths.append(candidate)
    for path in sorted(set(paths)):
        digest.update(
            _canonical({"path": str(path.relative_to(ROOT)), **_stream_regular_state(path)})
        )
    return digest.hexdigest()


def _normalized_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def _expected_spec_semantics(uid: str) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "field_key": fact["field_key"],
            "field_value": fact["display_value"],
            "normalized_value": _normalized_text(fact["display_value"]),
            "source": "OFFICIAL_MODEL_LEVEL",
            "source_url": fact["source_url"],
            "confidence": 1.0,
            "is_price_field": 0,
            "label_ru": fact["label_ru"],
            "category": fact["category"],
            "unit": fact["unit"],
            "evidence_count": 1,
            "source_domains_json": json.dumps(list(fact["source_domains"]), ensure_ascii=False),
            "source_urls_json": json.dumps([fact["source_url"]], ensure_ascii=False),
            "verification_status": "VERIFIED_MODEL_LEVEL",
            "model_match_score": 1.0,
            "is_manual": 0,
            "is_visible": 1,
        }
        for fact in FACTS[uid]
    )


def _spec_state(connection: sqlite3.Connection, schema: str, uid: str) -> dict[str, Any]:
    prefix = schema + "." if schema else ""
    required_tables = {"additional_specification", "additional_specification_meta"}
    table_schema = schema or "main"
    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM %s.sqlite_master WHERE type='table'" % table_schema
        )
    }
    task116_tables = {name for name in tables if name.startswith("ua116_")}
    if task116_tables:
        raise Task120Error("UNEXPECTED_TASK116_SCHEMA:" + ",".join(sorted(task116_tables)))
    if not required_tables.issubset(tables):
        raise Task120Error("SPEC_TABLES_MISSING:%s" % table_schema)
    rows = connection.execute(
        "SELECT a.field_key,a.field_value,a.normalized_value,a.source,a.source_url,"
        "a.confidence,a.is_price_field,m.label_ru,m.category,m.unit,m.evidence_count,"
        "m.source_domains_json,m.source_urls_json,m.verification_status,"
        "m.model_match_score,m.is_manual,m.is_visible "
        "FROM %sadditional_specification a LEFT JOIN %sadditional_specification_meta m "
        "ON m.car_uid=a.car_uid AND m.field_key=a.field_key "
        "WHERE a.car_uid=? ORDER BY a.field_key" % (prefix, prefix),
        (uid,),
    ).fetchall()
    orphan_meta = int(
        connection.execute(
            "SELECT COUNT(*) FROM %sadditional_specification_meta m "
            "LEFT JOIN %sadditional_specification a ON a.car_uid=m.car_uid "
            "AND a.field_key=m.field_key WHERE m.car_uid=? AND a.id IS NULL"
            % (prefix, prefix),
            (uid,),
        ).fetchone()[0]
    )
    if not rows and orphan_meta == 0:
        return {"state": "EMPTY", "count": 0, "digest": _sha(_canonical([]))}
    expected = {item["field_key"]: item for item in _expected_spec_semantics(uid)}
    actual: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        key = str(item["field_key"])
        if key in actual:
            raise Task120Error("SPEC_DUPLICATE:%s:%s" % (table_schema, uid))
        actual[key] = item
    if orphan_meta or set(actual) != set(expected):
        raise Task120Error("SPEC_PARTIAL_OR_FOREIGN:%s:%s" % (table_schema, uid))
    for key, wanted in expected.items():
        got = actual[key]
        for field, value in wanted.items():
            current = got.get(field)
            if field in {"confidence", "model_match_score"}:
                if abs(float(current) - float(value)) > 1e-9:
                    raise Task120Error("SPEC_VALUE_MISMATCH:%s:%s:%s" % (table_schema, uid, key))
            elif field in {"evidence_count", "is_price_field", "is_manual", "is_visible"}:
                if int(current) != int(value):
                    raise Task120Error("SPEC_VALUE_MISMATCH:%s:%s:%s" % (table_schema, uid, key))
            elif str(current or "") != str(value):
                raise Task120Error("SPEC_VALUE_MISMATCH:%s:%s:%s" % (table_schema, uid, key))
    semantic = [actual[key] for key in sorted(actual)]
    return {"state": "EXACT", "count": len(actual), "digest": _sha(_canonical(semantic))}


def _assert_spec_jobs_idle(connection: sqlite3.Connection, schema: str) -> None:
    prefix = schema + "." if schema else ""
    tables = {
        str(row[0]) for row in connection.execute(
            "SELECT name FROM %ssqlite_master WHERE type='table'" % prefix
        )
    }
    if "vin_spec_jobs" not in tables:
        raise Task120Error("SPEC_JOB_TABLE_MISSING")
    count = int(
        connection.execute(
            "SELECT COUNT(*) FROM %svin_spec_jobs "
            "WHERE UPPER(TRIM(status)) IN ('PENDING','RUNNING','PROCESSING')" % prefix
        ).fetchone()[0]
    )
    if count:
        raise Task120Error("SPEC_JOBS_NOT_IDLE:%d" % count)


def _all_spec_states(main: pathlib.Path, spec: pathlib.Path) -> dict[str, Any]:
    connection = _connect(main, readonly=True)
    try:
        connection.execute("ATTACH DATABASE ? AS ua120_spec", (str(spec),))
        _assert_spec_jobs_idle(connection, "ua120_spec")
        return {uid: _spec_state(connection, "ua120_spec", uid) for uid in TARGETS}
    finally:
        connection.close()


def _insert_specs(connection: sqlite3.Connection, schema: str, uid: str) -> None:
    prefix = schema + "." if schema else ""
    now = _utc_now()
    for item in _expected_spec_semantics(uid):
        connection.execute(
            "INSERT INTO %sadditional_specification"
            "(car_uid,field_key,field_value,normalized_value,source,source_url,confidence,is_price_field,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)" % prefix,
            (
                uid, item["field_key"], item["field_value"], item["normalized_value"],
                item["source"], item["source_url"], item["confidence"], 0, now,
            ),
        )
        connection.execute(
            "INSERT INTO %sadditional_specification_meta"
            "(car_uid,field_key,label_ru,category,unit,evidence_count,source_domains_json,"
            "source_urls_json,verification_status,model_match_score,is_manual,is_visible,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)" % prefix,
            (
                uid, item["field_key"], item["label_ru"], item["category"], item["unit"],
                1, item["source_domains_json"], item["source_urls_json"],
                item["verification_status"], 1.0, 0, 1, now, now,
            ),
        )


def _row_public(item: Mapping[str, Any]) -> dict[str, Any]:
    photos = item.get("photos")
    videos = item.get("videos")
    try:
        photo_count = len(json.loads(photos)) if isinstance(photos, str) else len(photos or [])
    except Exception:
        photo_count = -1
    try:
        video_count = len(json.loads(videos)) if isinstance(videos, str) else len(videos or [])
    except Exception:
        video_count = -1
    return {
        "id": int(item.get("id") or 0),
        "auto_number": str(item.get("auto_number") or "").strip().upper(),
        "vin_sha256": _sha(str(item.get("vin") or "").strip().upper().encode()),
        "brand": str(item.get("brand") or ""),
        "model": str(item.get("model") or ""),
        "year": str(item.get("year") or ""),
        "fuel": str(item.get("fuel") or ""),
        "engine_cc": int(item.get("engine_cc") or 0),
        "gearbox": str(item.get("gearbox") or ""),
        "drive": str(item.get("drive") or ""),
        "mileage_km": int(item.get("mileage_km") or 0),
        "color": str(item.get("color") or ""),
        "price_uah": int(item.get("price_uah") or 0),
        "status": str(item.get("status") or ""),
        "review_status": str(item.get("review_status") or ""),
        "published": item.get("published"),
        "publish_pending": item.get("publish_pending"),
        "photo_count": photo_count,
        "video_count": video_count,
        "row_digest": _sha(_canonical({key: _json_value(value) for key, value in item.items()})),
    }


def _validate_bindings(
    rows: Mapping[str, Mapping[str, Any]],
    connection: sqlite3.Connection | None = None,
) -> None:
    owned = connection is None
    if connection is None:
        connection = _connect(DB, readonly=True)
    try:
        columns = _car_columns(connection)
        required = {
            "id", "auto_number", "vin", "brand", "model", "year", "fuel",
            "engine_cc", "gearbox", "drive", "mileage_km", "color", "price_uah",
            "review_status", "status", "published", "publish_pending",
        }
        if not required.issubset(columns):
            raise Task120Error("CRM_SCHEMA_MISSING:" + ",".join(sorted(required - columns)))
        for uid, expected in TARGET_BINDINGS.items():
            item = rows[uid]
            actual: dict[str, Any] = {}
            for key, wanted in expected.items():
                current = item.get(key)
                if key == "vin":
                    actual[key] = str(current or "").strip().upper()
                elif isinstance(wanted, int):
                    actual[key] = int(current or 0)
                else:
                    actual[key] = str(current or "").strip()
            if actual != expected:
                raise Task120Error("TARGET_BINDING_MISMATCH:" + uid)
            if item.get("published") not in (0, 1):
                raise Task120Error("TARGET_PUBLISHED_INVALID:" + uid)
            duplicate_uid = int(
                connection.execute(
                    "SELECT COUNT(*) FROM cars WHERE UPPER(TRIM(auto_number))=?", (uid,)
                ).fetchone()[0]
            )
            duplicate_vin = int(
                connection.execute(
                    "SELECT COUNT(*) FROM cars WHERE UPPER(TRIM(vin))=?", (expected["vin"],)
                ).fetchone()[0]
            )
            if duplicate_uid != 1 or duplicate_vin != 1:
                raise Task120Error("TARGET_IDENTITY_NOT_UNIQUE:" + uid)
    finally:
        if owned:
            connection.close()


def _published_ids(connection: sqlite3.Connection) -> tuple[str, ...]:
    rows = connection.execute(
        "SELECT UPPER(TRIM(auto_number)) FROM cars WHERE COALESCE(published,0)=1 "
        "ORDER BY UPPER(TRIM(auto_number))"
    ).fetchall()
    values = tuple(str(row[0]) for row in rows)
    if len(values) != len(set(values)):
        raise Task120Error("PUBLISHED_UID_DUPLICATE")
    return values


def _runtime_hashes() -> dict[str, str]:
    names = (
        "publikaciya.py",
        "publish_transaction_guard.py",
        "stranica.py",
        "master_card.py",
        "yadro.py",
        "ua_additional_spec.py",
        "vin_spec_service.py",
        "catalog_design_guard.py",
        "catalog_design_golden.html",
    )
    if set(names) != set(EXPECTED_RUNTIME_HASHES):
        raise Task120Error("RUNTIME_EXPECTATION_KEY_SET")
    result: dict[str, str] = {}
    for name in names:
        path = ROOT / name
        value, _ = _read_regular(path, MAX_SOURCE_BYTES)
        if name.endswith(".py"):
            compile(value.decode("utf-8"), name, "exec")
        result[name] = _sha(value)
        expected = EXPECTED_RUNTIME_HASHES.get(name)
        if expected is not None and result[name] != expected:
            raise Task120Error("RUNTIME_HASH_DRIFT:" + name)
    publisher = (ROOT / "publikaciya.py").read_text(encoding="utf-8")
    guard = (ROOT / "publish_transaction_guard.py").read_text(encoding="utf-8")
    required_publisher = (
        "def opublikovat(",
        "_UA083_BASE_PUBLISH",
        "publish_transaction_guard",
        "_ua111_spec.inject_public_spec(html, kod)",
    )
    if any(value not in publisher for value in required_publisher):
        raise Task120Error("PUBLISHER_CONTRACT_MISSING")
    if (
        "def publish_batch(" not in guard
        or "def _publish_locked(" not in guard
        or "def rollback_backup(" not in guard
    ):
        raise Task120Error("PUBLISH_GUARD_CONTRACT_MISSING")
    return result


def _html_manifest() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for root in SITE_ROOTS:
        if not root.is_dir() or root.is_symlink():
            raise Task120Error("SITE_ROOT_INVALID:" + str(root))
        for path in sorted(root.glob("*.html")):
            value, info = _read_regular(path, MAX_HTML_BYTES)
            relative = str(path.relative_to(ROOT))
            result[relative] = {
                "exists": True,
                "sha256": _sha(value),
                "size": len(value),
                "mode": stat.S_IMODE(info.st_mode),
            }
        for uid in TARGETS:
            for suffix in (".html", "-diag.html"):
                relative = str(root.relative_to(ROOT) / (uid + suffix))
                result.setdefault(relative, {"exists": False})
    return result


def _html_preimage_state(item: Mapping[str, Any]) -> dict[str, Any]:
    """Return only the live-file state from an enriched backup HTML entry."""
    exists = item.get("exists")
    if exists is False:
        return {"exists": False}
    if exists is not True:
        raise Task120Error("BACKUP_HTML_STATE_INVALID")
    sha256 = item.get("sha256")
    size = item.get("size")
    mode = item.get("mode")
    if (
        not isinstance(sha256, str)
        or not SHA_RE.fullmatch(sha256)
        or not isinstance(size, int)
        or isinstance(size, bool)
        or size < 0
        or size > MAX_HTML_BYTES
        or not isinstance(mode, int)
        or isinstance(mode, bool)
        or mode < 0
        or mode > 0o7777
    ):
        raise Task120Error("BACKUP_HTML_STATE_INVALID")
    return {"exists": True, "sha256": sha256, "size": size, "mode": mode}


def _renderer_temp_paths() -> list[pathlib.Path]:
    result: list[pathlib.Path] = []
    owned_name = re.compile(
        r"^(?:"
        r"UA-001[78](?:-diag)?(?:-[0-9a-f]{6,10})?\.html\.rem2tmp"
        r"|\.(?:katalog|UA-001[78](?:-diag)?(?:-[0-9a-f]{6,10})?)\.html"
        r"(?:\.[A-Za-z0-9_-]+\.task083\.tmp|\.task120\.tmp)"
        r")$",
        re.I,
    )
    for root in SITE_ROOTS:
        for path in root.iterdir():
            if owned_name.fullmatch(path.name):
                _read_regular(path, MAX_HTML_BYTES)
                result.append(path)
    return sorted(result)


def _preflight() -> dict[str, Any]:
    if ROOT == pathlib.Path("/") or not ROOT.is_dir() or ROOT.is_symlink():
        raise Task120Error("ROOT_INVALID")
    for path in (DB, *SITE_ROOTS):
        if not path.exists():
            raise Task120Error("REQUIRED_PATH_MISSING:" + str(path))
    if _quick_check(DB) != "ok":
        raise Task120Error("CRM_QUICK_CHECK")
    spec = _spec_db()
    if _quick_check(spec) != "ok":
        raise Task120Error("SPEC_QUICK_CHECK")
    with _connect(DB, readonly=True) as connection:
        connection.execute("ATTACH DATABASE ? AS ua120_spec", (str(spec),))
        journal_modes = _assert_atomic_journal_modes(connection)
        rows = _rows_by_uid(connection)
        published = _published_ids(connection)
        media_plan = _media_plan(connection, rows)
    _validate_bindings(rows)
    target_flag_pairs = {
        (rows[uid].get("published"), rows[uid].get("publish_pending"))
        for uid in TARGETS
    }
    if len(target_flag_pairs) != 1 or next(iter(target_flag_pairs)) not in {(0, 0), (1, 0)}:
        raise Task120Error("TARGET_PUBLICATION_STATE_MIXED_OR_INVALID")
    required_before = set(EXPECTED_PUBLIC_IDS[:16])
    if not required_before.issubset(set(published)):
        raise Task120Error("LEGACY_16_NOT_ALL_PUBLISHED")
    if not set(published).issubset(set(EXPECTED_PUBLIC_IDS)):
        raise Task120Error("UNEXPECTED_PUBLISHED_UIDS")
    runtime = _runtime_hashes()
    html = _html_manifest()
    media = _media_inventory(media_plan)
    if _renderer_temp_paths():
        raise Task120Error("RENDERER_TEMP_PREEXISTING")
    renderer_videos = {
        uid: [str(path.relative_to(ROOT)) for path in _renderer_video_paths(uid)]
        for uid in TARGETS
    }
    if renderer_videos["UA-0017"] or renderer_videos["UA-0018"] not in (
        [], ["video/UA-0018.mp4"]
    ):
        raise Task120Error("RENDERER_VIDEO_SCOPE")
    for uid in published:
        for root in SITE_ROOTS:
            if not (root / (uid + ".html")).is_file():
                raise Task120Error("PUBLISHED_PAGE_MISSING:%s:%s" % (uid, root.name))
    public_rows = {uid: _row_public(row) for uid, row in rows.items()}
    spec_states = _all_spec_states(DB, spec)
    digest_payload = {
        "targets": public_rows,
        "published_ids": published,
        "runtime": runtime,
        "html": html,
        "media_plan": _public_media_plan(media_plan),
        "media": media,
        "renderer_videos": renderer_videos,
        "protected_media_digest": _protected_media_digest(),
        "spec_path": str(spec),
        "spec_states": spec_states,
        "journal_modes": journal_modes,
    }
    return {
        **digest_payload,
        "preflight_digest": _sha(_canonical(digest_payload)),
        "database_paths": {"main": str(DB), "spec": str(spec)},
        "free_bytes": shutil.disk_usage(ROOT).free,
    }


def _assert_fresh_backup_preimage(preflight: Mapping[str, Any]) -> None:
    if tuple(preflight.get("published_ids") or ()) != EXPECTED_PUBLIC_IDS[:16]:
        raise Task120Error("BACKUP_NOT_FRESH_PUBLISHED_SET")
    targets = preflight.get("targets") or {}
    specs = preflight.get("spec_states") or {}
    if any(
        (targets.get(uid) or {}).get("published") != 0
        or (targets.get(uid) or {}).get("publish_pending") != 0
        or (specs.get(uid) or {}).get("state") != "EMPTY"
        for uid in TARGETS
    ):
        raise Task120Error("BACKUP_NOT_FRESH_TARGET_DB")
    media = preflight.get("media") or {}
    if any(item.get("exists") for item in (media.get("entries") or {}).values()):
        raise Task120Error("BACKUP_NOT_FRESH_TARGET_MEDIA")
    if any(item.get("exists") for item in (media.get("directories") or {}).values()):
        raise Task120Error("BACKUP_NOT_FRESH_TARGET_MEDIA_DIRECTORY")
    if any((preflight.get("renderer_videos") or {}).get(uid) for uid in TARGETS):
        raise Task120Error("BACKUP_NOT_FRESH_RENDERER_VIDEO")
    html = preflight.get("html") or {}
    for relative, item in html.items():
        if _allowed_web_relative(relative) and not relative.endswith("/katalog.html"):
            if item.get("exists"):
                raise Task120Error("BACKUP_NOT_FRESH_TARGET_HTML:" + relative)
    for root in SITE_ROOTS:
        source = (root / "katalog.html").read_text(encoding="utf-8")
        if (
            _catalog_ids(source) != EXPECTED_PUBLIC_IDS[:16]
            or _catalog_card_counts(source) != {uid: 1 for uid in EXPECTED_PUBLIC_IDS[:16]}
            or _catalog_href_counts(source) != {uid: 2 for uid in EXPECTED_PUBLIC_IDS[:16]}
        ):
            raise Task120Error("BACKUP_NOT_FRESH_CATALOG:" + root.name)


def _backup(preflight: Mapping[str, Any]) -> tuple[pathlib.Path, dict[str, Any], str]:
    free = int(shutil.disk_usage(ROOT).free)
    db_size = int(DB.stat().st_size) + int(_spec_db().stat().st_size)
    if free < max(64 * 1024 * 1024, db_size * 3):
        raise Task120Error("INSUFFICIENT_BACKUP_SPACE")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    _safe_backup_root(create=True)
    root = BACKUP_ROOT / (stamp + "-" + os.urandom(6).hex())
    html_entries: dict[str, Any] = {}
    media_entries: dict[str, Any] = {}
    with _exclusive(PUBLISH_LOCK):
        current = _preflight()
        if current["preflight_digest"] != preflight["preflight_digest"]:
            raise Task120Error("PREFLIGHT_CHANGED_BEFORE_BACKUP")
        _assert_fresh_backup_preimage(current)
        root.mkdir(mode=0o700, exist_ok=False)
        for relative, metadata in current["html"].items():
            item = dict(metadata)
            if item.get("exists"):
                path = ROOT / relative
                value, _ = _read_regular(path, MAX_HTML_BYTES)
                stored = pathlib.Path("html") / (relative + ".gz")
                packed = gzip.compress(value, compresslevel=9, mtime=0)
                _atomic(root / stored, packed, 0o600)
                item["stored"] = str(stored)
                item["stored_sha256"] = _sha(packed)
            html_entries[relative] = item
        for relative, metadata in current["media"]["entries"].items():
            item = dict(metadata)
            if item.get("exists"):
                path = ROOT / relative
                maximum = MAX_VIDEO_BYTES if relative.endswith(".mp4") else MAX_PHOTO_BYTES
                value, _ = _read_regular(path, maximum)
                stored = pathlib.Path("media") / (relative + ".gz")
                packed = gzip.compress(value, compresslevel=9, mtime=0)
                _atomic(root / stored, packed, 0o600)
                item["stored"] = str(stored)
                item["stored_sha256"] = _sha(packed)
            media_entries[relative] = item
        main_meta = _sqlite_backup(DB, root / "db/main.sqlite3")
        spec_path = _spec_db()
        spec_meta = _sqlite_backup(spec_path, root / "db/spec.sqlite3")
    rows = current["targets"]
    preimage = {
        uid: {
            "id": int(rows[uid]["id"]),
            "published": rows[uid]["published"],
            "publish_pending": rows[uid]["publish_pending"],
            "row_digest": rows[uid]["row_digest"],
        }
        for uid in TARGETS
    }
    manifest: dict[str, Any] = {
        "schema": BACKUP_SCHEMA,
        "contract_id": CONTRACT_ID,
        "created_at": _utc_now(),
        "root": str(ROOT),
        "backup_root": str(root),
        "preflight_digest": current["preflight_digest"],
        "preimage": preimage,
        "spec_preimage": current["spec_states"],
        "runtime": current["runtime"],
        "html": html_entries,
        "media_plan": current["media_plan"],
        "media": {
            "directories": current["media"]["directories"],
            "entries": media_entries,
        },
        "protected_media_digest": current["protected_media_digest"],
        "databases": {
            "main": {**main_meta, "source": str(DB)},
            "spec": {**spec_meta, "source": str(spec_path)},
        },
    }
    manifest_path = root / "manifest.json"
    _atomic_json(manifest_path, manifest)
    manifest_bytes, _ = _read_regular(manifest_path, 64 * 1024 * 1024)
    manifest_sha = _sha(manifest_bytes)
    index_path = BACKUP_ROOT / "index" / (manifest_sha + ".json")
    if index_path.exists():
        raise Task120Error("BACKUP_INDEX_COLLISION")
    _atomic_json(
        index_path,
        {
            "schema": BACKUP_INDEX_SCHEMA,
            "task_id": TASK_ID,
            "manifest": _backup_relative(manifest_path),
            "manifest_sha256": manifest_sha,
        },
    )
    return root, manifest, manifest_sha


def _load_backup(relative: str, expected_sha: str) -> tuple[pathlib.Path, dict[str, Any]]:
    if not SHA_RE.fullmatch(expected_sha):
        raise Task120Error("BACKUP_SHA_INVALID")
    _safe_backup_root(create=False)
    if not relative:
        index_path = BACKUP_ROOT / "index" / (expected_sha + ".json")
        index_value, _ = _read_regular(index_path, 1024 * 1024)
        index = json.loads(index_value.decode("utf-8"))
        if (
            not isinstance(index, dict)
            or index.get("schema") != BACKUP_INDEX_SCHEMA
            or index.get("task_id") != TASK_ID
            or index.get("manifest_sha256") != expected_sha
        ):
            raise Task120Error("BACKUP_INDEX_IDENTITY")
        relative = str(index.get("manifest") or "")
    raw = pathlib.PurePosixPath(relative)
    if raw.is_absolute() or ".." in raw.parts or raw.name != "manifest.json":
        raise Task120Error("BACKUP_RELATIVE_INVALID")
    path = _assert_under(BACKUP_ROOT / pathlib.Path(*raw.parts), BACKUP_ROOT)
    value, _ = _read_regular(path, 64 * 1024 * 1024)
    if _sha(value) != expected_sha:
        raise Task120Error("BACKUP_MANIFEST_SHA_MISMATCH")
    manifest = json.loads(value.decode("utf-8"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != BACKUP_SCHEMA
        or manifest.get("contract_id") != CONTRACT_ID
        or manifest.get("root") != str(ROOT)
        or pathlib.Path(str(manifest.get("backup_root"))) != path.parent
    ):
        raise Task120Error("BACKUP_MANIFEST_IDENTITY")
    return path.parent, manifest


def _backup_relative(manifest_path: pathlib.Path) -> str:
    return str(manifest_path.relative_to(BACKUP_ROOT))


def _flags_from_manifest(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw = manifest.get("preimage")
    if not isinstance(raw, dict) or set(raw) != set(TARGETS):
        raise Task120Error("BACKUP_PREIMAGE_INVALID")
    result: dict[str, dict[str, Any]] = {}
    for uid in TARGETS:
        item = raw[uid]
        if not isinstance(item, dict) or int(item.get("id") or 0) != TARGET_BINDINGS[uid]["id"]:
            raise Task120Error("BACKUP_PREIMAGE_BINDING:" + uid)
        if item.get("published") not in (0, 1):
            raise Task120Error("BACKUP_PREIMAGE_FLAG:" + uid)
        result[uid] = dict(item)
    return result


def _bot_token() -> str:
    value, _ = _read_regular(ROOT / "team_token.txt", 1024)
    token = value.decode("utf-8", "strict").strip()
    if not re.fullmatch(r"[0-9]{6,16}:[A-Za-z0-9_-]{25,100}", token):
        raise Task120Error("TELEGRAM_TOKEN_INVALID")
    return token


def _jpeg_dimensions(value: bytes) -> tuple[int, int]:
    if len(value) < 12 or not value.startswith(b"\xff\xd8\xff") or not value.endswith(b"\xff\xd9"):
        raise Task120Error("TELEGRAM_JPEG_STRUCTURE")
    offset = 2
    sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while offset + 4 <= len(value):
        if value[offset] != 0xFF:
            offset += 1
            continue
        while offset < len(value) and value[offset] == 0xFF:
            offset += 1
        if offset >= len(value):
            break
        marker = value[offset]
        offset += 1
        if marker == 0x01 or 0xD0 <= marker <= 0xD9:
            continue
        if offset + 2 > len(value):
            break
        length = int.from_bytes(value[offset:offset + 2], "big")
        if length < 2 or offset + length > len(value):
            break
        if marker in sof and length >= 7:
            height = int.from_bytes(value[offset + 3:offset + 5], "big")
            width = int.from_bytes(value[offset + 5:offset + 7], "big")
            if 0 < width <= 32768 and 0 < height <= 32768 and width * height <= 100_000_000:
                return width, height
            break
        if marker == 0xDA:
            break
        offset += length
    raise Task120Error("TELEGRAM_JPEG_STRUCTURE")


def _mp4_boxes(
    value: bytes, start: int = 0, end: int | None = None
) -> list[tuple[bytes, int, int]]:
    """Strict ISO-BMFF box walk; returned offsets delimit each box payload."""
    limit = len(value) if end is None else end
    if start < 0 or limit > len(value) or start > limit:
        raise Task120Error("TELEGRAM_MP4_BOX_RANGE")
    result: list[tuple[bytes, int, int]] = []
    offset = start
    while offset < limit:
        if limit - offset < 8:
            raise Task120Error("TELEGRAM_MP4_BOX_TRUNCATED")
        size = int.from_bytes(value[offset:offset + 4], "big")
        kind = value[offset + 4:offset + 8]
        header = 8
        if size == 1:
            if limit - offset < 16:
                raise Task120Error("TELEGRAM_MP4_BOX_TRUNCATED")
            size = int.from_bytes(value[offset + 8:offset + 16], "big")
            header = 16
        elif size == 0:
            size = limit - offset
        if size < header or offset + size > limit or not re.fullmatch(rb"[A-Za-z0-9 ]{4}", kind):
            raise Task120Error("TELEGRAM_MP4_BOX_INVALID")
        result.append((kind, offset + header, offset + size))
        offset += size
    if offset != limit:
        raise Task120Error("TELEGRAM_MP4_BOX_TRUNCATED")
    return result


def _mp4_video_metadata(value: bytes) -> dict[str, Any]:
    top = _mp4_boxes(value)
    if not top or top[0][0] != b"ftyp":
        raise Task120Error("TELEGRAM_MP4_FTYP")
    kinds = [item[0] for item in top]
    if b"moov" not in kinds or b"mdat" not in kinds:
        raise Task120Error("TELEGRAM_MP4_REQUIRED_BOX")
    ftyp = top[0]
    if ftyp[2] - ftyp[1] < 8:
        raise Task120Error("TELEGRAM_MP4_FTYP")
    brand = value[ftyp[1]:ftyp[1] + 4]
    if not re.fullmatch(rb"[A-Za-z0-9 ]{4}", brand):
        raise Task120Error("TELEGRAM_MP4_BRAND")
    moov = next(item for item in top if item[0] == b"moov")
    moov_children = _mp4_boxes(value, moov[1], moov[2])
    duration_seconds: float | None = None
    for kind, payload, box_end in moov_children:
        if kind != b"mvhd" or box_end - payload < 24:
            continue
        version = value[payload]
        if version == 0 and box_end - payload >= 20:
            timescale = int.from_bytes(value[payload + 12:payload + 16], "big")
            duration = int.from_bytes(value[payload + 16:payload + 20], "big")
        elif version == 1 and box_end - payload >= 32:
            timescale = int.from_bytes(value[payload + 20:payload + 24], "big")
            duration = int.from_bytes(value[payload + 24:payload + 32], "big")
        else:
            raise Task120Error("TELEGRAM_MP4_MVHD")
        if timescale <= 0 or duration <= 0:
            raise Task120Error("TELEGRAM_MP4_DURATION")
        duration_seconds = duration / timescale
        break
    if duration_seconds is None or not (0 < duration_seconds <= 24 * 60 * 60):
        raise Task120Error("TELEGRAM_MP4_DURATION")
    video_tracks: list[tuple[int, int]] = []
    for kind, payload, box_end in moov_children:
        if kind != b"trak":
            continue
        track_children = _mp4_boxes(value, payload, box_end)
        tkhd = next((item for item in track_children if item[0] == b"tkhd"), None)
        mdia = next((item for item in track_children if item[0] == b"mdia"), None)
        if tkhd is None or mdia is None or tkhd[2] - tkhd[1] < 8:
            continue
        mdia_children = _mp4_boxes(value, mdia[1], mdia[2])
        hdlr = next((item for item in mdia_children if item[0] == b"hdlr"), None)
        if hdlr is None or hdlr[2] - hdlr[1] < 12:
            continue
        if value[hdlr[1] + 8:hdlr[1] + 12] != b"vide":
            continue
        if tkhd[2] - tkhd[1] < 44:
            raise Task120Error("TELEGRAM_MP4_TKHD")
        matrix_raw = [
            int.from_bytes(value[offset:offset + 4], "big", signed=True)
            for offset in range(tkhd[2] - 44, tkhd[2] - 8, 4)
        ]
        a, b, c, d = matrix_raw[0], matrix_raw[1], matrix_raw[3], matrix_raw[4]
        identity_axis = (
            abs(abs(a) - 65536) <= 2 and abs(abs(d) - 65536) <= 2
            and abs(b) <= 2 and abs(c) <= 2
        )
        quarter_turn = (
            abs(a) <= 2 and abs(d) <= 2
            and abs(abs(b) - 65536) <= 2 and abs(abs(c) - 65536) <= 2
        )
        if not identity_axis and not quarter_turn:
            raise Task120Error("TELEGRAM_MP4_ROTATION_MATRIX")
        physical_width = int.from_bytes(value[tkhd[2] - 8:tkhd[2] - 4], "big") >> 16
        physical_height = int.from_bytes(value[tkhd[2] - 4:tkhd[2]], "big") >> 16
        if (
            physical_width <= 0 or physical_height <= 0
            or physical_width > 16384 or physical_height > 16384
        ):
            raise Task120Error("TELEGRAM_MP4_DIMENSIONS")
        width, height = (
            (physical_height, physical_width) if quarter_turn
            else (physical_width, physical_height)
        )
        video_tracks.append((width, height))
    if len(video_tracks) != 1:
        raise Task120Error("TELEGRAM_MP4_VIDEO_TRACK")
    width, height = video_tracks[0]
    if height <= width:
        raise Task120Error("TELEGRAM_MP4_NOT_VERTICAL")
    return {
        "ftyp": brand.decode("ascii"),
        "width": width,
        "height": height,
        "duration_ms": int(round(duration_seconds * 1000)),
        "video_tracks": 1,
    }


def _validate_media_bytes(value: bytes, kind: str) -> dict[str, Any]:
    if kind == "foto":
        if len(value) < 1000:
            raise Task120Error("TELEGRAM_JPEG_INVALID")
        width, height = _jpeg_dimensions(value)
        return {"width": width, "height": height}
    if len(value) < 10_000:
        raise Task120Error("TELEGRAM_MP4_INVALID")
    return _mp4_video_metadata(value)


def _telegram_media(
    token: str,
    item: Mapping[str, Any],
    cancel_event: threading.Event | None = None,
    reserve_check=None,
) -> bytes:
    label = "%s:%s:%d" % (item["uid"], item["kind"], int(item["order"]))
    get_url = (
        "https://api.telegram.org/bot"
        + token
        + "/getFile?"
        + urllib.parse.urlencode({"file_id": str(item["file_id"])})
    )
    last_error = ""
    for attempt in range(3):
        try:
            if cancel_event is not None and cancel_event.is_set():
                raise Task120Error("MEDIA_STAGE_CANCELLED")
            request = urllib.request.Request(
                get_url, headers={"User-Agent": "ua-art-task120-media/1"}
            )
            with urllib.request.urlopen(request, timeout=45) as response:
                metadata_raw = response.read(1024 * 1024 + 1)
                status = int(response.status)
            if status != 200 or len(metadata_raw) > 1024 * 1024:
                raise Task120Error("TELEGRAM_GETFILE_HTTP")
            metadata = json.loads(metadata_raw.decode("utf-8"))
            result = metadata.get("result") if isinstance(metadata, dict) else None
            if metadata.get("ok") is not True or not isinstance(result, dict):
                raise Task120Error("TELEGRAM_GETFILE_RESULT")
            file_path = str(result.get("file_path") or "")
            pure = pathlib.PurePosixPath(file_path)
            if (
                not file_path
                or pure.is_absolute()
                or ".." in pure.parts
                or str(pure) != file_path
            ):
                raise Task120Error("TELEGRAM_FILE_PATH")
            lowered = file_path.casefold()
            if item["kind"] == "foto":
                allowed_path = pure.parts[0] == "photos" and lowered.endswith((".jpg", ".jpeg"))
                maximum = MAX_PHOTO_BYTES
            else:
                allowed_path = pure.parts[0] in {"videos", "documents"} and lowered.endswith(".mp4")
                maximum = MAX_VIDEO_BYTES
            if not allowed_path:
                raise Task120Error("TELEGRAM_MEDIA_TYPE")
            declared = int(result.get("file_size") or 0)
            if declared < 0 or declared > maximum:
                raise Task120Error("TELEGRAM_MEDIA_SIZE")
            download_url = (
                "https://api.telegram.org/file/bot"
                + token
                + "/"
                + urllib.parse.quote(file_path, safe="/")
            )
            download_request = urllib.request.Request(
                download_url, headers={"User-Agent": "ua-art-task120-media/1"}
            )
            with urllib.request.urlopen(download_request, timeout=90) as response:
                status = int(response.status)
                chunks: list[bytes] = []
                downloaded = 0
                while downloaded <= maximum:
                    if cancel_event is not None and cancel_event.is_set():
                        raise Task120Error("MEDIA_STAGE_CANCELLED")
                    block = response.read(min(1024 * 1024, maximum + 1 - downloaded))
                    if not block:
                        break
                    downloaded += len(block)
                    if reserve_check is not None:
                        reserve_check(downloaded)
                    chunks.append(block)
                value = b"".join(chunks)
            if status != 200 or len(value) > maximum or (declared and len(value) != declared):
                raise Task120Error("TELEGRAM_DOWNLOAD_SIZE")
            _validate_media_bytes(value, str(item["kind"]))
            return value
        except Exception as exc:
            last_error = type(exc).__name__
            if attempt < 2:
                time.sleep(1 + attempt)
    raise Task120Error("TELEGRAM_MEDIA_DOWNLOAD:%s:%s" % (label, last_error))


def _stage_media(
    backup_root: pathlib.Path,
    plan: Mapping[str, Iterable[Mapping[str, Any]]],
) -> dict[str, Any]:
    stage_root = _assert_under(backup_root / "media-stage", backup_root)
    if stage_root.exists() and (not stage_root.is_dir() or stage_root.is_symlink()):
        raise Task120Error("MEDIA_STAGE_UNSAFE")
    stage_root.mkdir(parents=True, mode=0o700, exist_ok=True)
    token = _bot_token()
    items = [dict(item) for uid in TARGETS for item in plan[uid]]
    destinations = _media_destinations(plan)
    free_before = shutil.disk_usage(backup_root).free
    if free_before < 256 * 1024 * 1024:
        raise Task120Error("MEDIA_STAGE_FREE_SPACE")
    cancel_event = threading.Event()
    reserve_lock = threading.Lock()

    def reserve_check(inflight_bytes: int) -> None:
        with reserve_lock:
            # Leave rollback/headroom plus the worst case for the other three
            # workers whose payloads may not yet have reached disk.
            needed = 128 * 1024 * 1024 + inflight_bytes + 3 * MAX_VIDEO_BYTES
            if shutil.disk_usage(backup_root).free < needed:
                cancel_event.set()
                raise Task120Error("MEDIA_STAGE_FREE_SPACE")

    def fetch(item: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        if cancel_event.is_set():
            raise Task120Error("MEDIA_STAGE_CANCELLED")
        value = _telegram_media(token, item, cancel_event, reserve_check)
        if item["kind"] == "foto":
            relative = "video/foto/%s/%03d.jpg" % (item["uid"], int(item["order"]))
        else:
            relative = "video/%s.mp4" % item["uid"]
        if relative not in destinations:
            raise Task120Error("MEDIA_STAGE_DESTINATION")
        staged = _assert_under(stage_root / relative, stage_root)
        with reserve_lock:
            if cancel_event.is_set():
                raise Task120Error("MEDIA_STAGE_CANCELLED")
            if shutil.disk_usage(backup_root).free < len(value) + 128 * 1024 * 1024:
                cancel_event.set()
                raise Task120Error("MEDIA_STAGE_FREE_SPACE")
            _atomic(staged, value, 0o600)
        readback = _stream_regular_state(staged)
        if readback["sha256"] != _sha(value) or readback["size"] != len(value):
            raise Task120Error("MEDIA_STAGE_READBACK:" + relative)
        dimensions = _validate_media_bytes(value, str(item["kind"]))
        return relative, {
            "sha256": _sha(value), "size": len(value), "kind": item["kind"],
            "order": int(item["order"]), "mode": 0o644, **dimensions,
        }

    evidence: dict[str, Any] = {}
    total = 0
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    futures = {executor.submit(fetch, item): item for item in items}
    try:
        for future in concurrent.futures.as_completed(futures):
            relative, metadata = future.result()
            total += int(metadata["size"])
            if total > free_before - 128 * 1024 * 1024:
                raise Task120Error("MEDIA_STAGE_FREE_SPACE")
            evidence[relative] = metadata
    except Exception:
        cancel_event.set()
        for future in futures:
            future.cancel()
        executor.shutdown(wait=True, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True, cancel_futures=True)
    if shutil.disk_usage(ROOT).free < total + 128 * 1024 * 1024:
        raise Task120Error("MEDIA_PROMOTE_FREE_SPACE")
    if len(evidence) != sum(sum(value.values()) for value in EXPECTED_MEDIA_COUNTS.values()):
        raise Task120Error("MEDIA_STAGE_COUNT")
    _atomic_json(stage_root / "manifest.json", {"task_id": TASK_ID, "files": evidence})
    return {"root": str(stage_root), "files": evidence}


def _write_media_intent(
    manifest_path: pathlib.Path,
    manifest: Mapping[str, Any],
    staged: Mapping[str, Any],
) -> dict[str, Any]:
    files = staged.get("files")
    media = manifest.get("media")
    preimage = media.get("entries") if isinstance(media, dict) else None
    if not isinstance(files, dict) or not isinstance(preimage, dict):
        raise Task120Error("MEDIA_INTENT_INPUT")
    if not set(files).issubset(set(preimage)):
        raise Task120Error("MEDIA_INTENT_SCOPE")
    intent = {
        "task_id": TASK_ID,
        "backup_manifest_sha256": _sha(
            _read_regular(manifest_path, 64 * 1024 * 1024)[0]
        ),
        "files": {
            relative: {"before": preimage[relative], "after": files[relative]}
            for relative in sorted(files)
        },
        "created_at": _utc_now(),
    }
    _atomic_json(manifest_path.with_name(MEDIA_INTENT_NAME), intent)
    return intent


def _path_state(path: pathlib.Path, maximum: int) -> dict[str, Any]:
    if not os.path.lexists(str(path)):
        return {"exists": False}
    value, info = _read_regular(path, maximum)
    return {
        "exists": True,
        "sha256": _sha(value),
        "size": len(value),
        "mode": stat.S_IMODE(info.st_mode),
    }


def _promote_media(
    staged: Mapping[str, Any],
    manifest: Mapping[str, Any],
    intent: Mapping[str, Any],
) -> dict[str, Any]:
    stage_root = pathlib.Path(str(staged.get("root") or "")).resolve()
    files = staged.get("files")
    if not isinstance(files, dict):
        raise Task120Error("MEDIA_STAGE_MANIFEST")
    intent_files = intent.get("files")
    media = manifest.get("media")
    preimage = media.get("entries") if isinstance(media, dict) else None
    if (
        not isinstance(intent_files, dict)
        or not isinstance(preimage, dict)
        or set(intent_files) != set(files)
    ):
        raise Task120Error("MEDIA_INTENT_IDENTITY")
    written: list[str] = []
    unchanged: list[str] = []
    hashes: dict[str, Any] = {}
    for relative, expected in sorted(files.items()):
        maximum = MAX_VIDEO_BYTES if relative.endswith(".mp4") else MAX_PHOTO_BYTES
        source = _assert_under(stage_root / relative, stage_root)
        value, _ = _read_regular(source, maximum)
        if _sha(value) != expected.get("sha256") or len(value) != expected.get("size"):
            raise Task120Error("MEDIA_STAGE_CHANGED:" + relative)
        destination = _lexical_under(ROOT, relative)
        if destination.parent.exists() and (
            not destination.parent.is_dir() or destination.parent.is_symlink()
        ):
            raise Task120Error("MEDIA_DESTINATION_PARENT_UNSAFE:" + relative)
        destination.parent.mkdir(parents=True, mode=0o755, exist_ok=True)
        current = _path_state(destination, maximum)
        before = preimage.get(relative)
        post = {
            "exists": True,
            "sha256": expected["sha256"],
            "size": expected["size"],
            "mode": 0o644,
        }
        current_core = {
            key: current[key] for key in ("exists", "sha256", "size", "mode") if key in current
        }
        before_core = {
            key: before[key] for key in ("exists", "sha256", "size", "mode") if key in before
        } if isinstance(before, dict) else {}
        if current_core not in (before_core, post):
            raise Task120Error("MEDIA_PROMOTE_CAS:" + relative)
        if current_core == post:
            unchanged.append(relative)
        else:
            _atomic_live(destination, value, 0o644)
            written.append(relative)
        final_state = _path_state(destination, maximum)
        if final_state != post:
            raise Task120Error("MEDIA_PROMOTE_READBACK:" + relative)
        hashes[relative] = final_state
    return {
        "status": "PASS",
        "written": written,
        "already_exact": unchanged,
        "files": hashes,
        "photo_counts": {"UA-0017": 39, "UA-0018": 36},
        "video_counts": {"UA-0017": 0, "UA-0018": 1},
    }


def _set_publication_flags(manifest: Mapping[str, Any]) -> dict[str, Any]:
    preimage = _flags_from_manifest(manifest)
    spec_preimage = manifest.get("spec_preimage")
    if not isinstance(spec_preimage, dict) or set(spec_preimage) != set(TARGETS):
        raise Task120Error("BACKUP_SPEC_PREIMAGE_INVALID")
    spec_path = pathlib.Path(str(manifest["databases"]["spec"]["source"]))
    connection = _connect(DB, readonly=False)
    try:
        connection.execute("ATTACH DATABASE ? AS ua120_spec", (str(spec_path),))
        _assert_atomic_journal_modes(connection)
        connection.execute("BEGIN IMMEDIATE")
        _assert_spec_jobs_idle(connection, "ua120_spec")
        rows = _rows_by_uid(connection)
        _validate_bindings(rows, connection)
        for uid in TARGETS:
            public = _row_public(rows[uid])
            if public["row_digest"] != preimage[uid]["row_digest"]:
                raise Task120Error("TARGET_ROW_CHANGED_SINCE_BACKUP:" + uid)
        inserted_specs: list[str] = []
        for uid in TARGETS:
            current_spec = _spec_state(connection, "ua120_spec", uid)
            if current_spec != spec_preimage[uid]:
                raise Task120Error("SPEC_CHANGED_SINCE_BACKUP:" + uid)
            if current_spec.get("state") == "EMPTY":
                _insert_specs(connection, "ua120_spec", uid)
                inserted_specs.append(uid)
            elif current_spec.get("state") != "EXACT":
                raise Task120Error("SPEC_PREIMAGE_STATE_INVALID:" + uid)
        for uid in TARGETS:
            binding = TARGET_BINDINGS[uid]
            before = preimage[uid]
            cursor = connection.execute(
                "UPDATE cars SET published=1,publish_pending=0 "
                "WHERE id=? AND UPPER(TRIM(auto_number))=? AND UPPER(TRIM(vin))=? "
                "AND published IS ? AND publish_pending IS ?",
                (
                    binding["id"], uid, binding["vin"],
                    before["published"], before["publish_pending"],
                ),
            )
            if cursor.rowcount != 1:
                raise Task120Error("TARGET_FLAG_CAS_FAILED:" + uid)
        connection.commit()
        final_rows = _rows_by_uid(connection)
        for uid in TARGETS:
            if final_rows[uid].get("published") != 1 or final_rows[uid].get("publish_pending") != 0:
                raise Task120Error("TARGET_FLAG_READBACK:" + uid)
        final_specs = {uid: _spec_state(connection, "ua120_spec", uid) for uid in TARGETS}
        if any(item.get("state") != "EXACT" for item in final_specs.values()):
            raise Task120Error("SPEC_INSERT_READBACK")
        return {
            "rows": {uid: _row_public(final_rows[uid]) for uid in TARGETS},
            "inserted_specs": inserted_specs,
            "spec_states": final_specs,
            "database_digests": {
                "main": _database_digest(DB),
                "spec": _database_digest(spec_path),
            },
        }
    except Exception:
        with contextlib.suppress(Exception):
            connection.rollback()
        raise
    finally:
        connection.close()


def _restore_flags(
    manifest: Mapping[str, Any], connection: sqlite3.Connection | None = None
) -> dict[str, Any]:
    preimage = _flags_from_manifest(manifest)
    spec_preimage = manifest.get("spec_preimage")
    if not isinstance(spec_preimage, dict) or set(spec_preimage) != set(TARGETS):
        raise Task120Error("BACKUP_SPEC_PREIMAGE_INVALID")
    spec_path = pathlib.Path(str(manifest["databases"]["spec"]["source"]))
    owned = connection is None
    if connection is None:
        connection = _connect(DB, readonly=False)
    restored: list[str] = []
    removed_specs: list[str] = []
    try:
        if owned:
            connection.execute("ATTACH DATABASE ? AS ua120_spec", (str(spec_path),))
            _assert_atomic_journal_modes(connection)
            connection.execute("BEGIN IMMEDIATE")
        elif not connection.in_transaction:
            raise Task120Error("ROLLBACK_DATABASE_FENCE_MISSING")
        _assert_spec_jobs_idle(connection, "ua120_spec")
        rows = _rows_by_uid(connection)
        _validate_bindings(rows, connection)
        for uid in TARGETS:
            normalized = dict(rows[uid])
            normalized["published"] = preimage[uid]["published"]
            normalized["publish_pending"] = preimage[uid]["publish_pending"]
            if _row_public(normalized)["row_digest"] != preimage[uid]["row_digest"]:
                raise Task120Error("ROLLBACK_TARGET_ROW_CONFLICT:" + uid)
        for uid in TARGETS:
            before_spec = spec_preimage[uid]
            current_spec = _spec_state(connection, "ua120_spec", uid)
            state = before_spec.get("state")
            if state == "EMPTY":
                if current_spec.get("state") == "EXACT":
                    connection.execute(
                        "DELETE FROM ua120_spec.additional_specification_meta WHERE car_uid=?",
                        (uid,),
                    )
                    connection.execute(
                        "DELETE FROM ua120_spec.additional_specification WHERE car_uid=?",
                        (uid,),
                    )
                    removed_specs.append(uid)
                elif current_spec.get("state") != "EMPTY":
                    raise Task120Error("ROLLBACK_SPEC_CONFLICT:" + uid)
            elif state == "EXACT":
                if current_spec != before_spec:
                    raise Task120Error("ROLLBACK_SPEC_CONFLICT:" + uid)
            else:
                raise Task120Error("ROLLBACK_SPEC_PREIMAGE_STATE:" + uid)
        for uid in TARGETS:
            current = rows[uid]
            desired = preimage[uid]
            pair = (current.get("published"), current.get("publish_pending"))
            wanted = (desired.get("published"), desired.get("publish_pending"))
            if pair == wanted:
                continue
            if pair != (1, 0):
                raise Task120Error("ROLLBACK_FLAG_CONFLICT:" + uid)
            cursor = connection.execute(
                "UPDATE cars SET published=?,publish_pending=? "
                "WHERE id=? AND UPPER(TRIM(auto_number))=? AND UPPER(TRIM(vin))=? "
                "AND published=1 AND publish_pending=0",
                (
                    desired["published"], desired["publish_pending"],
                    TARGET_BINDINGS[uid]["id"], uid, TARGET_BINDINGS[uid]["vin"],
                ),
            )
            if cursor.rowcount != 1:
                raise Task120Error("ROLLBACK_FLAG_CAS_FAILED:" + uid)
            restored.append(uid)
        if owned:
            connection.commit()
        after = _rows_by_uid(connection)
        for uid in TARGETS:
            if (
                after[uid].get("published") != preimage[uid].get("published")
                or after[uid].get("publish_pending") != preimage[uid].get("publish_pending")
            ):
                raise Task120Error("ROLLBACK_FLAG_READBACK:" + uid)
        final_specs = {uid: _spec_state(connection, "ua120_spec", uid) for uid in TARGETS}
        if final_specs != spec_preimage:
            raise Task120Error("ROLLBACK_SPEC_READBACK")
        return {
            "restored": restored,
            "removed_specs": removed_specs,
            "spec_states": final_specs,
            "status": "PASS",
        }
    except Exception:
        if owned:
            with contextlib.suppress(Exception):
                connection.rollback()
        raise
    finally:
        if owned:
            connection.close()


def _allowed_web_relative(relative: str) -> bool:
    pure = pathlib.PurePosixPath(relative)
    if len(pure.parts) != 2 or pure.parts[0] not in {"site", "video"}:
        return False
    name = pure.name
    if name == "katalog.html":
        return True
    for uid in TARGETS:
        if name in {uid + ".html", uid + "-diag.html"}:
            return True
        if re.fullmatch(re.escape(uid) + r"-[0-9a-f]{6,10}\.html", name, re.I):
            return True
    return False


def _prevalidate_web_backup(
    backup_root: pathlib.Path, manifest: Mapping[str, Any]
) -> dict[str, Any]:
    entries = manifest.get("html")
    if not isinstance(entries, dict):
        raise Task120Error("BACKUP_HTML_INVALID")
    checked = 0
    for relative, item in entries.items():
        if not _allowed_web_relative(relative) or not item.get("exists"):
            continue
        stored = _assert_under(backup_root / str(item.get("stored") or ""), backup_root)
        packed, _ = _read_regular(stored, MAX_HTML_BYTES + 1024 * 1024)
        if _sha(packed) != item.get("stored_sha256"):
            raise Task120Error("ROLLBACK_STORED_SHA:" + relative)
        value = gzip.decompress(packed)
        if len(value) > MAX_HTML_BYTES or _sha(value) != item.get("sha256"):
            raise Task120Error("ROLLBACK_HTML_SHA:" + relative)
        checked += 1
    return {"status": "PASS", "checked": checked}


def _prevalidate_database_backups(
    backup_root: pathlib.Path, manifest: Mapping[str, Any]
) -> dict[str, Any]:
    databases = manifest.get("databases")
    if not isinstance(databases, dict) or set(databases) != {"main", "spec"}:
        raise Task120Error("BACKUP_DATABASES_INVALID")
    checked: dict[str, Any] = {}
    for name in ("main", "spec"):
        item = databases[name]
        if not isinstance(item, dict):
            raise Task120Error("BACKUP_DATABASE_INVALID:" + name)
        path = _assert_under(backup_root / str(item.get("stored") or ""), backup_root)
        state = _stream_regular_state(path)
        if (
            state.get("sha256") != item.get("sha256")
            or state.get("size") != item.get("size")
            or _quick_check(path) != "ok"
            or _database_digest(path) != item.get("logical_digest")
        ):
            raise Task120Error("BACKUP_DATABASE_PAYLOAD:" + name)
        checked[name] = state
    return {"status": "PASS", "databases": checked}


def _restore_web(backup_root: pathlib.Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    entries = manifest.get("html")
    if not isinstance(entries, dict):
        raise Task120Error("BACKUP_HTML_INVALID")
    current = _html_manifest()
    protected_conflicts = []
    for relative, expected in entries.items():
        if _allowed_web_relative(relative):
            continue
        if current.get(relative) != _html_preimage_state(expected):
            protected_conflicts.append(relative)
    extra_protected = [
        relative for relative in current
        if relative not in entries and not _allowed_web_relative(relative)
    ]
    stage_root = pathlib.Path(tempfile.mkdtemp(prefix="rollback-web-stage-", dir=backup_root))
    os.chmod(stage_root, 0o700)
    staged_payloads: dict[str, pathlib.Path] = {}
    controlled_current: dict[str, dict[str, Any]] = {}
    for relative, item in sorted(entries.items()):
        if not _allowed_web_relative(relative):
            continue
        controlled_current[relative] = current.get(relative, {"exists": False})
        if item.get("exists"):
            stored = _assert_under(backup_root / str(item.get("stored") or ""), backup_root)
            packed, _ = _read_regular(stored, MAX_HTML_BYTES + 1024 * 1024)
            if _sha(packed) != item.get("stored_sha256"):
                raise Task120Error("ROLLBACK_STORED_SHA:" + relative)
            value = gzip.decompress(packed)
            if len(value) > MAX_HTML_BYTES or _sha(value) != item.get("sha256"):
                raise Task120Error("ROLLBACK_HTML_SHA:" + relative)
            staged = stage_root / (_sha(relative.encode("utf-8")) + ".html")
            _atomic(staged, value, 0o600)
            staged_payloads[relative] = staged
    extra_controlled = {
        relative: metadata for relative, metadata in current.items()
        if relative not in entries and _allowed_web_relative(relative)
    }
    renderer_temps = _renderer_temp_paths()
    if renderer_temps and not (backup_root / PUBLISH_STARTED_NAME).is_file():
        raise Task120Error("ROLLBACK_RENDERER_TEMP_WITHOUT_INTENT")
    # Every stored web preimage was validated before this function, and all
    # current controlled states were CAS-fenced by _prevalidate_rollback_state.
    # Remove only exact renderer/TASK120 crash-residue names created after the
    # fresh backup, before restoring the authoritative target paths.
    for temporary in renderer_temps:
        temporary.unlink()
        _fsync_dir(temporary.parent)
    restored: list[str] = []
    removed: list[str] = []
    for relative, item in entries.items():
        if not _allowed_web_relative(relative):
            continue
        path = _lexical_under(ROOT, relative)
        if _path_state(path, MAX_HTML_BYTES) != controlled_current[relative]:
            raise Task120Error("ROLLBACK_WEB_RACE:" + relative)
        if item.get("exists"):
            value, _ = _read_regular(staged_payloads[relative], MAX_HTML_BYTES)
            if _sha(value) != item.get("sha256"):
                raise Task120Error("ROLLBACK_HTML_STAGE_SHA:" + relative)
            if controlled_current[relative] != _html_preimage_state(item):
                _atomic_live(path, value, int(item.get("mode") or 0o644))
                restored.append(relative)
        elif path.exists():
            if not path.is_file() or path.is_symlink():
                raise Task120Error("ROLLBACK_NEW_TARGET_UNSAFE:" + relative)
            path.unlink()
            _fsync_dir(path.parent)
            removed.append(relative)
    for root in SITE_ROOTS:
        for path in root.glob("*.html"):
            relative = str(path.relative_to(ROOT))
            if relative not in entries and _allowed_web_relative(relative):
                if _path_state(path, MAX_HTML_BYTES) != extra_controlled.get(relative):
                    raise Task120Error("ROLLBACK_NEW_WEB_RACE:" + relative)
                if path.name == "katalog.html":
                    raise Task120Error("ROLLBACK_CATALOG_PREIMAGE_MISSING")
                path.unlink()
                removed.append(relative)
    after = _html_manifest()
    mismatches = [
        relative for relative, expected in entries.items()
        if _allowed_web_relative(relative)
        and after.get(relative) != _html_preimage_state(expected)
    ]
    if mismatches:
        raise Task120Error("ROLLBACK_WEB_READBACK:" + ",".join(mismatches[:12]))
    return {
        "status": "PASS",
        "restored": restored,
        "removed": removed,
        "protected_drift": sorted(protected_conflicts + extra_protected),
    }


def _restore_media(backup_root: pathlib.Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    media = manifest.get("media")
    if not isinstance(media, dict):
        raise Task120Error("BACKUP_MEDIA_INVALID")
    entries = media.get("entries")
    directories = media.get("directories")
    if not isinstance(entries, dict) or not isinstance(directories, dict):
        raise Task120Error("BACKUP_MEDIA_INVALID")
    intent_files: dict[str, Any] = {}
    orphan_temps: list[pathlib.Path] = []
    intent_path = backup_root / MEDIA_INTENT_NAME
    if intent_path.exists():
        intent_raw, _ = _read_regular(intent_path, 64 * 1024 * 1024)
        intent = json.loads(intent_raw.decode("utf-8"))
        manifest_sha = _sha(_read_regular(backup_root / "manifest.json", 64 * 1024 * 1024)[0])
        if (
            not isinstance(intent, dict)
            or intent.get("task_id") != TASK_ID
            or intent.get("backup_manifest_sha256") != manifest_sha
        ):
            raise Task120Error("ROLLBACK_MEDIA_INTENT_IDENTITY")
        raw_intent_files = intent.get("files")
        if not isinstance(raw_intent_files, dict) or not set(raw_intent_files).issubset(entries):
            raise Task120Error("ROLLBACK_MEDIA_INTENT_SCOPE")
        intent_files = raw_intent_files
    allowed = set(entries)
    for relative, item in sorted(directories.items()):
        folder = _lexical_under(ROOT, relative + "/.scope").parent
        exists = os.path.lexists(str(folder))
        if exists:
            info = folder.lstat()
            if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise Task120Error("ROLLBACK_MEDIA_DIRECTORY_UNSAFE:" + relative)
            mode = stat.S_IMODE(info.st_mode)
            if item.get("exists"):
                if mode != item.get("mode"):
                    raise Task120Error("ROLLBACK_MEDIA_DIRECTORY_MODE:" + relative)
            elif intent_files and mode != 0o755:
                raise Task120Error("ROLLBACK_MEDIA_DIRECTORY_MODE:" + relative)
        elif item.get("exists"):
            raise Task120Error("ROLLBACK_MEDIA_DIRECTORY_MISSING:" + relative)
    for uid in TARGETS:
        folder = ROOT / "video/foto" / uid
        if os.path.lexists(str(folder)):
            info = folder.lstat()
            if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise Task120Error("ROLLBACK_MEDIA_DIRECTORY_UNSAFE:" + uid)
            unexpected = [
                str(path.relative_to(ROOT)) for path in folder.iterdir()
                if str(path.relative_to(ROOT)) not in allowed
                and not (
                    path.name == "." + path.name.removeprefix(".").removesuffix(".task120.tmp")
                    + ".task120.tmp"
                    and path.name.removeprefix(".").removesuffix(".task120.tmp")
                    in {pathlib.PurePosixPath(item).name for item in intent_files}
                )
            ]
            if unexpected:
                raise Task120Error("ROLLBACK_MEDIA_CONFLICT:" + ",".join(unexpected[:8]))
        for path in _target_video_candidates(uid):
            relative = str(path.relative_to(ROOT))
            if relative not in allowed:
                raise Task120Error("ROLLBACK_MEDIA_CONFLICT:" + relative)
    # Validate every target current state and every stored preimage before the
    # first mutation.  This prevents a late conflict/corrupt backup from
    # producing a predictable partial rollback.
    stage_root = pathlib.Path(tempfile.mkdtemp(prefix="rollback-media-stage-", dir=backup_root))
    os.chmod(stage_root, 0o700)
    validated: dict[str, tuple[dict[str, Any], dict[str, Any], pathlib.Path | None]] = {}
    for relative, item in sorted(entries.items()):
        path = _lexical_under(ROOT, relative)
        maximum = MAX_VIDEO_BYTES if relative.endswith(".mp4") else MAX_PHOTO_BYTES
        current_state = _path_state(path, maximum)
        current_core = {
            key: current_state[key] for key in ("exists", "sha256", "size", "mode")
            if key in current_state
        }
        before_core = {
            key: item[key] for key in ("exists", "sha256", "size", "mode") if key in item
        }
        allowed_states = [before_core]
        if relative in intent_files:
            after = intent_files[relative].get("after")
            if not isinstance(after, dict):
                raise Task120Error("ROLLBACK_MEDIA_INTENT_ENTRY:" + relative)
            allowed_states.append(
                {
                    "exists": True,
                    "sha256": after.get("sha256"),
                    "size": after.get("size"),
                    "mode": after.get("mode"),
                }
            )
        if current_core not in allowed_states:
            raise Task120Error("ROLLBACK_MEDIA_CONCURRENT_CHANGE:" + relative)
        if item.get("exists"):
            stored = _assert_under(backup_root / str(item.get("stored") or ""), backup_root)
            packed, _ = _read_regular(stored, maximum + 1024 * 1024)
            if _sha(packed) != item.get("stored_sha256"):
                raise Task120Error("ROLLBACK_MEDIA_STORED_SHA:" + relative)
            value = gzip.decompress(packed)
            if len(value) > maximum or _sha(value) != item.get("sha256"):
                raise Task120Error("ROLLBACK_MEDIA_SHA:" + relative)
            staged_preimage = stage_root / (_sha(relative.encode("utf-8")) + ".bin")
            _atomic(staged_preimage, value, 0o600)
        else:
            staged_preimage = None
        validated[relative] = (current_core, before_core, staged_preimage)

        live_temp = path.with_name("." + path.name + ".task120.tmp")
        if os.path.lexists(str(live_temp)):
            if relative not in intent_files:
                raise Task120Error("ROLLBACK_MEDIA_TEMP_CONFLICT:" + relative)
            _read_regular(live_temp, maximum)
            orphan_temps.append(live_temp)

    for temporary in orphan_temps:
        temporary.unlink()
        _fsync_dir(temporary.parent)

    restored: list[str] = []
    removed: list[str] = []
    for relative, item in sorted(entries.items()):
        path = _lexical_under(ROOT, relative)
        maximum = MAX_VIDEO_BYTES if relative.endswith(".mp4") else MAX_PHOTO_BYTES
        current_core, before_core, staged_preimage = validated[relative]
        if _path_state(path, maximum) != current_core:
            raise Task120Error("ROLLBACK_MEDIA_RACE:" + relative)
        if item.get("exists"):
            if staged_preimage is None:
                raise Task120Error("ROLLBACK_MEDIA_STAGE_MISSING:" + relative)
            preimage_value, _ = _read_regular(staged_preimage, maximum)
            if len(preimage_value) > maximum or _sha(preimage_value) != item.get("sha256"):
                raise Task120Error("ROLLBACK_MEDIA_STAGE_SHA:" + relative)
            if current_core != before_core:
                path.parent.mkdir(parents=True, mode=0o755, exist_ok=True)
                _atomic_live(path, preimage_value, int(item.get("mode") or 0o644))
                restored.append(relative)
        elif current_core.get("exists"):
            path.unlink()
            _fsync_dir(path.parent)
            removed.append(relative)
    for relative, item in sorted(directories.items(), reverse=True):
        folder = _lexical_under(ROOT, relative + "/.scope").parent
        if item.get("exists"):
            if not folder.is_dir() or folder.is_symlink():
                raise Task120Error("ROLLBACK_MEDIA_DIRECTORY_MISSING:" + relative)
        elif os.path.lexists(str(folder)):
            if not folder.is_dir() or folder.is_symlink() or any(folder.iterdir()):
                raise Task120Error("ROLLBACK_MEDIA_DIRECTORY_CONFLICT:" + relative)
            folder.rmdir()
            _fsync_dir(folder.parent)
    for relative, item in entries.items():
        path = _lexical_under(ROOT, relative)
        if bool(os.path.lexists(str(path))) != bool(item.get("exists")):
            raise Task120Error("ROLLBACK_MEDIA_READBACK:" + relative)
        if item.get("exists"):
            value, _ = _read_regular(
                path, MAX_VIDEO_BYTES if relative.endswith(".mp4") else MAX_PHOTO_BYTES
            )
            if (
                _sha(value) != item.get("sha256")
                or stat.S_IMODE(path.lstat().st_mode) != item.get("mode")
            ):
                raise Task120Error("ROLLBACK_MEDIA_READBACK:" + relative)
    return {
        "status": "PASS", "restored": restored, "removed": removed,
        "validated_stage": str(stage_root.relative_to(backup_root)),
    }


def _prevalidate_target_database_state(
    manifest: Mapping[str, Any], connection: sqlite3.Connection | None = None
) -> dict[str, Any]:
    preimage = _flags_from_manifest(manifest)
    spec_preimage = manifest.get("spec_preimage")
    if not isinstance(spec_preimage, dict) or set(spec_preimage) != set(TARGETS):
        raise Task120Error("BACKUP_SPEC_PREIMAGE_INVALID")
    spec_source = pathlib.Path(str(manifest["databases"]["spec"]["source"]))
    owned = connection is None
    if connection is None:
        connection = _connect(DB, readonly=True)
    try:
        if owned:
            connection.execute("ATTACH DATABASE ? AS ua120_spec", (str(spec_source),))
        _assert_spec_jobs_idle(connection, "ua120_spec")
        rows = _rows_by_uid(connection)
        _validate_bindings(rows, connection)
        phases: set[str] = set()
        spec_states: dict[str, Any] = {}
        for uid in TARGETS:
            wanted = (preimage[uid]["published"], preimage[uid]["publish_pending"])
            current_pair = (rows[uid].get("published"), rows[uid].get("publish_pending"))
            if current_pair == wanted:
                flag_phase = "PREIMAGE"
            elif current_pair == (1, 0):
                flag_phase = "TASK120_POSTIMAGE"
            else:
                raise Task120Error("ROLLBACK_TARGET_FLAGS_CONFLICT:" + uid)
            phases.add(flag_phase)
            normalized = dict(rows[uid])
            normalized["published"], normalized["publish_pending"] = wanted
            if _row_public(normalized)["row_digest"] != preimage[uid]["row_digest"]:
                raise Task120Error("ROLLBACK_TARGET_ROW_CONFLICT:" + uid)
            current_spec = _spec_state(connection, "ua120_spec", uid)
            before_spec = spec_preimage[uid]
            if before_spec.get("state") == "EMPTY":
                if current_spec.get("state") not in {"EMPTY", "EXACT"}:
                    raise Task120Error("ROLLBACK_TARGET_SPEC_CONFLICT:" + uid)
                spec_phase = (
                    "PREIMAGE" if current_spec.get("state") == "EMPTY"
                    else "TASK120_POSTIMAGE"
                )
                if spec_phase != flag_phase:
                    raise Task120Error("ROLLBACK_TARGET_DB_PHASE_MIXED:" + uid)
            elif current_spec != before_spec:
                raise Task120Error("ROLLBACK_TARGET_SPEC_CONFLICT:" + uid)
            spec_states[uid] = current_spec
        if len(phases) != 1:
            raise Task120Error("ROLLBACK_TARGET_PHASE_MIXED")
        return {
            "status": "PASS",
            "phase": next(iter(phases)),
            "spec_states": spec_states,
            "jobs": "IDLE",
        }
    finally:
        if owned:
            connection.close()


def _prevalidate_rollback_state(
    manifest: Mapping[str, Any], connection: sqlite3.Connection | None = None
) -> dict[str, Any]:
    """Fence rollback before the first write so no concurrent publisher is erased."""
    target = _prevalidate_target_database_state(manifest, connection)
    drift: list[str] = []
    try:
        runtime_now = _runtime_hashes()
        if runtime_now != manifest.get("runtime"):
            drift.append("RUNTIME_CHANGED")
    except Exception as exc:
        runtime_now = {}
        drift.append("RUNTIME:" + type(exc).__name__ + ":" + str(exc))
    preimage = _flags_from_manifest(manifest)
    main_before = str(manifest["databases"]["main"]["logical_digest"])
    main_normalized = _database_digest(DB, normalized_flags=preimage)
    if main_normalized != main_before:
        drift.append("CRM_OUTSIDE_TARGET_FLAGS_CHANGED")
    spec_source = pathlib.Path(str(manifest["databases"]["spec"]["source"]))
    spec_preimage = manifest.get("spec_preimage")
    if not isinstance(spec_preimage, dict) or set(spec_preimage) != set(TARGETS):
        raise Task120Error("BACKUP_SPEC_PREIMAGE_INVALID")
    spec_before = str(manifest["databases"]["spec"]["logical_digest"])
    spec_normalized = _database_digest(spec_source, normalized_specs=spec_preimage)
    if spec_normalized != spec_before:
        drift.append("SPEC_OUTSIDE_TARGET_ROWS_CHANGED")
    protected_before = str(manifest.get("protected_media_digest") or "")
    ignored_media_temps: set[str] = set()
    intent_path = pathlib.Path(str(manifest.get("backup_root") or "")) / MEDIA_INTENT_NAME
    if intent_path.is_file():
        intent_raw, _ = _read_regular(intent_path, 64 * 1024 * 1024)
        intent = json.loads(intent_raw.decode("utf-8"))
        manifest_path = pathlib.Path(str(manifest.get("backup_root") or "")) / "manifest.json"
        manifest_sha = _sha(_read_regular(manifest_path, 64 * 1024 * 1024)[0])
        if (
            not isinstance(intent, dict)
            or intent.get("task_id") != TASK_ID
            or intent.get("backup_manifest_sha256") != manifest_sha
            or not isinstance(intent.get("files"), dict)
        ):
            raise Task120Error("ROLLBACK_MEDIA_INTENT_IDENTITY")
        for relative in intent["files"]:
            path = _lexical_under(ROOT, relative)
            ignored_media_temps.add(
                str(path.with_name("." + path.name + ".task120.tmp").relative_to(ROOT))
            )
    protected_now = _protected_media_digest(ignored_media_temps)
    if not SHA_RE.fullmatch(protected_before) or protected_now != protected_before:
        drift.append("PROTECTED_MEDIA_CHANGED")
    entries = manifest.get("html")
    if not isinstance(entries, dict):
        raise Task120Error("BACKUP_HTML_INVALID")
    current = _html_manifest()
    postimage_entries: dict[str, Any] | None = None
    postimage_path = pathlib.Path(str(manifest.get("backup_root") or "")) / POSTIMAGE_NAME
    if postimage_path.is_file():
        raw_postimage, _ = _read_regular(postimage_path, 64 * 1024 * 1024)
        postimage = json.loads(raw_postimage.decode("utf-8"))
        manifest_path = pathlib.Path(str(manifest.get("backup_root") or "")) / "manifest.json"
        manifest_sha = _sha(_read_regular(manifest_path, 64 * 1024 * 1024)[0])
        if (
            not isinstance(postimage, dict)
            or postimage.get("task_id") != TASK_ID
            or postimage.get("backup_manifest_sha256") != manifest_sha
            or not isinstance(postimage.get("html"), dict)
        ):
            raise Task120Error("ROLLBACK_POSTIMAGE_IDENTITY")
        postimage_entries = postimage["html"]
    for relative, expected in entries.items():
        actual = current.get(relative)
        if actual == _html_preimage_state(expected):
            continue
        if not _allowed_web_relative(relative):
            drift.append("PROTECTED_HTML_CHANGED:" + relative)
            continue
        if not actual or not actual.get("exists"):
            raise Task120Error("ROLLBACK_WEB_CONCURRENT_CHANGE:" + relative)
        if postimage_entries is not None:
            if actual != postimage_entries.get(relative):
                raise Task120Error("ROLLBACK_WEB_POSTIMAGE_CAS:" + relative)
            continue
        path = _lexical_under(ROOT, relative)
        name = path.name
        if name == "katalog.html":
            source = path.read_text(encoding="utf-8")
            if (
                _catalog_ids(source) != EXPECTED_PUBLIC_IDS
                or _catalog_card_counts(source) != {uid: 1 for uid in EXPECTED_PUBLIC_IDS}
                or _catalog_href_counts(source) != {uid: 2 for uid in EXPECTED_PUBLIC_IDS}
            ):
                raise Task120Error("ROLLBACK_CATALOG_UNRECOGNIZED:" + relative)
            continue
        matched = re.fullmatch(r"(UA-001[78])(?:-[0-9a-f]{6,10})?(\.html)", name, re.I)
        diagnostic = False
        if not matched:
            matched = re.fullmatch(r"(UA-001[78])-diag(\.html)", name, re.I)
            diagnostic = True
        if not matched:
            raise Task120Error("ROLLBACK_WEB_SCOPE:" + relative)
        uid = matched.group(1).upper()
        contract = _page_contract(path, uid, TARGET_BINDINGS[uid]["vin"], diagnostic=diagnostic)
        if contract["errors"]:
            raise Task120Error("ROLLBACK_PAGE_UNRECOGNIZED:" + relative)
    for relative, actual in current.items():
        if relative in entries:
            continue
        if not _allowed_web_relative(relative):
            drift.append("NEW_PROTECTED_HTML:" + relative)
            continue
        if not actual.get("exists"):
            raise Task120Error("ROLLBACK_NEW_HTML_INVALID:" + relative)
        if postimage_entries is not None:
            if actual != postimage_entries.get(relative):
                raise Task120Error("ROLLBACK_NEW_HTML_POSTIMAGE_CAS:" + relative)
            continue
        path = _lexical_under(ROOT, relative)
        match = re.fullmatch(r"(UA-001[78])-[0-9a-f]{6,10}\.html", path.name, re.I)
        if not match:
            raise Task120Error("ROLLBACK_NEW_HTML_SCOPE:" + relative)
        uid = match.group(1).upper()
        if _page_contract(path, uid, TARGET_BINDINGS[uid]["vin"])["errors"]:
            raise Task120Error("ROLLBACK_NEW_PAGE_UNRECOGNIZED:" + relative)
    return {
        "status": "PASS" if not drift else "DRIFT",
        "drift": sorted(drift),
        "runtime": "UNCHANGED" if runtime_now == manifest.get("runtime") else "CHANGED",
        "crm_normalized_digest": main_normalized,
        "spec_normalized_digest": spec_normalized,
        "protected_media_digest": protected_now,
        "target": target,
        "postimage_bound": postimage_entries is not None,
    }


def _task083_observation(backup_root: pathlib.Path) -> dict[str, Any]:
    """Validate the nested evidence, but use outer backup A as rollback authority."""
    started_path = backup_root / PUBLISH_STARTED_NAME
    task083_path = backup_root / TASK083_EVIDENCE_NAME
    if not task083_path.exists():
        return {
            "status": "NOT_CREATED_NO_TASK083_RENDER_SNAPSHOT"
            if started_path.exists() else "PUBLICATION_NOT_STARTED",
            "rollback_authority": "OUTER_BACKUP_A",
        }
    if not started_path.is_file() or not task083_path.is_file():
        raise Task120Error("TASK083_EVIDENCE_INCOMPLETE")
    raw, _ = _read_regular(task083_path, 64 * 1024 * 1024)
    saved = json.loads(raw.decode("utf-8"))
    if (
        not isinstance(saved, dict)
        or saved.get("task_id") != TASK_ID
        or tuple(saved.get("codes") or ()) != TARGETS
    ):
        raise Task120Error("TASK083_EVIDENCE_IDENTITY")
    recorded = pathlib.Path(str(saved.get("backup_root") or "")).resolve()
    expected_parent = ROOT / "rezerv_publikacii"
    if recorded == expected_parent or expected_parent.resolve() not in recorded.parents:
        raise Task120Error("TASK083_BACKUP_SCOPE")
    guard_manifest, _ = _read_regular(recorded / "manifest.json", MAX_HTML_BYTES)
    if _sha(guard_manifest) != saved.get("manifest_sha256"):
        raise Task120Error("TASK083_MANIFEST_IDENTITY")
    return {
        "status": "OBSERVED_VALID",
        "backup_root": str(recorded),
        "rollback_authority": "OUTER_BACKUP_A",
    }


def _rollback(backup_root: pathlib.Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    task083: dict[str, Any] | None = None
    web: dict[str, Any] | None = None
    media: dict[str, Any] | None = None
    flags: dict[str, Any] | None = None
    prevalidation: dict[str, Any] | None = None
    with _exclusive(PUBLISH_LOCK):
        # Every check happens while holding the same global lock as every write.
        # Outer backup A contains all renderer-owned HTML, both databases and
        # exact target media, so calling TASK083's blind rollback is unnecessary.
        spec_source = pathlib.Path(str(manifest["databases"]["spec"]["source"]))
        connection = _connect(DB, readonly=False)
        try:
            connection.execute("ATTACH DATABASE ? AS ua120_spec", (str(spec_source),))
            _assert_atomic_journal_modes(connection)
            connection.execute("BEGIN IMMEDIATE")
            _assert_spec_jobs_idle(connection, "ua120_spec")
            prevalidation = _prevalidate_rollback_state(manifest, connection)
            database_payloads = _prevalidate_database_backups(backup_root, manifest)
            _prevalidate_web_backup(backup_root, manifest)
            if prevalidation.get("status") != "PASS":
                errors.extend(
                    "PREFLIGHT_DRIFT:" + item for item in prevalidation.get("drift", [])
                )
            try:
                task083 = _task083_observation(backup_root)
            except Exception as exc:
                errors.append("TASK083_EVIDENCE:" + type(exc).__name__ + ":" + str(exc))
                task083 = {"status": "INVALID_BUT_OUTER_BACKUP_USED"}
            # _restore_media validates every current state and stored payload
            # before its first write; web payloads and states were fenced above.
            media = _restore_media(backup_root, manifest)
            web = _restore_web(backup_root, manifest)
            flags = _restore_flags(manifest, connection)
            connection.commit()
        except Exception:
            with contextlib.suppress(Exception):
                connection.rollback()
            raise
        finally:
            connection.close()
        main_before = str(manifest["databases"]["main"]["logical_digest"])
        main_after = _database_digest(DB)
        spec_before = str(manifest["databases"]["spec"]["logical_digest"])
        spec_after = _database_digest(spec_source)
        protected_before = str(manifest.get("protected_media_digest") or "")
        protected_after = _protected_media_digest()
    crm = {
        "status": "UNCHANGED" if main_before == main_after else "MISMATCH",
        "before": main_before,
        "after": main_after,
    }
    spec = {
        "status": "UNCHANGED" if spec_before == spec_after else "MISMATCH",
        "before": spec_before,
        "after": spec_after,
    }
    protected_media = {
        "status": "UNCHANGED" if protected_before == protected_after else "MISMATCH",
        "before": protected_before,
        "after": protected_after,
    }
    if main_before != main_after:
        errors.append("CRM:LOGICAL_DIGEST_MISMATCH")
    if spec_before != spec_after:
        errors.append("SPEC:LOGICAL_DIGEST_MISMATCH")
    if protected_before != protected_after:
        errors.append("PROTECTED_MEDIA:DIGEST_MISMATCH")
    html_preimage = manifest.get("html") or {}
    media_preimage = (manifest.get("media") or {}).get("entries") or {}
    public_preimage: dict[str, Any] = {}
    for relative in (
        "video/katalog.html", "video/UA-0016.html",
        "video/UA-0017.html", "video/UA-0017-diag.html",
        "video/UA-0018.html", "video/UA-0018-diag.html",
    ):
        if relative in html_preimage:
            public_preimage[relative] = {
                key: html_preimage[relative][key]
                for key in ("exists", "sha256", "size")
                if key in html_preimage[relative]
            }
    for relative, item in media_preimage.items():
        if relative.endswith(".poster.jpg"):
            continue
        public_preimage[relative] = {
            key: item[key] for key in ("exists", "sha256", "size") if key in item
        }
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "task083": task083,
        "prevalidation": prevalidation,
        "database_payloads": database_payloads,
        "web": web,
        "media": media,
        "flags": flags,
        "crm": crm,
        "spec": spec,
        "protected_media": protected_media,
        "public_preimage": public_preimage,
    }


def _catalog_ids(source: str) -> tuple[str, ...]:
    values = {
        value.upper()
        for value in re.findall(
            r"href\s*=\s*['\"](?:[^'\"]*/)?(UA-[0-9]{4})\.html(?:\?[^'\"]*)?['\"]",
            source,
            re.I,
        )
    }
    return tuple(sorted(values))


def _catalog_href_counts(source: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in re.findall(
        r"href\s*=\s*['\"](?:[^'\"]*/)?(UA-[0-9]{4})\.html(?:\?[^'\"]*)?['\"]",
        source,
        re.I,
    ):
        uid = value.upper()
        counts[uid] = counts.get(uid, 0) + 1
    return counts


def _catalog_card_counts(source: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in re.findall(
        r"\bdata-ua-card\s*=\s*['\"](UA-[0-9]{4})['\"]", source, re.I
    ):
        uid = value.upper()
        counts[uid] = counts.get(uid, 0) + 1
    return counts


def _page_contract(
    path: pathlib.Path,
    uid: str,
    vin: str,
    *,
    diagnostic: bool = False,
) -> dict[str, Any]:
    value, _ = _read_regular(path, MAX_HTML_BYTES)
    text = value.decode("utf-8", "replace")
    errors = []
    if uid not in text:
        errors.append("UID_MISSING")
    if not diagnostic and vin not in text.upper():
        errors.append("VIN_MISSING")
    if diagnostic and not re.search(
        r"href\s*=\s*['\"](?:[^'\"]*/)?"
        + re.escape(uid)
        + r"\.html(?:\?[^'\"]*)?['\"]",
        text,
        re.I,
    ):
        errors.append("PRIMARY_LINK_MISSING")
    if "</html>" not in text.casefold():
        errors.append("HTML_INCOMPLETE")
    if len(value) < 5000:
        errors.append("PAGE_TOO_SMALL")
    lowered = text.casefold()
    if "carhistory.kr" in lowered or "Проверить vin".casefold() in lowered:
        errors.append("VIN_AD_PRESENT")
    spec_rows = 0
    photo_refs: list[str] = []
    video_reference = False
    if not diagnostic:
        spec_rows = len(re.findall(r"<div\b[^>]*class=['\"][^'\"]*\bua-addspec-row\b", text, re.I))
        expected_spec = len(FACTS[uid])
        if spec_rows != expected_spec:
            errors.append("SPEC_ROW_COUNT")
        if (
            "data-ua-additional-spec" not in lowered
        ):
            errors.append("SPEC_SOURCE_MARKER")
        photo_refs = re.findall(
            r"<img\b[^>]*\bsrc=['\"]foto/" + re.escape(uid)
            + r"/([0-9]{3})\.jpg(?:\?[^'\"]*)?['\"]",
            text,
            re.I,
        )
        expected_photos = EXPECTED_MEDIA_COUNTS[uid]["foto"]
        expected_names = ["%03d" % index for index in range(1, expected_photos + 1)]
        if len(photo_refs) != expected_photos or set(photo_refs) != set(expected_names):
            errors.append("PHOTO_REFERENCES")
        video_sources = re.findall(
            r"<source\b[^>]*\bsrc=['\"]" + re.escape(uid)
            + r"\.mp4(?:\?[^'\"]*)?['\"]",
            text,
            re.I,
        )
        target_video_refs = re.findall(
            r"(?:src|href)\s*=\s*['\"]([^'\"]*"
            + re.escape(uid)
            + r"[^'\"]*\.mp4(?:\?[^'\"]*)?)['\"]",
            text,
            re.I,
        )
        normalized_video_refs = {
            reference.split("?", 1)[0].rsplit("/", 1)[-1].casefold()
            for reference in target_video_refs
        }
        video_reference = bool(video_sources)
        expected_video_names = {uid.casefold() + ".mp4"} if uid == "UA-0018" else set()
        if (
            len(video_sources) != EXPECTED_MEDIA_COUNTS[uid]["video"]
            or normalized_video_refs != expected_video_names
        ):
            errors.append("VIDEO_REFERENCE")
    return {
        "sha256": _sha(value),
        "size": len(value),
        "errors": errors,
        "spec_rows": spec_rows,
        "photo_references": len(photo_refs),
        "video_reference": video_reference,
    }


def _verify_final(
    manifest: Mapping[str, Any] | None = None,
    expected_database_digests: Mapping[str, str] | None = None,
    expected_media: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    spec_path = _spec_db()
    with _connect(DB, readonly=True) as connection:
        rows = _rows_by_uid(connection)
        _validate_bindings(rows)
        published = _published_ids(connection)
        current_media_plan = _media_plan(connection, rows)
        published_rows = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM cars WHERE COALESCE(published,0)=1 ORDER BY auto_number,id"
            ).fetchall()
        ]
    errors: list[str] = []
    spec_states: dict[str, Any] = {}
    try:
        spec_states = _all_spec_states(DB, spec_path)
        for uid in TARGETS:
            if spec_states[uid].get("state") != "EXACT":
                errors.append("SPEC_NOT_EXACT:" + uid)
    except Exception as exc:
        errors.append("SPEC_VERIFY:" + type(exc).__name__ + ":" + str(exc))
    if published != EXPECTED_PUBLIC_IDS:
        errors.append("PUBLISHED_SET_INVALID")
    for uid in TARGETS:
        if rows[uid].get("published") != 1 or rows[uid].get("publish_pending") != 0:
            errors.append("TARGET_FLAGS_INVALID:" + uid)
    catalogs: dict[str, Any] = {}
    catalog_values: list[bytes] = []
    pages: dict[str, Any] = {}
    for root in SITE_ROOTS:
        catalog_path = root / "katalog.html"
        value, _ = _read_regular(catalog_path, MAX_HTML_BYTES)
        catalog_values.append(value)
        ids = _catalog_ids(value.decode("utf-8", "replace"))
        href_counts = _catalog_href_counts(value.decode("utf-8", "replace"))
        card_counts = _catalog_card_counts(value.decode("utf-8", "replace"))
        if (
            ids != EXPECTED_PUBLIC_IDS
            or set(href_counts) != set(EXPECTED_PUBLIC_IDS)
            or href_counts != {uid: 2 for uid in EXPECTED_PUBLIC_IDS}
            or card_counts != {uid: 1 for uid in EXPECTED_PUBLIC_IDS}
        ):
            errors.append("CATALOG_IDS_INVALID:" + root.name)
        catalogs[root.name] = {
            "sha256": _sha(value), "size": len(value),
            "unique_ids": list(ids), "unique_count": len(ids),
            "href_counts": href_counts,
            "semantic_card_counts": card_counts,
        }
        for uid in EXPECTED_PUBLIC_IDS:
            if not (root / (uid + ".html")).is_file():
                errors.append("DIRECT_PAGE_MISSING:%s:%s" % (root.name, uid))
        for uid in TARGETS:
            binding = TARGET_BINDINGS[uid]
            primary = _page_contract(root / (uid + ".html"), uid, binding["vin"])
            diagnostic = _page_contract(
                root / (uid + "-diag.html"), uid, binding["vin"], diagnostic=True
            )
            pages[root.name + "/" + uid] = {"primary": primary, "diagnostic": diagnostic}
            errors.extend("%s:%s:%s" % (root.name, uid, item) for item in primary["errors"])
            errors.extend("%s:%s:DIAG_%s" % (root.name, uid, item) for item in diagnostic["errors"])
    if catalog_values[0] != catalog_values[1]:
        errors.append("CATALOG_ROOTS_DIVERGED")
    for uid in TARGETS:
        for suffix in (".html", "-diag.html"):
            left = (SITE_ROOTS[0] / (uid + suffix)).read_bytes()
            right = (SITE_ROOTS[1] / (uid + suffix)).read_bytes()
            if left != right:
                errors.append("TARGET_ROOTS_DIVERGED:" + uid + suffix)
    catalog_audit: dict[str, Any] = {}
    media_checks: dict[str, Any] = {}
    media_inventory: dict[str, Any] = {}
    renderer_videos: dict[str, Any] = {}
    try:
        media_inventory = _media_inventory(current_media_plan)
        renderer_videos = _assert_renderer_video_state(materialized=True)
    except Exception as exc:
        errors.append("TARGET_MEDIA_INVENTORY:" + type(exc).__name__ + ":" + str(exc))
    if expected_media is not None:
        for relative, expected in sorted(expected_media.items()):
            path = _lexical_under(ROOT, relative)
            maximum = MAX_VIDEO_BYTES if relative.endswith(".mp4") else MAX_PHOTO_BYTES
            try:
                actual = _path_state(path, maximum)
                media_checks[relative] = actual
                if actual != {
                    "exists": True,
                    "sha256": expected.get("sha256"),
                    "size": expected.get("size"),
                    "mode": expected.get("mode"),
                }:
                    errors.append("TARGET_MEDIA_CHANGED:" + relative)
            except Exception as exc:
                errors.append("TARGET_MEDIA_INVALID:%s:%s" % (relative, type(exc).__name__))
    try:
        sys.path.insert(0, str(ROOT))
        design = importlib.import_module("catalog_design_guard")
        if pathlib.Path(str(design.__file__)).resolve() != (ROOT / "catalog_design_guard.py").resolve():
            raise Task120Error("CATALOG_GUARD_MODULE_ORIGIN")
        golden = (ROOT / "catalog_design_golden.html").read_text(encoding="utf-8")
        for root in SITE_ROOTS:
            audit = design.audit_catalog(
                (root / "katalog.html").read_text(encoding="utf-8"), published_rows, golden
            )
            catalog_audit[root.name] = audit
            if audit.get("status") != "PASS":
                errors.append("CATALOG_GUARD_FAIL:" + root.name)
    except Exception as exc:
        errors.append("CATALOG_GUARD_ERROR:" + type(exc).__name__ + ":" + str(exc))
    db_checks: dict[str, Any] = {}
    if manifest is not None:
        preimage = _flags_from_manifest(manifest)
        main_before = str(manifest["databases"]["main"]["logical_digest"])
        main_after = _database_digest(DB, normalized_flags=preimage)
        spec_before = str(manifest["databases"]["spec"]["logical_digest"])
        spec_after = _database_digest(spec_path)
        spec_preimage = manifest.get("spec_preimage")
        if not isinstance(spec_preimage, dict) or set(spec_preimage) != set(TARGETS):
            raise Task120Error("BACKUP_SPEC_PREIMAGE_INVALID")
        spec_normalized_after = _database_digest(
            spec_path, normalized_specs=spec_preimage
        )
        db_checks = {
            "main_normalized_before": main_before,
            "main_normalized_after": main_after,
            "spec_before": spec_before,
            "spec_after": spec_after,
            "spec_normalized_after": spec_normalized_after,
        }
        if main_before != main_after:
            errors.append("CRM_CHANGED_OUTSIDE_TARGET_FLAGS")
        if spec_before != spec_normalized_after:
            errors.append("SPEC_CHANGED_OUTSIDE_EXPECTED_ROWS")
        protected_before = str(manifest.get("protected_media_digest") or "")
        protected_after = _protected_media_digest()
        db_checks["protected_media_before"] = protected_before
        db_checks["protected_media_after"] = protected_after
        if not SHA_RE.fullmatch(protected_before) or protected_before != protected_after:
            errors.append("PROTECTED_MEDIA_CHANGED")
        if expected_database_digests is not None:
            if _database_digest(DB) != expected_database_digests.get("main"):
                errors.append("CRM_POSTIMAGE_CHANGED")
            if spec_after != expected_database_digests.get("spec"):
                errors.append("SPEC_POSTIMAGE_CHANGED")
        before_html = manifest.get("html") or {}
        after_html = _html_manifest()
        for relative, expected in before_html.items():
            if (
                not _allowed_web_relative(relative)
                and after_html.get(relative) != _html_preimage_state(expected)
            ):
                errors.append("PROTECTED_HTML_CHANGED:" + relative)
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "published_ids": list(published),
        "published_count": len(published),
        "targets": {uid: _row_public(rows[uid]) for uid in TARGETS},
        "catalogs": catalogs,
        "catalog_audit": catalog_audit,
        "pages": pages,
        "target_media": media_checks,
        "target_media_inventory": media_inventory,
        "renderer_videos": renderer_videos,
        "spec_states": spec_states,
        "database_checks": db_checks,
    }


def _import_publish_runtime():
    os.environ["UA_ART_ROOT"] = str(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    importlib.invalidate_caches()
    publisher = importlib.import_module("publikaciya")
    guard = importlib.import_module("publish_transaction_guard")
    if pathlib.Path(str(publisher.__file__)).resolve() != (ROOT / "publikaciya.py").resolve():
        raise Task120Error("PUBLISHER_MODULE_ORIGIN")
    if pathlib.Path(str(guard.__file__)).resolve() != (ROOT / "publish_transaction_guard.py").resolve():
        raise Task120Error("PUBLISH_GUARD_MODULE_ORIGIN")
    if not callable(getattr(publisher, "opublikovat", None)):
        raise Task120Error("PUBLISHER_ENTRYPOINT_MISSING")
    base = getattr(publisher, "_UA083_BASE_PUBLISH", None)
    locked = getattr(guard, "_publish_locked", None)
    rollback = getattr(guard, "rollback_backup", None)
    if not callable(base) or not callable(locked) or not callable(rollback):
        raise Task120Error("ATOMIC_BATCH_ENTRYPOINT_MISSING")
    if tuple(inspect.signature(locked).parameters) != ("base_publish", "codes", "proba"):
        raise Task120Error("ATOMIC_LOCKED_SIGNATURE_DRIFT")
    publisher_paths = {
        "BASE": ROOT,
        "VIDEO": ROOT / "video",
        "SITE": ROOT / "site",
        "LOG": ROOT / "publish_log.txt",
        "REZERV_KORE": ROOT / "rezerv_publikacii",
    }
    for name, expected in publisher_paths.items():
        if pathlib.Path(str(getattr(publisher, name, ""))).resolve() != expected.resolve():
            raise Task120Error("PUBLISHER_GLOBAL_DRIFT:" + name)
    guard_paths = {
        "ROOT": ROOT,
        "VIDEO": ROOT / "video",
        "SITE": ROOT / "site",
        "DB": DB,
        "LOCK": PUBLISH_LOCK,
        "BACKUPS": ROOT / "rezerv_publikacii/TASK083",
        "LOG": ROOT / "publish_log.txt",
    }
    for name, expected in guard_paths.items():
        if pathlib.Path(str(getattr(guard, name, ""))).resolve() != expected.resolve():
            raise Task120Error("PUBLISH_GUARD_GLOBAL_DRIFT:" + name)
    if tuple(pathlib.Path(str(item)).resolve() for item in getattr(guard, "ROOTS", ())) != tuple(
        path.resolve() for path in (ROOT / "video", ROOT / "site")
    ):
        raise Task120Error("PUBLISH_GUARD_ROOTS_DRIFT")
    return publisher, guard, base, locked


def _publish(
    manifest_path: pathlib.Path, manifest: Mapping[str, Any], run_id: str
) -> dict[str, Any]:
    # Telegram I/O is deliberately outside the global publication lock.  The
    # staged bytes are private to backup A and cannot affect production.
    started_path = manifest_path.with_name(PUBLISH_STARTED_NAME)
    if os.path.lexists(str(started_path)):
        raise Task120Error("PUBLISH_LINEAGE_ALREADY_STARTED")
    initial = _preflight()
    if initial["preflight_digest"] != manifest.get("preflight_digest"):
        raise Task120Error("PREFLIGHT_CHANGED_AFTER_BACKUP")
    with _connect(DB, readonly=True) as connection:
        initial_rows = _rows_by_uid(connection)
        initial_plan = _media_plan(connection, initial_rows)
    if _public_media_plan(initial_plan) != manifest.get("media_plan"):
        raise Task120Error("MEDIA_PLAN_CHANGED_AFTER_BACKUP")
    staged_media = _stage_media(manifest_path.parent, initial_plan)

    if str(PUBLISH_LOCK.resolve()) not in _HELD_LOCKS:
        raise Task120Error("PUBLISH_LOCK_NOT_HELD")
    with contextlib.nullcontext():
        preflight = _preflight()
        if preflight["preflight_digest"] != manifest.get("preflight_digest"):
            raise Task120Error("PREFLIGHT_CHANGED_AFTER_BACKUP")
        if preflight["runtime"] != manifest.get("runtime"):
            raise Task120Error("RUNTIME_CHANGED_AFTER_BACKUP")
        publisher, guard, base, locked = _import_publish_runtime()
        _atomic_json(
            started_path,
            {
                "task_id": TASK_ID,
                "run_id": run_id,
                "codes": list(TARGETS),
                "started_at": _utc_now(),
                "backup_manifest_sha256": _sha(_read_regular(manifest_path, 64 * 1024 * 1024)[0]),
            },
        )
        media_intent = _write_media_intent(manifest_path, manifest, staged_media)
        post_media = _promote_media(staged_media, manifest, media_intent)
        renderer_videos = _assert_renderer_video_state(materialized=True)
        post_flags = _set_publication_flags(manifest)
        original_snapshot = getattr(guard, "Snapshot", None)
        if not callable(original_snapshot):
            raise Task120Error("TASK083_SNAPSHOT_ENTRYPOINT_MISSING")

        def recording_snapshot(codes):
            snapshot = original_snapshot(codes)
            task083_manifest, _ = _read_regular(
                pathlib.Path(snapshot.root) / "manifest.json", MAX_HTML_BYTES
            )
            _atomic_json(
                manifest_path.with_name(TASK083_EVIDENCE_NAME),
                {
                    "task_id": TASK_ID,
                    "codes": list(TARGETS),
                    "backup_root": str(pathlib.Path(snapshot.root).resolve()),
                    "manifest_sha256": _sha(task083_manifest),
                    "phase": "SNAPSHOT_COMMITTED_BEFORE_RENDER",
                },
            )
            return snapshot

        renderer_backups = _assert_under(
            manifest_path.parent / "runtime-renderer-backups", manifest_path.parent
        )
        task083_backups = _assert_under(
            manifest_path.parent / "task083-backups", manifest_path.parent
        )
        renderer_backups.mkdir(mode=0o700, exist_ok=False)
        task083_backups.mkdir(mode=0o700, exist_ok=False)
        original_renderer_backups = publisher.REZERV_KORE
        original_guard_backups = guard.BACKUPS
        publisher.REZERV_KORE = str(renderer_backups)
        guard.BACKUPS = task083_backups
        guard.Snapshot = recording_snapshot
        log_path = ROOT / "publish_log.txt"
        if os.path.lexists(str(log_path)):
            log_before, _ = _read_regular(log_path, 128 * 1024 * 1024)
        else:
            log_before = b""
        try:
            result = locked(base, list(TARGETS), False)
        finally:
            guard.Snapshot = original_snapshot
            publisher.REZERV_KORE = original_renderer_backups
            guard.BACKUPS = original_guard_backups
        log_after, _ = _read_regular(log_path, 128 * 1024 * 1024)
        if not log_after.startswith(log_before):
            raise Task120Error("PUBLISH_LOG_NOT_APPEND_ONLY")
        log_delta = log_after[len(log_before):]
        if not log_delta or len(log_delta) > 1024 * 1024:
            raise Task120Error("PUBLISH_LOG_APPEND_SIZE")
        log_lines = [line for line in log_delta.decode("utf-8", "strict").splitlines() if line]
        if not log_lines or any(
            not any(marker in line for marker in ("UA-0017", "UA-0018", "TASK083"))
            for line in log_lines
        ):
            raise Task120Error("PUBLISH_LOG_APPEND_SCOPE")
        audit_log = {
            "path": "publish_log.txt", "before_size": len(log_before),
            "append_size": len(log_delta), "append_sha256": _sha(log_delta),
            "after_size": len(log_after), "status": "APPEND_ONLY_EXPECTED",
        }
        if not isinstance(result, (tuple, list)) or len(result) != 3:
            raise Task120Error("ATOMIC_BATCH_RESULT_INVALID")
        ok, message, evidence = result
        if not isinstance(evidence, dict):
            raise Task120Error("ATOMIC_BATCH_EVIDENCE_INVALID")
        task083_root = pathlib.Path(str(evidence.get("backup_root") or "")).resolve()
        guard_root = task083_backups.resolve()
        if task083_root == guard_root or guard_root not in task083_root.parents:
            raise Task120Error("ATOMIC_BATCH_BACKUP_SCOPE")
        task083_manifest, _ = _read_regular(task083_root / "manifest.json", MAX_HTML_BYTES)
        _atomic_json(
            manifest_path.with_name(TASK083_EVIDENCE_NAME),
            {
                "task_id": TASK_ID,
                "codes": list(TARGETS),
                "backup_root": str(task083_root),
                "manifest_sha256": _sha(task083_manifest),
                "evidence": evidence,
            },
        )
        if ok is not True or not isinstance(evidence, dict) or evidence.get("status") != "PASS":
            raise Task120Error("ATOMIC_BATCH_FAILED:" + str(message)[:500])
        if tuple(evidence.get("codes") or ()) != TARGETS:
            raise Task120Error("ATOMIC_BATCH_TARGET_SET")
        final_html = _html_manifest()
        postimage_path = manifest_path.with_name(POSTIMAGE_NAME)
        if os.path.lexists(str(postimage_path)):
            raise Task120Error("POSTIMAGE_ALREADY_EXISTS")
        _atomic_json(
            postimage_path,
            {
                "task_id": TASK_ID,
                "backup_manifest_sha256": _sha(
                    _read_regular(manifest_path, 64 * 1024 * 1024)[0]
                ),
                "html": {
                    relative: metadata for relative, metadata in final_html.items()
                    if _allowed_web_relative(relative)
                },
                "target_media": post_media["files"],
                "database_digests": post_flags["database_digests"],
                "created_at": _utc_now(),
            },
        )
        verification = _verify_final(
            manifest,
            expected_database_digests=post_flags["database_digests"],
            expected_media=post_media["files"],
        )
        if verification["status"] != "PASS":
            raise Task120Error("FINAL_VERIFY_FAILED:" + ";".join(verification["errors"][:12]))
        return {
            "status": "PASS",
            "outcome": "PUBLISHED",
            "message": str(message),
            "post_flags": post_flags,
            "target_media": post_media,
            "renderer_videos": renderer_videos,
            "atomic_batch": evidence,
            "audit_log": audit_log,
            "verification": verification,
            "backup_manifest": _backup_relative(manifest_path),
        }


def _receipt_path(run_id: str) -> pathlib.Path:
    if not RUN_RE.fullmatch(run_id):
        raise Task120Error("RUN_ID_INVALID")
    return REMOTE_DIR / ("task120-receipt-" + run_id + ".json")


def _completed_path(run_id: str) -> pathlib.Path:
    return REMOTE_DIR / ("task120-completed-" + run_id + ".json")


def _write_receipt(run_id: str, value: Mapping[str, Any]) -> None:
    receipt = _receipt_path(run_id)
    completed = _completed_path(run_id)
    payload = dict(value)
    _atomic_json(completed, payload)
    _atomic_json(receipt, payload)


def _base_receipt(mode: str, run_id: str, script_sha: str) -> dict[str, Any]:
    return {
        "schema": RECEIPT_SCHEMA,
        "task_id": TASK_ID,
        "contract_id": CONTRACT_ID,
        "mode": mode.upper(),
        "run_id": run_id,
        "script_sha256": script_sha,
        "created_at": _utc_now(),
        "production_root": str(ROOT),
        "runtime_llm_tokens": 0,
        "status": "FAIL",
        "errors": [],
    }


def _main(args: argparse.Namespace) -> int:
    script_value, _ = _read_regular(SELF, MAX_SOURCE_BYTES)
    script_sha = _sha(script_value)
    receipt = _base_receipt(args.mode, args.run_id, script_sha)
    if args.expected_script_sha256 != script_sha:
        receipt["errors"] = ["SCRIPT_SHA256_MISMATCH"]
        _write_receipt(args.run_id, receipt)
        return 1
    completed = _completed_path(args.run_id)
    if completed.is_file():
        value, _ = _read_regular(completed, 64 * 1024 * 1024)
        _atomic(_receipt_path(args.run_id), value, 0o600)
        previous = json.loads(value.decode("utf-8"))
        return 0 if previous.get("status") == "PASS" else 1
    # Controller execution is always-on-only and strictly sequential.  The
    # existing global production publication lock fences every write; no new
    # persistent TASK120 coordination file is created.
    with contextlib.nullcontext():
        try:
            if args.mode == "probe":
                observation = _preflight()
                receipt.update({"status": "PASS", "read_only": True, "observation": observation})
            elif args.mode == "backup":
                observation = _preflight()
                if observation["preflight_digest"] != args.expected_preflight_digest:
                    raise Task120Error("EXPECTED_PREFLIGHT_DIGEST_MISMATCH")
                root, _manifest, manifest_sha = _backup(observation)
                manifest_path = root / "manifest.json"
                receipt.update(
                    {
                        "status": "PASS",
                        "production_write": False,
                        "backup_manifest": _backup_relative(manifest_path),
                        "backup_manifest_sha256": manifest_sha,
                        "preflight_digest": observation["preflight_digest"],
                    }
                )
            elif args.mode == "publish":
                backup_root, manifest = _load_backup(
                    args.backup_manifest, args.backup_manifest_sha256
                )
                manifest_path = backup_root / "manifest.json"
                receipt["backup_manifest"] = _backup_relative(manifest_path)
                receipt["backup_manifest_sha256"] = args.backup_manifest_sha256
                try:
                    with _exclusive(PUBLISH_LOCK):
                        outcome = _publish(manifest_path, manifest, args.run_id)
                    receipt.update(outcome)
                    receipt["production_write"] = True
                except Exception as publish_exc:
                    started_by_this_run = False
                    started_path = backup_root / PUBLISH_STARTED_NAME
                    if started_path.is_file():
                        try:
                            started_raw, _ = _read_regular(started_path, 1024 * 1024)
                            started = json.loads(started_raw.decode("utf-8"))
                            started_by_this_run = (
                                isinstance(started, dict)
                                and started.get("task_id") == TASK_ID
                                and started.get("run_id") == args.run_id
                            )
                        except Exception:
                            started_by_this_run = False
                    if started_by_this_run:
                        rollback = _rollback(backup_root, manifest)
                        receipt["rollback"] = rollback
                        receipt["errors"] = [
                            "PUBLISH:" + type(publish_exc).__name__ + ":" + str(publish_exc)
                        ] + list(rollback.get("errors") or [])
                        receipt["status"] = (
                            "ROLLED_BACK" if rollback.get("status") == "PASS" else "FAIL"
                        )
                    else:
                        receipt["errors"] = [
                            "PUBLISH_BEFORE_FIRST_WRITE:"
                            + type(publish_exc).__name__ + ":" + str(publish_exc)
                        ]
                        receipt["status"] = "FAIL"
            elif args.mode == "verify":
                backup_root, manifest = _load_backup(
                    args.backup_manifest, args.backup_manifest_sha256
                )
                manifest_path = backup_root / "manifest.json"
                receipt["backup_manifest"] = _backup_relative(manifest_path)
                receipt["backup_manifest_sha256"] = args.backup_manifest_sha256
                expected_media = None
                intent_path = backup_root / MEDIA_INTENT_NAME
                if intent_path.is_file():
                    intent_raw, _ = _read_regular(intent_path, 64 * 1024 * 1024)
                    intent = json.loads(intent_raw.decode("utf-8"))
                    if intent.get("backup_manifest_sha256") != args.backup_manifest_sha256:
                        raise Task120Error("MEDIA_INTENT_BACKUP_IDENTITY")
                    expected_media = {
                        relative: details["after"]
                        for relative, details in (intent.get("files") or {}).items()
                    }
                verification = _verify_final(manifest, expected_media=expected_media)
                receipt.update(
                    {
                        "status": verification["status"],
                        "read_only": True,
                        "verification": verification,
                        "backup_root": str(backup_root),
                    }
                )
            elif args.mode == "rollback":
                backup_root, manifest = _load_backup(
                    args.backup_manifest, args.backup_manifest_sha256
                )
                manifest_path = backup_root / "manifest.json"
                receipt["backup_manifest"] = _backup_relative(manifest_path)
                receipt["backup_manifest_sha256"] = args.backup_manifest_sha256
                rollback = _rollback(backup_root, manifest)
                receipt.update(
                    {
                        "status": rollback["status"],
                        "production_write": True,
                        "rollback": rollback,
                    }
                )
            else:
                raise Task120Error("MODE_INVALID")
        except Exception as exc:
            receipt["status"] = "FAIL"
            receipt["errors"] = [type(exc).__name__ + ":" + str(exc)]
            receipt["traceback_tail"] = traceback.format_exc().splitlines()[-12:]
        _write_receipt(args.run_id, receipt)
    return 0 if receipt.get("status") == "PASS" else 1


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("probe", "backup", "publish", "verify", "rollback"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-script-sha256", required=True)
    parser.add_argument("--expected-preflight-digest", default="")
    parser.add_argument("--backup-manifest", default="")
    parser.add_argument("--backup-manifest-sha256", default="")
    args = parser.parse_args(argv)
    if not RUN_RE.fullmatch(args.run_id):
        parser.error("invalid run id")
    if not SHA_RE.fullmatch(args.expected_script_sha256):
        parser.error("invalid script sha256")
    if args.mode == "backup" and not SHA_RE.fullmatch(args.expected_preflight_digest):
        parser.error("backup requires preflight digest")
    if args.mode in ("publish", "verify", "rollback"):
        if not SHA_RE.fullmatch(args.backup_manifest_sha256):
            parser.error("mode requires backup manifest sha256")
    return args


if __name__ == "__main__":
    raise SystemExit(_main(parse_args()))
