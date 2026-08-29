#!/usr/bin/env python3
"""GET-only live Gate A and local canary for TASK 084.

Downloads immutable snapshots from PythonAnywhere with GET requests only,
applies the owner's UA-0011 Korea reset to in-memory copies, and proves the
catalog result without writing to CRM, PythonAnywhere, or public pages.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parent
STAGE_GUARD_ROOT = ROOT.parent / "task_075_stage_guard"
sys.path.insert(0, str(STAGE_GUARD_ROOT))

from stage_guard import (  # noqa: E402
    StageGuardError,
    audit_catalog,
    enforce_catalog,
    extract_main_photo,
    stage_number,
)


TASK_ID = "task_084"
CONTRACT_ID = "UA-0011-KOREA-CARD-RESET-001-V1.0"
API = "https://www.pythonanywhere.com/api/v0/user/Carix/files/path"
REMOTE_ROOT = "/home/Carix"
PUBLIC = "https://www.uaart.com.ua"
MAX_FILE = 80_000_000
TARGET_CARD = "UA-0011"
TARGET_VIN = "KMHE341DBKA544289"
TARGET_STATUS = "kr_bought"
TRANSPORT_FIELDS = ("sea_container", "sea_date_out", "eta_manual", "days_to_kyiv")
EVIDENCE = ROOT / "evidence" / "live_gate_a.json"
REPORT = ROOT / "TASK_084_REPORT.md"
MATRIX = ROOT / "before_after_matrix.md"
CANARY = ROOT / "canary"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def stable_json(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def sha_value(value) -> str:
    return sha_bytes(stable_json(value))


def get_remote(path: str, *, missing: bool = False, limit: int = MAX_FILE) -> bytes | None:
    """Fetch one remote file with bounded transient retries and no write verb."""
    url = API + urllib.parse.quote(path, safe="/")
    last_error = None
    for attempt in range(1, 4):
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Authorization": "Token " + os.environ["PYTHONANYWHERE_API_TOKEN"],
                "User-Agent": "ua-art-task084-get-only/1",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                data = response.read(limit + 1)
            if len(data) > limit:
                raise RuntimeError("REMOTE_FILE_TOO_LARGE:" + pathlib.PurePosixPath(path).name)
            return data
        except urllib.error.HTTPError as exc:
            if missing and exc.code == 404:
                return None
            last_error = exc
            if exc.code < 500 or attempt == 3:
                raise
        except (TimeoutError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt == 3:
                raise
        time.sleep(attempt * 2)
    raise RuntimeError("GET_RETRY_EXHAUSTED:%s:%s" % (path, last_error))


def json_list(value) -> list:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        loaded = json.loads(value) if isinstance(value, str) else value
    except Exception:
        return []
    return loaded if isinstance(loaded, list) else []


def load_database(db_bytes: bytes, wal_bytes: bytes | None):
    with tempfile.TemporaryDirectory(prefix="task084-db-") as directory:
        db_path = pathlib.Path(directory) / "crm.db"
        db_path.write_bytes(db_bytes)
        if wal_bytes:
            pathlib.Path(str(db_path) + "-wal").write_bytes(wal_bytes)
        con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA query_only=ON")
            quick = con.execute("PRAGMA quick_check").fetchone()[0]
            schema = [dict(row) for row in con.execute("PRAGMA table_info(cars)").fetchall()]
            rows = [dict(row) for row in con.execute(
                "SELECT * FROM cars WHERE auto_number GLOB 'UA-*' ORDER BY auto_number,id"
            ).fetchall()]
            target = con.execute(
                "SELECT * FROM cars WHERE auto_number=? ORDER BY id DESC LIMIT 1", (TARGET_CARD,)
            ).fetchone()
            if target is None:
                raise StageGuardError("UA0011_NOT_FOUND")
            target = dict(target)
            audit = []
            tables = {row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            if "audit" in tables:
                audit = [dict(row) for row in con.execute(
                    "SELECT * FROM audit WHERE entity_id=? AND entity_type IN ('car','cars') "
                    "ORDER BY id DESC LIMIT 30", (target.get("id"),)
                ).fetchall()]
        finally:
            con.close()
    return quick, schema, rows, target, audit


def manifest(value) -> dict:
    items = json_list(value)
    return {
        "count": len(items),
        "ordered_entry_sha256": [sha_value(item) for item in items],
        "manifest_sha256": sha_value(items),
    }


def add_base(source: str, base: str) -> str:
    source = re.sub(r"<base\b[^>]*>", "", source, flags=re.I)
    opening = re.search(r"<head\b[^>]*>", source, re.I)
    if opening is None:
        raise StageGuardError("CANARY_HEAD_MISSING")
    return source[:opening.end()] + '<base href="%s/">' % base.rstrip("/") + source[opening.end():]


def write_json(path: pathlib.Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def transport_snapshot(row: dict, present_fields: list[str]) -> dict:
    return {name: row.get(name) for name in ["status", *present_fields]}


def public_row(row: dict) -> dict:
    return {
        "auto_number": row.get("auto_number"),
        "brand": row.get("brand"),
        "model": row.get("model"),
        "year": row.get("year"),
        "status": row.get("status"),
        "stage": stage_number(row),
        "photos": len(json_list(row.get("photos"))),
        "videos": len(json_list(row.get("videos"))),
    }


def render_matrix(evidence: dict) -> str:
    before = evidence.get("ua0011", {}).get("before", {})
    after = evidence.get("ua0011", {}).get("after", {})
    lines = [
        "# UA-0011 Before/After matrix — TASK 084", "",
        "Live Gate A status: **%s**" % evidence.get("status", "FAIL"), "",
        "| CRM field | Before (live GET-only) | After (sandbox target) |",
        "|---|---|---|",
    ]
    for field in ["status", *evidence.get("ua0011", {}).get("transport_fields", [])]:
        lines.append("| `%s` | `%s` | `%s` |" % (field, before.get(field), after.get(field)))
    lines.extend([
        "", "- Other CRM fields SHA-256 before: `%s`" % evidence.get("ua0011", {}).get("protected_fields_sha256_before", ""),
        "- Other CRM fields SHA-256 after: `%s`" % evidence.get("ua0011", {}).get("protected_fields_sha256_after", ""),
        "- Media manifest preserved: **%s**" % ("PASS" if evidence.get("ua0011", {}).get("media_preserved") else "FAIL"),
        "- First facade photo resolved: **%s**" % ("PASS" if evidence.get("ua0011", {}).get("resolved_main_photo") else "FAIL"),
        "- Production touched: **NO**", "",
    ])
    return "\n".join(lines)


def main() -> int:
    evidence = {
        "task_id": TASK_ID,
        "contract_id": CONTRACT_ID,
        "status": "FAIL",
        "mode": "LIVE_GET_ONLY_LOCAL_SANDBOX_CANARY",
        "started_at_utc": now(),
        "production_touched": False,
        "pythonanywhere_methods": ["GET"],
        "crm_write": False,
        "site_write": False,
        "media_write": False,
        "runtime_llm_tokens": 0,
        "errors": [],
    }
    try:
        if not os.environ.get("PYTHONANYWHERE_API_TOKEN"):
            raise RuntimeError("PYTHONANYWHERE_API_TOKEN_MISSING")
        paths = {
            "crm_db": REMOTE_ROOT + "/crm.db",
            "crm_wal": REMOTE_ROOT + "/crm.db-wal",
            "video_catalog": REMOTE_ROOT + "/video/katalog.html",
            "site_catalog": REMOTE_ROOT + "/site/katalog.html",
            "master_card": REMOTE_ROOT + "/master_card.py",
            "publikaciya": REMOTE_ROOT + "/publikaciya.py",
            "stranica": REMOTE_ROOT + "/stranica.py",
            "yadro": REMOTE_ROOT + "/yadro.py",
        }
        blobs = {
            name: get_remote(path, missing=(name == "crm_wal"))
            for name, path in paths.items()
        }
        evidence["backup"] = {
            "captured_before_transform": True,
            "files": {
                name: ({"path": paths[name], "sha256": sha_bytes(data), "bytes": len(data)}
                       if data is not None else {"path": paths[name], "missing": True})
                for name, data in blobs.items()
            },
        }
        quick, schema, rows, ua11, audit = load_database(blobs["crm_db"], blobs["crm_wal"])
        if quick != "ok":
            raise StageGuardError("CRM_QUICK_CHECK:" + str(quick))
        all_identifiers = [str(row.get("auto_number") or "").upper() for row in rows]
        if len(all_identifiers) != len(set(all_identifiers)):
            raise StageGuardError("DUPLICATE_PUBLISHED_CARD_IDS")
        scoped_rows = []
        for row in rows:
            identifier = str(row.get("auto_number") or "").upper()
            match = re.fullmatch(r"UA-(\d{4,})", identifier)
            if match and 1 <= int(match.group(1)) <= 11:
                scoped_rows.append(row)
        identifiers = [str(row.get("auto_number") or "").upper() for row in scoped_rows]
        if TARGET_CARD not in identifiers or "UA-0009" not in identifiers:
            raise StageGuardError("MANDATORY_CARD_MISSING")
        if len(identifiers) != 11 or len(set(identifiers)) != 11:
            raise StageGuardError("UA0001_UA0011_SCOPE_INCOMPLETE")
        columns = {item["name"] for item in schema}
        if "status" not in columns:
            raise StageGuardError("STATUS_FIELD_MISSING")
        present_transport = [name for name in TRANSPORT_FIELDS if name in columns]
        if "sea_container" not in present_transport:
            raise StageGuardError("SEA_CONTAINER_FIELD_MISSING")
        if not any(name in present_transport for name in ("sea_date_out", "eta_manual", "days_to_kyiv")):
            raise StageGuardError("ARRIVAL_OR_DAYS_FIELD_MISSING")

        after = copy.deepcopy(ua11)
        after["status"] = TARGET_STATUS
        for field in present_transport:
            after[field] = None
        allowed = {"status", *present_transport}
        changed = {
            key: {"before": ua11.get(key), "after": after.get(key)}
            for key in sorted(set(ua11) | set(after)) if ua11.get(key) != after.get(key)
        }
        unexpected = sorted(set(changed) - allowed)
        if unexpected:
            raise StageGuardError("UNEXPECTED_SANDBOX_DELTA:" + ",".join(unexpected))
        protected_before = {key: value for key, value in ua11.items() if key not in allowed}
        protected_after = {key: value for key, value in after.items() if key not in allowed}
        if protected_before != protected_after:
            raise StageGuardError("PROTECTED_FIELDS_CHANGED")

        photos = {}
        page_manifest = {}
        for identifier in identifiers:
            selected = ""
            for variant in ("video", "site"):
                remote = "%s/%s/%s.html" % (REMOTE_ROOT, variant, identifier)
                page = get_remote(remote, missing=True, limit=3_000_000)
                page_manifest[variant + ":" + identifier] = (
                    {"sha256": sha_bytes(page), "bytes": len(page)} if page else {"missing": True}
                )
                if page and not selected:
                    selected = extract_main_photo(
                        page.decode("utf-8", "replace"),
                        "%s/%s/%s.html" % (PUBLIC, variant, identifier), identifier,
                    )
            photos[identifier] = selected
        if not photos.get(TARGET_CARD):
            raise StageGuardError("UA0011_MAIN_PHOTO_UNRESOLVED")
        if not json_list(ua11.get("photos")):
            raise StageGuardError("UA0011_CRM_PHOTOS_EMPTY")
        evidence["backup"]["pages"] = page_manifest

        transformed_rows = [
            after if row.get("auto_number") == TARGET_CARD else copy.deepcopy(row)
            for row in scoped_rows
        ]
        CANARY.mkdir(parents=True, exist_ok=True)
        canaries = {}
        repeated = {}
        for variant, blob_name in (("video", "video_catalog"), ("site", "site_catalog")):
            original = blobs[blob_name].decode("utf-8", "replace")
            candidates = []
            audits = []
            for _ in range(10):
                candidate = enforce_catalog(original, transformed_rows, photos)
                audit_result = audit_catalog(candidate, transformed_rows)
                if audit_result.get("status") != "PASS":
                    raise StageGuardError("%s_CANARY:%s" % (variant, ";".join(audit_result.get("errors", []))))
                candidates.append(candidate)
                audits.append(audit_result)
            hashes = [sha_bytes(item.encode("utf-8")) for item in candidates]
            if len(set(hashes)) != 1:
                raise StageGuardError("%s_TEN_RUN_DRIFT" % variant.upper())
            audit_result = audits[-1]
            card = audit_result["cards"].get(TARGET_CARD, {})
            if not (card.get("count") == 1 and card.get("stage") == 1 and
                    card.get("category") == "korea" and card.get("template") and
                    card.get("photo") and card.get("absolute_photo")):
                raise StageGuardError("%s_UA0011_KOREA_TEMPLATE_FAIL" % variant.upper())
            target = CANARY / (variant + "-katalog.html")
            target.write_text(add_base(candidates[-1], "%s/%s" % (PUBLIC, variant)), encoding="utf-8")
            canaries[variant] = {
                "before_sha256": sha_bytes(blobs[blob_name]),
                "sandbox_sha256": hashes[-1],
                "ten_runs": 10,
                "unique_run_hashes": len(set(hashes)),
                "audit": audit_result,
                "canary_path": str(target.relative_to(ROOT)),
            }
            repeated[variant] = hashes

        ua9_after = next(row for row in transformed_rows if row.get("auto_number") == "UA-0009")
        ua9_cards = [canaries[v]["audit"]["cards"].get("UA-0009", {}) for v in ("video", "site")]
        ua9_safe = all(card.get("count") == 1 and card.get("photo") and card.get("stage_ok") for card in ua9_cards)
        if not ua9_safe:
            raise StageGuardError("UA0009_SAFE_GATE_FAIL")

        evidence["database"] = {
            "quick_check": quick,
            "published": sum(1 for row in rows if int(row.get("published") or 0) == 1),
            "known_cards": len(rows),
            "unique_ids": len(set(all_identifiers)),
            "canary_scope": identifiers,
            "out_of_scope_published": sorted(
                str(row.get("auto_number") or "").upper()
                for row in rows
                if int(row.get("published") or 0) == 1
                and str(row.get("auto_number") or "").upper() not in set(identifiers)
            ),
            "rows": [public_row(row) for row in rows],
        }
        evidence["ua0011"] = {
            "schema_fields": sorted(columns),
            "transport_fields": present_transport,
            "before": transport_snapshot(ua11, present_transport),
            "after": transport_snapshot(after, present_transport),
            "changed_fields": changed,
            "protected_fields_sha256_before": sha_value(protected_before),
            "protected_fields_sha256_after": sha_value(protected_after),
            "media": {"photos": manifest(ua11.get("photos")), "videos": manifest(ua11.get("videos"))},
            "media_preserved": ua11.get("photos") == after.get("photos") and ua11.get("videos") == after.get("videos"),
            "resolved_main_photo": True,
            "resolved_main_photo_url_sha256": sha_value(photos[TARGET_CARD]),
            "audit_tail_sha256": sha_value(audit),
            "sandbox_stage": stage_number(after),
        }
        evidence["canary"] = canaries
        evidence["ten_run_guard"] = {
            "runs": 10,
            "duplicates": 0,
            "drift": 0,
            "unexpected_changes": 0,
        }
        evidence["ua0009"] = {
            "safe_to_publish_without_damaging_existing_cards": True,
            "status": ua9_after.get("status"),
            "stage": stage_number(ua9_after),
            "photo_preserved": True,
        }
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))

    evidence["finished_at_utc"] = now()
    write_json(EVIDENCE, evidence)
    MATRIX.write_text(render_matrix(evidence), encoding="utf-8")
    lines = [
        "# UA-0011-KOREA-CARD-RESET-001 v1.0 — LIVE GATE A", "",
        "STATUS: **%s**" % evidence["status"], "",
        "- Production touched: **NO**",
        "- PythonAnywhere methods: **GET only**",
        "- CRM/site/media writes: **NO**",
    ]
    if evidence["status"] == "PASS":
        lines.extend([
            "- Fresh live CRM snapshot and backup SHA: **PASS**",
            "- UA-0011 sandbox target: **В Корее**, container/date/days empty: **PASS**",
            "- UA-0011 full card with first facade photo: **PASS**",
            "- Ten repeated canary runs: **10/10 PASS; duplicates 0; drift 0**",
            "- UA-0009 safety check: **SAFE TO PUBLISH UA-0009: YES**",
            "", "Production remains locked pending a separate written owner command.",
        ])
    else:
        lines.extend(["- Errors: `%s`" % "; ".join(evidence["errors"]), "", "Production remains locked."])
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("TASK084_LIVE_GATE_A_" + evidence["status"])
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
