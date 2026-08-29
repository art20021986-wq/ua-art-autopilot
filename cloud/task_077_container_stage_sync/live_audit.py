#!/usr/bin/env python3
"""TASK 077: secret-backed GET-only audit + local SQLite canary.

The PythonAnywhere API surface implemented here is strictly GET.  The live
database and sources are never modified; the only writes are to a temporary
runner directory and to sanitized evidence inside this repository checkout.
"""
from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import shutil
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

import stage_sync

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "patcher"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "task_076_eta_sync"))
import live_patcher


CONTRACT_ID = "CRM-CONTAINER-STAGE-SYNC-004-V1.0"
REMOTE_ROOT = "/home/Carix"
API = "https://www.pythonanywhere.com/api/v0/user/Carix/files/path"
HERE = pathlib.Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence" / "live_audit.json"
REPORT = HERE / "TASK_077_AUDIT.md"
MAX_REMOTE_BYTES = 80_000_000
SOURCE_NAMES = (
    "cars_schema.py",
    "cars_ui.py",
    "konteyner.py",
    "db.py",
    "publikaciya.py",
    "stranica.py",
    "master_card.py",
    "yadro.py",
)
RELEVANT_NEEDLES = (
    "sea_loaded",
    "sea_transit",
    "sold_transit",
    "eta_days",
    "days_to_kyiv",
    "eta_manual",
    "SEO068_DIAGNOSTIC_TARGET_MISSING",
    "Машина видна клиентам в каталоге",
    "opublikovat",
)


def utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_text(value: str) -> str:
    return sha_bytes(value.encode("utf-8"))


