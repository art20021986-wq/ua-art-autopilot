#!/usr/bin/env python3
"""Remove the unsolicited public VIN advertisement and restore specifications."""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import gzip
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import sqlite3
import stat
import tempfile
import urllib.parse


TASK_ID = "TASK115-REMOVE-VIN-ADS"
CONTRACT = "UA-ART-NO-VIN-ADS-V1.0"
ROOT = pathlib.Path("/home/Carix")
SAFE = ROOT / "autopilot_inbox/cloud/task_068_ferry_vin"
RECEIPT = SAFE / "task115_receipt.json"
LATEST = SAFE / "task115_latest_backup.txt"
BACKUPS = SAFE / "task115_backups"
LOCK = ROOT / ".task115_no_vin_ads.lock"
DB = ROOT / "crm.db"
SOURCE_PATHS = (
    ROOT / "ua_additional_spec.py",
    ROOT / "vin_spec_service.py",
)
PUBLIC_ROOTS = (ROOT / "video", ROOT / "site")
IDS = tuple("UA-%04d" % value for value in range(1, 17))
ADD_START = "<!--UA099_ADD_SPEC_START-->"
ADD_END = "<!--UA099_ADD_SPEC_END-->"
CLEAN_START = "<!--UA099_CLEAN_VIN_START-->"
CLEAN_END = "<!--UA099_CLEAN_VIN_END-->"
OLD_START = "<!-- UA-ART-VIN-GUARD-LITE-V1:START -->"
OLD_END = "<!-- UA-ART-VIN-GUARD-LITE-V1:END -->"
PY_START = "# >>> UA115 NO PUBLIC VIN ADS"
PY_END = "# <<< UA115 NO PUBLIC VIN ADS"
WORKER_START = "# >>> UA115 VIN AUTOWORKER DISABLED"
WORKER_END = "# <<< UA115 VIN AUTOWORKER DISABLED"
FORBIDDEN = re.compile(r"carhistory(?:\.kr)?|проверить\s+vin|перевірити\s+vin|2\s*200\s*krw", re.I)
APPROVED_HOSTS = {"www.uaart.com.ua", "uaart.com.ua", "wa.me", "t.me", "maps.app.goo.gl", "ecomm.one-line.com"}
MAX_BYTES = 64 * 1024 * 1024


class InstallError(RuntimeError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read(path: pathlib.Path, required: bool = True) -> bytes | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        if required:
            raise InstallError("MISSING:" + str(path))
        return None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
        raise InstallError("UNSAFE_FILE:" + str(path))
    value = path.read_bytes()
    if len(value) > MAX_BYTES:
        raise InstallError("FILE_TOO_LARGE:" + str(path))
    return value


def atomic(path: pathlib.Path, value: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    current = read(path, False)
    actual_mode = mode if mode is not None else (stat.S_IMODE(path.stat().st_mode) if current is not None else 0o600)
    handle = tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix="." + path.name + ".", suffix=".task115", delete=False)
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, actual_mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, value: dict) -> None:
    atomic(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())


def car_rows() -> dict[str, str]:
    uri = "file:" + str(DB.resolve()) + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=30) as conn:
        conn.execute("PRAGMA query_only=ON")
        rows = conn.execute("SELECT auto_number,vin FROM cars WHERE published=1 ORDER BY auto_number").fetchall()
        if conn.total_changes:
            raise InstallError("CRM_WRITE_GUARD")
    result = {str(uid): str(vin or "").strip().upper() for uid, vin in rows}
    if tuple(sorted(result)) != IDS or any(not result[uid] for uid in IDS):
        raise InstallError("CARD_REGISTRY_NOT_16")
    return result


def target_paths() -> list[pathlib.Path]:
    paths = list(SOURCE_PATHS)
    for root in PUBLIC_ROOTS:
        paths.extend(root / (uid + ".html") for uid in IDS)
    return paths


def backup(paths: list[pathlib.Path]) -> pathlib.Path:
    BACKUPS.mkdir(parents=True, exist_ok=True)
    folder = BACKUPS / dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    (folder / "files").mkdir(parents=True)
    items = []
    for index, path in enumerate(paths):
        value = read(path)
        stored = "files/%04d.gz" % index
        atomic(folder / stored, gzip.compress(value or b"", 9, mtime=0), 0o600)
        items.append({"path": str(path), "sha256": sha(value or b""), "mode": stat.S_IMODE(path.stat().st_mode), "stored": stored})
    atomic_json(folder / "manifest.json", {"task_id": TASK_ID, "files": items})
    atomic(LATEST, (str(folder) + "\n").encode(), 0o600)
    return folder


def backup_only() -> dict:
    folder = backup(target_paths())
    manifest = read(folder / "manifest.json") or b""
    return {"task_id": TASK_ID, "contract_id": CONTRACT, "status": "PASS", "mode": "BACKUP",
            "backup": str(folder), "backup_manifest_sha256": sha(manifest),
            "crm_write": False, "media_write": False}


