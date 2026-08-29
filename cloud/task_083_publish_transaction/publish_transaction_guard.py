#!/usr/bin/env python3
"""Transactional publication guard for UA ART.

The active legacy publisher expects a diagnostic target to exist before it
can render a new primary page.  This guard stages the diagnostic page first,
backs up the complete bounded publication bundle, invokes the approved master
publisher, rebuilds both catalogs, verifies the result and rolls everything
back on any failure.

Runtime LLM use: none.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import sqlite3
import tempfile
import time
import uuid
from typing import Any, Callable, Iterable


CONTRACT_ID = "UA-0012-UA-0013-PUBLISH-TRANSACTION-001-V1.0"
ROOT = pathlib.Path(os.environ.get("UA_ART_ROOT", "/home/Carix")).resolve()
VIDEO = ROOT / "video"
SITE = ROOT / "site"
DB = ROOT / "crm.db"
LOCK = ROOT / ".ua_art_publish_transaction.lock"
BACKUPS = ROOT / "rezerv_publikacii" / "TASK083"
LOG = ROOT / "publish_log.txt"
ROOTS = (VIDEO, SITE)
ID_RE = re.compile(r"^UA-[0-9]{4,}$")
MAX_FILE = 32 * 1024 * 1024
WAIT_SECONDS = 90


class PublishError(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read(path: pathlib.Path) -> bytes:
    data = path.read_bytes()
    if len(data) > MAX_FILE:
        raise PublishError("FILE_TOO_LARGE:" + str(path))
    return data


def _atomic(path: pathlib.Path, data: bytes, mode: int | None = None) -> None:
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


def _append_log(message: str) -> None:
    try:
        with io.open(LOG, "a", encoding="utf-8") as handle:
            handle.write("%s  TASK083 %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), message))
    except Exception:
        pass


def _code(value: Any) -> str:
    result = str(value or "").strip().upper()
    if not ID_RE.fullmatch(result):
        raise PublishError("INVALID_AUTO_NUMBER:" + result[:40])
    return result


def _stage(row: dict[str, Any]) -> int:
    status = str(row.get("status") or row.get("stage") or "").strip().lower()
    if status.startswith("kr_"):
        return 1
    if status.startswith("sea_") or status.startswith("sold_transit"):
        return 2
    if status == "ge_to_kyiv" or status.startswith("ge_"):
        return 3
    if status.startswith("ua_") or status in {"sold", "archive"}:
        return 4
    raise PublishError("UNKNOWN_STAGE:%s:%s" % (row.get("auto_number"), status))


def _category(stage: int) -> str:
    return {1: "korea", 2: "more", 3: "gruzia", 4: "kiev"}[stage]


def _rows() -> tuple[list[dict[str, Any]], str]:
    connection = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        rows = [dict(row) for row in connection.execute(
            "SELECT * FROM cars WHERE published=1 ORDER BY auto_number, id"
        ).fetchall()]
    finally:
        connection.close()
    if quick != "ok":
        raise PublishError("CRM_QUICK_CHECK:" + quick)
    normalized = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode()
    return rows, _sha(normalized)


def _row_map() -> tuple[dict[str, dict[str, Any]], str]:
    rows, digest = _rows()
    return {str(row.get("auto_number") or "").upper(): row for row in rows}, digest


def _protected_pages(codes: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for root in ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("UA-*.html")):
            if any(path.name.startswith(code) for code in codes):
                continue
            result[str(path)] = _sha(_read(path))
    return result


def _matching_paths(codes: set[str]) -> set[pathlib.Path]:
    paths: set[pathlib.Path] = {root / "katalog.html" for root in ROOTS}
    for code in codes:
        for root in ROOTS:
            paths.add(root / (code + ".html"))
            paths.add(root / (code + "-diag.html"))
            if root.is_dir():
                paths.update(path for path in root.glob(code + "*") if path.is_file())
            for folder in (root / "foto" / code, root / "diag" / code):
                if folder.is_dir():
                    paths.update(path for path in folder.rglob("*") if path.is_file())
        archive = ROOT / "archive" / "video_dubli"
        if archive.is_dir():
            paths.update(path for path in archive.glob(code + "*") if path.is_file())
    return paths


class Snapshot:
    """Persistent bounded backup with exact rollback semantics."""

    def __init__(self, codes: Iterable[str]):
        self.codes = {_code(value) for value in codes}
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        self.root = BACKUPS / (stamp + "-" + uuid.uuid4().hex[:12])
        self.root.mkdir(parents=True, exist_ok=False)
        self.before_paths = _matching_paths(self.codes)
        self.present = {path for path in self.before_paths if path.is_file()}
        manifest: dict[str, Any] = {}
        for path in sorted(self.before_paths):
            item: dict[str, Any] = {"exists": path in self.present, "path": str(path)}
            if path in self.present:
                data = _read(path)
                relative = path.relative_to(ROOT)
                target = self.root / "files" / relative
                _atomic(target, data, path.stat().st_mode & 0o777)
                item.update({"sha256": _sha(data), "mode": path.stat().st_mode & 0o777})
            manifest[str(path)] = item
        _atomic(
            self.root / "manifest.json",
            (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
        )

    def restore(self) -> dict[str, Any]:
        current = _matching_paths(self.codes)
        removed: list[str] = []
        restored: list[str] = []
        for path in sorted(current - self.present, reverse=True):
            if path.is_file():
                path.unlink()
                removed.append(str(path))
        manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        for path in sorted(self.present):
            item = manifest[str(path)]
            data = _read(self.root / "files" / path.relative_to(ROOT))
            if not path.is_file() or _read(path) != data:
                _atomic(path, data, int(item.get("mode") or 0o644))
                restored.append(str(path))
        mismatches = []
        for path in self.present:
            expected = manifest[str(path)]["sha256"]
            if not path.is_file() or _sha(_read(path)) != expected:
                mismatches.append(str(path))
        if mismatches:
            raise PublishError("ROLLBACK_READBACK_MISMATCH:" + ",".join(mismatches))
        return {"backup_root": str(self.root), "removed": removed, "restored": restored}


@contextlib.contextmanager
def _exclusive_lock():
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    handle = open(LOCK, "a+")
    deadline = time.monotonic() + WAIT_SECONDS
    try:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise PublishError("PUBLISH_LOCK_TIMEOUT")
                time.sleep(0.25)
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _render_diag(code: str) -> bytes:
    import stranica as page

    row = None
    for item in page.mashiny():
        if str(page.nomer(item)).strip().upper() == code:
            row = item
            break
    if row is None:
        raise PublishError("PUBLISHED_CARD_NOT_FOUND:" + code)
    value = page.sobrat_diagnostiku(row)
    if isinstance(value, bytes):
        data = value
        text = value.decode("utf-8", "replace")
    else:
        text = str(value or "")
        data = text.encode("utf-8")
    if len(data) < 300 or code not in text or "</html>" not in text.lower():
        raise PublishError("DIAGNOSTIC_PLACEHOLDER_INVALID:" + code)
    if re.search(r"UA-[0-9]{4,}", text) and any(
        other != code for other in set(re.findall(r"UA-[0-9]{4,}", text, re.I))
    ):
        raise PublishError("DIAGNOSTIC_FOREIGN_IDENTIFIER:" + code)
    return data


def _stage_diags(codes: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for code in codes:
        data = _render_diag(code)
        for root in ROOTS:
            if not root.is_dir():
                raise PublishError("SITE_ROOT_MISSING:" + str(root))
            path = root / (code + "-diag.html")
            _atomic(path, data, path.stat().st_mode & 0o777 if path.exists() else 0o644)
            if _read(path) != data:
                raise PublishError("DIAGNOSTIC_READBACK_MISMATCH:" + str(path))
        result[code] = _sha(data)
    return result


def _href_counts(source: str) -> dict[str, int]:
    pattern = re.compile(
        r"href\s*=\s*['\"](?:https?://[^'\"]+)?(?:[^'\"]*/)?"
        r"(UA-[0-9]{4,})\.html(?:\?[^'\"]*)?['\"]",
        re.I,
    )
    counts: dict[str, int] = {}
    for value in pattern.findall(source):
        code = value.upper()
        counts[code] = counts.get(code, 0) + 1
    return counts


def _catalog_card_window(source: str, code: str) -> str:
    match = re.search(
        r"href\s*=\s*['\"][^'\"]*" + re.escape(code) + r"\.html(?:\?[^'\"]*)?['\"]",
        source,
        re.I,
    )
    if not match:
        return ""
    start = max(0, match.start() - 1200)
    end = min(len(source), match.end() + 14000)
    return source[start:end]


def _validate_catalog(source: str, rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if len(source.encode("utf-8")) < 5000 or "</html>" not in source.lower():
        raise PublishError("CATALOG_HTML_INVALID")
    counts = _href_counts(source)
    expected = set(rows)
    wrong = {code: counts.get(code, 0) for code in sorted(expected) if counts.get(code, 0) != 1}
    unexpected = sorted(set(counts) - expected)
    if wrong:
        raise PublishError("CATALOG_CARD_COUNT:" + json.dumps(wrong, sort_keys=True))
    if unexpected:
        raise PublishError("CATALOG_UNEXPECTED_IDS:" + ",".join(unexpected))
    cards: dict[str, Any] = {}
    for code, row in rows.items():
        stage = _stage(row)
        category = _category(stage)
        window = _catalog_card_window(source, code)
        tokens = (
            'data-ua-stage="%d"' % stage,
            "data-ua-stage='%d'" % stage,
            'data-ua-stage-tile="%d"' % stage,
            "data-ua-stage-tile='%d'" % stage,
            'data-stage="%d"' % stage,
            "data-stage='%d'" % stage,
        )
        if not window or not any(token in window for token in tokens):
            raise PublishError("CATALOG_STAGE_MISMATCH:%s:%d" % (code, stage))
        cards[code] = {
            "href_count": 1,
            "stage": stage,
            "category": category,
            "category_token": bool(re.search(
                r"(?:data-(?:category|filter)|[?&](?:f|etap|stage)=)['\"]?" + re.escape(category),
                window,
                re.I,
            )),
        }
    return {"count": len(expected), "cards": cards, "ids": sorted(expected)}


def _validate_primary(code: str, row: dict[str, Any], source: str) -> dict[str, Any]:
    if len(source.encode("utf-8")) < 5000 or code not in source or "</html>" not in source.lower():
        raise PublishError("PRIMARY_HTML_INVALID:" + code)
    links = re.findall(
        r"href\s*=\s*['\"](?:[^'\"]*/)?" + re.escape(code) + r"-diag\.html(?:\?[^'\"]*)?['\"]",
        source,
        re.I,
    )
    if len(links) != 1:
        raise PublishError("PRIMARY_DIAGNOSTIC_LINK_COUNT:%s:%d" % (code, len(links)))
    foreign = {
        value.upper() for value in re.findall(r"UA-[0-9]{4,}", source, re.I)
        if value.upper() != code
    }
    if foreign:
        raise PublishError("PRIMARY_FOREIGN_IDENTIFIER:%s:%s" % (code, ",".join(sorted(foreign))))
    stage = _stage(row)
    stage_tokens = (
        'data-ua-stage-current="%d"' % stage,
        "data-ua-stage-current='%d'" % stage,
        'data-ua-stage="%d"' % stage,
        "data-ua-stage='%d'" % stage,
    )
    if not any(token in source for token in stage_tokens):
        raise PublishError("PRIMARY_STAGE_MISMATCH:%s:%d" % (code, stage))
    return {"bytes": len(source.encode("utf-8")), "diag_links": 1, "stage": stage}


def _build_catalog() -> tuple[str, list[dict[str, Any]]]:
    import publikaciya as publisher

    if not hasattr(publisher, "_ua9_sobrat_katalog"):
        raise PublishError("CATALOG_MASTER_MISSING")
    value, rows = publisher._ua9_sobrat_katalog()
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    return str(value or ""), list(rows or [])


def _install_catalog(source: str, target: str | None) -> dict[str, Any]:
    row_map, _ = _row_map()
    before = _validate_catalog(source, row_map)
    try:
        import catalog_stage_guard_core as stage_guard
    except ModuleNotFoundError as exc:
        raise PublishError("CATALOG_STAGE_GUARD_MISSING") from exc

    photos: dict[str, str] = {}
    for code in sorted(row_map):
        primary_path = VIDEO / (code + ".html")
        if not primary_path.is_file():
            raise PublishError("CATALOG_PRIMARY_NOT_READY:" + code)
        primary = _read(primary_path).decode("utf-8", "replace")
        photos[code] = stage_guard.extract_main_photo(
            primary, "https://www.uaart.com.ua/video/%s.html" % code, code
        )
        if not photos[code]:
            raise PublishError("CATALOG_MAIN_PHOTO_NOT_READY:" + code)

    try:
        normalized = stage_guard.enforce_catalog(source, list(row_map.values()), photos)
        stage_audit = stage_guard.audit_catalog(normalized, list(row_map.values()))
    except Exception as exc:
        raise PublishError("CATALOG_STAGE_GUARD_FAIL:" + str(exc)) from exc
    if not isinstance(stage_audit, dict) or stage_audit.get("status") != "PASS":
        raise PublishError("CATALOG_STAGE_AUDIT_FAIL")
    data = normalized.encode("utf-8")
    for root in ROOTS:
        path = root / "katalog.html"
        _atomic(path, data, path.stat().st_mode & 0o777 if path.exists() else 0o644)
        if _read(path) != data:
            raise PublishError("CATALOG_READBACK_MISMATCH:" + str(path))

    after: dict[str, Any] = {}
    for root in ROOTS:
        path = root / "katalog.html"
        after[str(path)] = {
            "sha256": _sha(_read(path)),
            "audit": _validate_catalog(_read(path).decode("utf-8", "replace"), row_map),
        }
    return {
        "candidate": before,
        "stage_guard": stage_audit,
        "target": target,
        "installed": after,
    }


def _verify_bundle(codes: list[str]) -> dict[str, Any]:
    rows, digest = _row_map()
    targets: dict[str, Any] = {}
    for code in codes:
        row = rows.get(code)
        if row is None:
            raise PublishError("TARGET_NOT_PUBLISHED:" + code)
        files: dict[str, Any] = {}
        for root in ROOTS:
            primary_path = root / (code + ".html")
            diag_path = root / (code + "-diag.html")
            if not primary_path.is_file() or not diag_path.is_file():
                raise PublishError("TARGET_FILE_MISSING:%s:%s" % (code, root))
            primary_text = _read(primary_path).decode("utf-8", "replace")
            diag_text = _read(diag_path).decode("utf-8", "replace")
            if code not in diag_text or "</html>" not in diag_text.lower():
                raise PublishError("DIAGNOSTIC_READBACK_INVALID:%s:%s" % (code, root))
            files[str(root)] = {
                "primary_sha256": _sha(_read(primary_path)),
                "diag_sha256": _sha(_read(diag_path)),
                "primary": _validate_primary(code, row, primary_text),
            }
        targets[code] = {
            "status": row.get("status"),
            "stage": _stage(row),
            "category": _category(_stage(row)),
            "files": files,
        }
    catalogs: dict[str, Any] = {}
    for root in ROOTS:
        path = root / "katalog.html"
        catalogs[str(path)] = _validate_catalog(
            _read(path).decode("utf-8", "replace"), rows
        )
    return {"targets": targets, "catalogs": catalogs, "published_rows_sha256": digest}


def _call_base(base_publish: Callable[..., Any], code: str, proba: bool) -> tuple[bool, str]:
    value = base_publish(code, proba=proba)
    if not isinstance(value, (tuple, list)) or len(value) < 2:
        raise PublishError("PUBLISHER_RESULT_INVALID:" + code)
    return value[0] is True, str(value[1])


def _publish_locked(
    base_publish: Callable[..., Any], codes: list[str], proba: bool = False
) -> tuple[bool, str, dict[str, Any]]:
    codes = [_code(value) for value in codes]
    if not codes or len(codes) != len(set(codes)):
        raise PublishError("TARGET_SET_INVALID")
    snapshot = Snapshot(codes)
    before_rows, before_db = _row_map()
    missing = [code for code in codes if code not in before_rows]
    if missing:
        raise PublishError("TARGETS_NOT_PUBLISHED:" + ",".join(missing))
    protected = _protected_pages(set(codes))
    evidence: dict[str, Any] = {
        "contract_id": CONTRACT_ID,
        "codes": codes,
        "mode": "PROBE" if proba else "INSTALL",
        "backup_root": str(snapshot.root),
        "published_rows_sha256_before": before_db,
        "staged_diagnostics": {},
        "base_results": {},
        "catalog": None,
        "verification": None,
        "rollback": None,
    }
    try:
        evidence["staged_diagnostics"] = _stage_diags(codes)
        for code in codes:
            ok, message = _call_base(base_publish, code, proba)
            evidence["base_results"][code] = {"ok": ok, "message": message[:2000]}
            if not ok:
                raise PublishError("BASE_PUBLISH_FAILED:%s:%s" % (code, message[:500]))

        catalog_source, catalog_rows = _build_catalog()
        generated_ids = {str(row.get("auto_number") or "").upper() for row in catalog_rows}
        if generated_ids != set(before_rows):
            raise PublishError("CATALOG_ROW_SET_MISMATCH")
        _validate_catalog(catalog_source, before_rows)

        if proba:
            evidence["rollback"] = snapshot.restore()
            evidence["status"] = "PASS"
            return True, "Проба публикации прошла; production-файлы не изменены.", evidence

        evidence["catalog"] = _install_catalog(catalog_source, codes[-1])
        after_rows, after_db = _row_map()
        if before_db != after_db or set(before_rows) != set(after_rows):
            raise PublishError("CRM_ROWS_CHANGED_DURING_PUBLICATION")
        if _protected_pages(set(codes)) != protected:
            raise PublishError("PROTECTED_PAGE_CHANGED")
        evidence["verification"] = _verify_bundle(codes)
        evidence["published_rows_sha256_after"] = after_db
        evidence["status"] = "PASS"
        _append_log("PASS %s backup=%s" % (",".join(codes), snapshot.root))
        return True, (
            "Страницы, диагностика и оба каталога опубликованы одним проверенным пакетом: "
            + ", ".join(codes)
        ), evidence
    except Exception as exc:
        try:
            evidence["rollback"] = snapshot.restore()
        except Exception as rollback_exc:
            evidence["rollback_error"] = type(rollback_exc).__name__ + ":" + str(rollback_exc)
            _append_log("CRITICAL ROLLBACK FAIL %s %s" % (",".join(codes), rollback_exc))
            raise
        evidence["status"] = "FAIL"
        evidence["error"] = type(exc).__name__ + ":" + str(exc)
        _append_log("FAIL %s %s rollback=PASS" % (",".join(codes), evidence["error"]))
        return False, "Публикация отменена: %s. Выполнен полный откат." % str(exc), evidence


def publish_batch(
    base_publish: Callable[..., Any], codes: Iterable[str], proba: bool = False
) -> tuple[bool, str, dict[str, Any]]:
    with _exclusive_lock():
        return _publish_locked(base_publish, list(codes), proba=proba)


def publish_one(
    base_publish: Callable[..., Any], code: str, proba: bool = False
) -> tuple[bool, str]:
    ok, message, _ = publish_batch(base_publish, [code], proba=proba)
    return ok, message


def rebuild_catalog() -> tuple[bool, str]:
    with _exclusive_lock():
        snapshot = Snapshot([])
        before_rows, before_db = _row_map()
        protected = _protected_pages(set())
        try:
            source, generated_rows = _build_catalog()
            generated_ids = {str(row.get("auto_number") or "").upper() for row in generated_rows}
            if generated_ids != set(before_rows):
                raise PublishError("CATALOG_ROW_SET_MISMATCH")
            _install_catalog(source, None)
            _, after_db = _row_map()
            if after_db != before_db:
                raise PublishError("CRM_ROWS_CHANGED_DURING_CATALOG_REBUILD")
            if _protected_pages(set()) != protected:
                raise PublishError("PROTECTED_PAGE_CHANGED")
            return True, "Каталог обновлён."
        except Exception as exc:
            snapshot.restore()
            return False, "Каталог не обновлён: %s. Выполнен откат." % str(exc)


def verify_bundle(codes: Iterable[str]) -> dict[str, Any]:
    """Read-only verification used by the deployment postcheck."""
    normalized = [_code(value) for value in codes]
    with _exclusive_lock():
        return _verify_bundle(normalized)


def rollback_backup(backup_root: str, codes: Iterable[str]) -> dict[str, Any]:
    """Restore a previously recorded publication snapshot."""
    root = pathlib.Path(backup_root).resolve()
    if root == BACKUPS or BACKUPS not in root.parents:
        raise PublishError("ROLLBACK_BACKUP_OUTSIDE_TASK083")
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise PublishError("ROLLBACK_MANIFEST_MISSING")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    instance = Snapshot.__new__(Snapshot)
    instance.codes = {_code(value) for value in codes}
    instance.root = root
    instance.before_paths = {pathlib.Path(value) for value in manifest}
    instance.present = {
        pathlib.Path(value) for value, item in manifest.items() if item.get("exists")
    }
    with _exclusive_lock():
        return instance.restore()


__all__ = [
    "CONTRACT_ID",
    "PublishError",
    "publish_batch",
    "publish_one",
    "rebuild_catalog",
    "verify_bundle",
    "rollback_backup",
]