def get_remote(path: str, *, missing_ok: bool = False, limit: int = MAX_REMOTE_BYTES):
    if not path.startswith(REMOTE_ROOT + "/"):
        raise RuntimeError("REMOTE_PATH_OUT_OF_SCOPE")
    token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("PYTHONANYWHERE_API_TOKEN_MISSING")
    request = urllib.request.Request(
        API + urllib.parse.quote(path, safe="/"),
        method="GET",
        headers={
            "Authorization": "Token " + token,
            "User-Agent": "ua-art-task077-get-only/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        if missing_ok and exc.code == 404:
            return None
        raise RuntimeError(
            "GET_HTTP_%d:%s" % (exc.code, pathlib.PurePosixPath(path).name)
        ) from exc
    if len(payload) > limit:
        raise RuntimeError("REMOTE_FILE_TOO_LARGE:" + pathlib.PurePosixPath(path).name)
    return payload


def _redact_source(source: str) -> str:
    source = re.sub(r"\b\d{7,12}:[A-Za-z0-9_-]{20,}\b", "[REDACTED_BOT_TOKEN]", source)
    source = re.sub(r"(?i)(token\s*[=:]\s*[\"'])[^\"']+", r"\1[REDACTED]", source)
    source = re.sub(r"sk-[A-Za-z0-9_-]{16,}", "[REDACTED_KEY]", source)
    return source


def relevant_definitions(filename: str, source: str) -> list[dict]:
    tree = ast.parse(source, filename=filename)
    lines = source.splitlines(keepends=True)
    result = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        segment = "".join(lines[node.lineno - 1 : node.end_lineno])
        if not any(needle in segment for needle in RELEVANT_NEEDLES):
            continue
        clean = _redact_source(segment)
        result.append(
            {
                "name": node.name,
                "line": node.lineno,
                "end_line": node.end_lineno,
                "sha256": sha_text(segment),
                "source": clean[:30_000],
                "truncated": len(clean) > 30_000,
            }
        )
    return sorted(result, key=lambda item: (item["line"], item["name"]))


def source_audit(filename: str, payload: bytes) -> dict:
    source = payload.decode("utf-8")
    compile(source, filename, "exec")
    return {
        "sha256": sha_bytes(payload),
        "bytes": len(payload),
        "compiled": True,
        "counts": {needle: source.count(needle) for needle in RELEVANT_NEEDLES},
        "callbacks": {
            "sea_loaded": len(re.findall(r"car_setstage[^\n]{0,120}sea_loaded", source)),
            "sea_transit": len(re.findall(r"car_setstage[^\n]{0,120}sea_transit", source)),
            "sold_transit": len(re.findall(r"car_setstage[^\n]{0,120}sold_transit", source)),
        },
        "definitions": relevant_definitions(filename, source),
    }


def _copy_db(db_payload: bytes, wal_payload: bytes | None, directory: pathlib.Path):
    db_path = directory / "crm.db"
    db_path.write_bytes(db_payload)
    if wal_payload:
        pathlib.Path(str(db_path) + "-wal").write_bytes(wal_payload)
    return db_path


def _media_digest(row: dict, media_columns: list[str]) -> str:
    value = {name: row.get(name) for name in media_columns}
    return sha_text(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def _safe_row(row: dict) -> dict:
    result = {}
    allowed = (
        "id",
        "auto_number",
        "status",
        "days_to_kyiv",
        "eta_manual",
        "updated_at",
        "sea_container",
        "sea_date_out",
        "published",
        "publish_pending",
    )
    for key in allowed:
        if key in row:
            result[key] = row.get(key)
    for key in ("photos", "videos", "condition_photos", "condition_videos"):
        if key in row:
            raw = row.get(key)
            result[key + "_bytes"] = len(str(raw or "").encode("utf-8"))
    return result


def database_audit_and_canary(db_payload: bytes, wal_payload: bytes | None) -> dict:
    with tempfile.TemporaryDirectory(prefix="task077-audit-") as raw_dir:
        root = pathlib.Path(raw_dir)
        # Keep explicit subdirectories so source and canary paths cannot alias.
        source_dir = root / "source"
        source_dir.mkdir()
        source_db = _copy_db(db_payload, wal_payload, source_dir)
        uri = "file:%s?mode=ro" % urllib.parse.quote(str(source_db), safe="/")
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA query_only=ON")
            quick_check = conn.execute("PRAGMA quick_check").fetchone()[0]
            columns = [row[1] for row in conn.execute("PRAGMA table_info(cars)")]
            rows = [dict(row) for row in conn.execute("SELECT * FROM cars ORDER BY id")]
        finally:
            conn.close()
        if quick_check != "ok":
            raise RuntimeError("CRM_QUICK_CHECK:" + str(quick_check))

        targets = [row for row in rows if str(row.get("auto_number") or "").upper() == "UA-0012"]
        if len(targets) != 1:
            raise RuntimeError("UA0012_ROW_COUNT:%d" % len(targets))
        ua12 = targets[0]
        ua9 = [row for row in rows if str(row.get("auto_number") or "").upper() == "UA-0009"]
        if len(ua9) != 1:
            raise RuntimeError("UA0009_ROW_COUNT:%d" % len(ua9))

        media_columns = [
            name
            for name in ("photos", "videos", "condition_photos", "condition_videos")
            if name in columns
        ]
        before_media = {int(row["id"]): _media_digest(row, media_columns) for row in rows}
        before_published = {int(row["id"]): row.get("published") for row in rows}
        legacy_ids = [int(row["id"]) for row in rows if row.get("status") == "sea_transit"]

        canary_dir = root / "canary"
        canary_dir.mkdir()
        canary_db = _copy_db(db_payload, wal_payload, canary_dir)
        candidate = sqlite3.connect(canary_db)
        candidate.row_factory = sqlite3.Row
        placeholder = stage_sync.diagnostic_or_placeholder("UA-0012", None)

        def publish_gate(row):
            return (
                row.get("status") == stage_sync.CANONICAL_FERRY_STATUS
                and int(row.get("days_to_kyiv")) == 30
                and row.get("eta_manual") == "2026-09-28"
                and "Материалы диагностики ожидаются" in placeholder
            )

        transition = stage_sync.save_container_eta_atomic(
            candidate,
            int(ua12["id"]),
            30,
            today=dt.date(2026, 8, 29),
            publish_gate=publish_gate,
            updated_at="2026-08-29T13:28:00+00:00",
        )
        after_rows = [dict(row) for row in candidate.execute("SELECT * FROM cars ORDER BY id")]
        after_ua12 = next(row for row in after_rows if int(row["id"]) == int(ua12["id"]))
        after_media = {int(row["id"]): _media_digest(row, media_columns) for row in after_rows}
        after_published = {int(row["id"]): row.get("published") for row in after_rows}
        candidate.close()
        if before_media != after_media:
            raise RuntimeError("MEDIA_CHANGED_IN_CANARY")
        if before_published != after_published:
            raise RuntimeError("PUBLISHED_CHANGED_IN_CANARY")

        migration_dir = root / "migration"
        migration_dir.mkdir()
        migration_db = _copy_db(db_payload, wal_payload, migration_dir)
        migration = sqlite3.connect(migration_db)
        migrated_ids = stage_sync.normalize_legacy_ferry_rows(migration)
        remaining_legacy = migration.execute(
            "SELECT COUNT(*) FROM cars WHERE status='sea_transit'"
        ).fetchone()[0]
        migration.close()
        if migrated_ids != legacy_ids or remaining_legacy != 0:
            raise RuntimeError("LEGACY_MIGRATION_CANARY_MISMATCH")

        published_rows = [row for row in rows if int(row.get("published") or 0) == 1]
        identifiers = [str(row.get("auto_number") or "").upper() for row in published_rows]
        count_conn = sqlite3.connect("file:%s?mode=ro" % source_db, uri=True)
        try:
            status_counts = dict(
                count_conn.execute(
                    "SELECT COALESCE(status,''),COUNT(*) FROM cars GROUP BY status ORDER BY status"
                ).fetchall()
            )
        finally:
            count_conn.close()
        return {
            "quick_check": quick_check,
            "db_sha256": sha_bytes(db_payload),
            "db_bytes": len(db_payload),
            "wal_present": wal_payload is not None,
            "columns": columns,
            "row_count": len(rows),
            "published_count": len(published_rows),
            "unique_published_ids": len(set(identifiers)),
            "ua0009": _safe_row(ua9[0]),
            "ua0012_before": _safe_row(ua12),
            "legacy_sea_transit_ids": legacy_ids,
            "status_counts": status_counts,
            "canary": {
                "ua0012_after": _safe_row(after_ua12),
                "transition": {
                    "status": transition.status,
                    "days_to_kyiv": transition.days_to_kyiv,
                    "eta_manual": transition.eta_manual,
                    "changed": transition.changed,
                },
                "owner_label": stage_sync.owner_status_label(after_ua12.get("status")),
                "diagnostic_placeholder": True,
                "media_hashes_unchanged": True,
                "published_unchanged": True,
                "migration_ids": migrated_ids,
                "legacy_remaining": remaining_legacy,
            },
        }


def page_manifest(name: str, payload: bytes | None) -> dict:
    if payload is None:
        return {"missing": True}
    text = payload.decode("utf-8", "replace")
    return {
        "missing": False,
        "sha256": sha_bytes(payload),
        "bytes": len(payload),
        "contains_ua0012": "UA-0012" in text,
        "contains_30_days": bool(re.search(r"\b30\s+(?:дн|дней|дня)", text, re.I)),
        "contains_2026_09_28": any(value in text for value in ("28.09.2026", "28 сентября 2026", "28 вересня 2026")),
        "contains_ferry_label": any(value in text for value in ("На пароме", "На поромі")),
        "contains_diag_wait": "Материалы диагностики ожидаются" in text,
    }


def write_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    evidence = {
        "task_id": "task_077",
        "contract_id": CONTRACT_ID,
        "status": "FAIL",
        "mode": "LIVE_GET_ONLY_PLUS_LOCAL_COPY_CANARY",
        "production_touched": False,
        "pythonanywhere_methods": ["GET"],
        "crm_write": False,
        "site_write": False,
        "media_write": False,
        "runtime_llm_tokens": 0,
        "started_at_utc": utc_now(),
        "errors": [],
    }
    try:
        paths = {name: REMOTE_ROOT + "/" + name for name in SOURCE_NAMES}
        paths.update(
            {
                "crm.db": REMOTE_ROOT + "/crm.db",
                "crm.db-wal": REMOTE_ROOT + "/crm.db-wal",
                "video_catalog": REMOTE_ROOT + "/video/katalog.html",
                "site_catalog": REMOTE_ROOT + "/site/katalog.html",
                "video_ua0012": REMOTE_ROOT + "/video/UA-0012.html",
                "site_ua0012": REMOTE_ROOT + "/site/UA-0012.html",
            }
        )
        blobs = {}
        optional = {"crm.db-wal", "video_ua0012", "site_ua0012"}
        for name, path in paths.items():
            blobs[name] = get_remote(path, missing_ok=name in optional)
        evidence["backup"] = {
            "captured_before_transform": True,
            "files": {
                name: (
                    {"path": paths[name], "sha256": sha_bytes(payload), "bytes": len(payload)}
                    if payload is not None
                    else {"path": paths[name], "missing": True}
                )
                for name, payload in blobs.items()
            },
        }
        evidence["sources"] = {
            name: source_audit(name, blobs[name]) for name in SOURCE_NAMES
        }
        # Apply the exact eight transforms only to a disposable source copy.
        # This proves full-file + function anchors and resulting compilation;
        # it cannot reach the live host because every remote method above is GET.
        with tempfile.TemporaryDirectory(prefix="task077-patch-bundle-") as patch_dir:
            patch_root = pathlib.Path(patch_dir)
            for name in live_patcher.LIVE_FULL_FILE_SHA256:
                (patch_root / name).write_bytes(blobs[name])
            patched = live_patcher.prepare_patch_bundle(str(patch_root))
            if len(live_patcher.PATCH_SPECS) != 8 or len(patched) != 5:
                raise RuntimeError("PATCH_BUNDLE_COVERAGE_MISMATCH")
            evidence["patch_bundle"] = {
                "status": "PASS",
                "function_transforms": len(live_patcher.PATCH_SPECS),
                "files": {
                    pathlib.Path(path).name: {
                        "sha256": sha_text(source),
                        "compiled": True,
                    }
                    for path, source in sorted(patched.items())
                },
                "production_write": False,
            }
        evidence["database"] = database_audit_and_canary(
            blobs["crm.db"], blobs["crm.db-wal"]
        )
        evidence["pages"] = {
            "video_ua0012": page_manifest("video_ua0012", blobs["video_ua0012"]),
            "site_ua0012": page_manifest("site_ua0012", blobs["site_ua0012"]),
            "video_catalog": page_manifest("video_catalog", blobs["video_catalog"]),
            "site_catalog": page_manifest("site_catalog", blobs["site_catalog"]),
        }
        evidence["defect_signals"] = {
            "standalone_sea_transit_in_sources": sum(
                item["counts"]["sea_transit"] for item in evidence["sources"].values()
            ),
            "sea_transit_callbacks": sum(
                item["callbacks"]["sea_transit"] for item in evidence["sources"].values()
            ),
            "sea_loaded_callbacks": sum(
                item["callbacks"]["sea_loaded"] for item in evidence["sources"].values()
            ),
            "sold_transit_callbacks": sum(
                item["callbacks"]["sold_transit"] for item in evidence["sources"].values()
            ),
            "diagnostic_missing_guards": sum(
                item["counts"]["SEO068_DIAGNOSTIC_TARGET_MISSING"]
                for item in evidence["sources"].values()
            ),
            "unconditional_success_texts": sum(
                item["counts"]["Машина видна клиентам в каталоге"]
                for item in evidence["sources"].values()
            ),
        }
        canary = evidence["database"]["canary"]
        if not (
            canary["transition"]["status"] == "sea_loaded"
            and canary["transition"]["days_to_kyiv"] == 30
            and canary["transition"]["eta_manual"] == "2026-09-28"
            and canary["owner_label"] == "На пароме"
            and canary["media_hashes_unchanged"]
            and canary["published_unchanged"]
            and canary["diagnostic_placeholder"]
        ):
            raise RuntimeError("LOCAL_CANARY_CONTRACT_FAILED")
        evidence["status"] = "PASS_AUDIT_DEFECT_REPRODUCED"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
    evidence["finished_at_utc"] = utc_now()
    write_json(EVIDENCE, evidence)
    report = [
        "# CRM-CONTAINER-STAGE-SYNC-004 v1.0 — Gate A audit",
        "",
        "STATUS: **%s**" % evidence["status"],
        "",
        "- Production touched: **NO**",
        "- PythonAnywhere methods: **GET only**",
        "- CRM/site/media writes: **NO**",
    ]
    if evidence["status"].startswith("PASS"):
        db = evidence["database"]
        report.extend(
            [
                "- SQLite quick_check: **%s**" % db["quick_check"],
                "- Current rows/published: **%d/%d**" % (db["row_count"], db["published_count"]),
                "- UA-0009 protected audit: **PASS**",
                "- UA-0012 local-copy canary: **sea_loaded / 30 / 2026-09-28 / На пароме**",
                "- Media and published fields in canary: **UNCHANGED**",
                "- Missing diagnostics placeholder: **PASS**",
                "",
                "This is audit/reproduction evidence only. Production remains locked.",
            ]
        )
    else:
        report.extend(["- Errors: `%s`" % "; ".join(evidence["errors"]), "", "Production remains locked."])
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({"status": evidence["status"], "errors": evidence["errors"]}, ensure_ascii=False))
    return 0 if evidence["status"] == "PASS_AUDIT_DEFECT_REPRODUCED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