def restore(folder: pathlib.Path) -> dict:
    resolved = folder.resolve()
    if resolved.parent != BACKUPS.resolve():
        raise InstallError("BACKUP_SCOPE")
    manifest = json.loads((read(resolved / "manifest.json") or b"").decode())
    if manifest.get("task_id") != TASK_ID:
        raise InstallError("BACKUP_IDENTITY")
    restored = []
    allowed = {str(path) for path in target_paths()}
    for item in manifest.get("files") or []:
        path = pathlib.Path(str(item.get("path") or ""))
        if str(path) not in allowed:
            raise InstallError("RESTORE_SCOPE")
        value = gzip.decompress(read(resolved / str(item["stored"])) or b"")
        if sha(value) != item.get("sha256"):
            raise InstallError("BACKUP_HASH")
        if read(path) != value:
            atomic(path, value, int(item["mode"]))
            restored.append(str(path))
    return {"status": "PASS", "restored": restored, "backup": str(resolved)}


def without_block(source: str, start: str, end: str) -> str:
    while start in source or end in source:
        left = source.find(start)
        right = source.find(end, max(0, left + len(start)))
        if left >= 0 and right >= 0:
            source = source[:left] + source[right + len(end):]
        else:
            source = source.replace(start, "").replace(end, "")
    return source


def without_style(source: str) -> str:
    return re.sub(r"<style\b[^>]*id=['\"]ua099-additional-spec-style['\"][^>]*>[\s\S]*?</style>", "", source, flags=re.I)


def canonical(source: str) -> str:
    for start, end in ((ADD_START, ADD_END), (CLEAN_START, CLEAN_END), (OLD_START, OLD_END)):
        source = without_block(source, start, end)
    return without_style(source)


def load_spec():
    spec = importlib.util.spec_from_file_location("ua_additional_spec", ROOT / "ua_additional_spec.py")
    if spec is None or spec.loader is None:
        raise InstallError("SPEC_IMPORT")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compact_vin(uid: str, vin: str) -> str:
    import html
    return (CLEAN_START + "<div class='blok ua-clean-vin' data-ua-clean-vin='1' data-ua-card='%s'>"
            "<div class='zag'>VIN</div><div class='ua-vin-value'>%s</div></div>" %
            (html.escape(uid), html.escape(vin)) + CLEAN_END)


def external_hosts(source: str) -> set[str]:
    result = set()
    for href in re.findall(r"<a\b[^>]*\bhref=['\"]([^'\"]+)['\"]", source, re.I):
        host = (urllib.parse.urlsplit(href).hostname or "").casefold()
        if host:
            result.add(host)
    return result


def transform(source: str, uid: str, vin: str, helper) -> str:
    before = canonical(source)
    cleaned = source
    for start, end in ((ADD_START, ADD_END), (CLEAN_START, CLEAN_END), (OLD_START, OLD_END)):
        cleaned = without_block(cleaned, start, end)
    cleaned = without_style(cleaned)
    block = helper.render_public_block(uid) + compact_vin(uid, vin)
    anchor = "<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:START -->"
    position = cleaned.find(anchor)
    if position < 0:
        raise InstallError("STAGE_ANCHOR:" + uid)
    cleaned = cleaned[:position] + block + cleaned[position:]
    cleaned = re.sub(r"</head>", helper._css() + "</head>", cleaned, count=1, flags=re.I)
    if canonical(cleaned) != before:
        raise InstallError("OUTSIDE_TARGET_CHANGED:" + uid)
    if FORBIDDEN.search(cleaned):
        raise InstallError("VIN_AD_REMAINS:" + uid)
    unknown = external_hosts(cleaned) - APPROVED_HOSTS
    if unknown:
        raise InstallError("UNAPPROVED_EXTERNAL_HOST:" + uid + ":" + ",".join(sorted(unknown)))
    if cleaned.count(ADD_START) != 1 or cleaned.count(CLEAN_START) != 1 or vin not in cleaned:
        raise InstallError("PUBLIC_CONTRACT:" + uid)
    return cleaned


def append_block(source: str, start: str, end: str, block: str) -> str:
    source = re.sub(r"(?:\n|^)" + re.escape(start) + r"[\s\S]*?" + re.escape(end) + r"\s*", "\n", source)
    return source.rstrip() + "\n\n" + block.strip() + "\n"


PY_BLOCK = r'''
# >>> UA115 NO PUBLIC VIN ADS
_UA115_BASE_INJECT_PUBLIC_SPEC = inject_public_spec

def inject_public_spec(source: str, value: Any) -> str:
    output = _UA115_BASE_INJECT_PUBLIC_SPEC(source, value)
    uid = canonical_uid(value)
    if not output or not uid:
        return output
    vin = _car_vin(uid)
    compact = (VIN_START + "<div class='blok ua-clean-vin' data-ua-clean-vin='1' "
               "data-ua-card='%s'><div class='zag'>VIN</div>"
               "<div class='ua-vin-value'>%s</div></div>" %
               (html.escape(uid), html.escape(vin)) + VIN_END)
    output = re.sub(re.escape(VIN_START) + r"[\s\S]*?" + re.escape(VIN_END), compact, output)
    if re.search(r"carhistory(?:\.kr)?|проверить\s+vin|перевірити\s+vin|2\s*200\s*krw", output, re.I):
        raise RuntimeError("UA115_PUBLIC_VIN_AD_GUARD:" + uid)
    import urllib.parse as _ua115_urlparse
    _ua115_allowed = {"www.uaart.com.ua", "uaart.com.ua", "wa.me", "t.me", "maps.app.goo.gl", "ecomm.one-line.com"}
    _ua115_hosts = {
        (_ua115_urlparse.urlsplit(item).hostname or "").casefold()
        for item in re.findall(r"<a\b[^>]*\bhref=['\"]([^'\"]+)['\"]", output, re.I)
    }
    _ua115_unknown = {item for item in _ua115_hosts if item and item not in _ua115_allowed}
    if _ua115_unknown:
        raise RuntimeError("UA115_UNAPPROVED_EXTERNAL_HOST:" + uid + ":" + ",".join(sorted(_ua115_unknown)))
    return output
# <<< UA115 NO PUBLIC VIN ADS
'''


WORKER_BLOCK = r'''
# >>> UA115 VIN AUTOWORKER DISABLED
def start_worker() -> None:
    """Owner disabled autonomous VIN enrichment on 2026-09-05."""
    return None
# <<< UA115 VIN AUTOWORKER DISABLED
'''


def verify(rows: dict[str, str]) -> dict:
    result = {}
    for root in PUBLIC_ROOTS:
        for uid in IDS:
            text = (read(root / (uid + ".html")) or b"").decode("utf-8")
            if FORBIDDEN.search(text) or text.count(ADD_START) != 1 or text.count(CLEAN_START) != 1 or rows[uid] not in text:
                raise InstallError("VERIFY:" + str(root) + ":" + uid)
            result[str(root / (uid + ".html"))] = sha(text.encode())
    return {"status": "PASS", "page_count": len(result), "card_count": len(IDS), "ua0009": "PASS", "sha256": result}


def install() -> dict:
    rows = car_rows()
    crm_before = sha(read(DB) or b"")
    folder = backup(target_paths())
    try:
        spec_source = (read(SOURCE_PATHS[0]) or b"").decode("utf-8")
        service_source = (read(SOURCE_PATHS[1]) or b"").decode("utf-8")
        spec_new = append_block(spec_source, PY_START, PY_END, PY_BLOCK)
        service_new = append_block(service_source, WORKER_START, WORKER_END, WORKER_BLOCK)
        compile(spec_new, "ua_additional_spec.py", "exec")
        compile(service_new, "vin_spec_service.py", "exec")
        atomic(SOURCE_PATHS[0], spec_new.encode())
        atomic(SOURCE_PATHS[1], service_new.encode())
        helper = load_spec()
        changed = []
        for root in PUBLIC_ROOTS:
            for uid in IDS:
                path = root / (uid + ".html")
                original = (read(path) or b"").decode("utf-8")
                updated = transform(original, uid, rows[uid], helper)
                if updated != original:
                    atomic(path, updated.encode())
                    changed.append(str(path))
        checked = verify(rows)
        if sha(read(DB) or b"") != crm_before:
            raise InstallError("CRM_CHANGED")
        return {"task_id": TASK_ID, "contract_id": CONTRACT, "status": "PASS", "mode": "INSTALL",
                "backup": str(folder), "changed": changed, "crm_write": False, "media_write": False,
                "autoworker_enabled": False, "vin_ad_count": 0, **checked}
    except Exception:
        restore(folder)
        raise


def run(mode: str) -> dict:
    with open(LOCK, "a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        if mode == "install":
            return install()
        if mode == "backup":
            return backup_only()
        if mode == "verify":
            value = verify(car_rows())
            return {"task_id": TASK_ID, "contract_id": CONTRACT, "mode": "VERIFY", "crm_write": False,
                    "media_write": False, "autoworker_enabled": False, "vin_ad_count": 0, **value}
        if mode == "rollback":
            path = pathlib.Path((read(LATEST) or b"").decode().strip())
            return {"task_id": TASK_ID, "contract_id": CONTRACT, "mode": "ROLLBACK", **restore(path)}
        raise InstallError("MODE")


def self_test() -> None:
    fixture = "A" + OLD_START + "AD" + OLD_END + "B"
    assert canonical(fixture) == "AB"
    assert without_block(fixture, OLD_START, OLD_END) == "AB"
    assert FORBIDDEN.search("Перевірити VIN")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("backup", "install", "verify", "rollback"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("TASK115_SELFTEST_PASS")
        return 0
    try:
        value = run(str(args.mode))
    except Exception as exc:
        value = {"task_id": TASK_ID, "contract_id": CONTRACT, "status": "FAIL", "mode": str(args.mode).upper(),
                 "errors": [type(exc).__name__ + ":" + str(exc)], "finished_at": now()}
    atomic_json(RECEIPT, value)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0 if value.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
