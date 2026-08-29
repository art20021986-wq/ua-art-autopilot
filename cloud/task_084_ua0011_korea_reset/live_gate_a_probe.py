#!/usr/bin/env python3
"""Fresh GET-only Gate A for the superseding UA-0011 Korea directive."""
from __future__ import annotations

import ast
import copy
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import tempfile
import urllib.error
import urllib.parse
import urllib.request


HERE = pathlib.Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence/live_gate_a.json"
COVER_BASE = HERE / "evidence/ua0011_cover"
API = "https://www.pythonanywhere.com/api/v0/user/Carix/files/path"
ROOT = "/home/Carix"
TARGET = "UA-0011"
VIN = "KMHE341DBKA544289"
TARGET_FIELDS = {"status": "kr_bought", "sea_container": None, "eta_manual": None}
SOURCE_FILES = ("cars_ui.py", "db.py", "start_safe.py", "ai_filter.py", "team_bot.py")
MAX_BYTES = 80_000_000


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def get_remote(path: str, missing: bool = False, limit: int = MAX_BYTES):
    request = urllib.request.Request(
        API + urllib.parse.quote(path, safe="/"), method="GET",
        headers={"Authorization": "Token " + os.environ["PYTHONANYWHERE_API_TOKEN"],
                 "User-Agent": "ua-art-task084-live-gate-a/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=70) as response:
            data = response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        if missing and exc.code == 404:
            return None
        raise
    if len(data) > limit:
        raise RuntimeError("REMOTE_FILE_TOO_LARGE:" + path)
    return data


def unpack_json(value):
    if not value:
        return []
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def scalar_hash(value) -> str:
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode())


def db_evidence(raw: bytes, wal: bytes | None):
    with tempfile.TemporaryDirectory(prefix="task084-live-") as directory:
        path = pathlib.Path(directory) / "crm.db"
        path.write_bytes(raw)
        if wal:
            pathlib.Path(str(path) + "-wal").write_bytes(wal)
        con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA query_only=ON")
            quick = con.execute("PRAGMA quick_check").fetchone()[0]
            row = con.execute("SELECT * FROM cars WHERE auto_number=?", (TARGET,)).fetchone()
            if row is None:
                raise RuntimeError("UA0011_ROW_MISSING")
            card = dict(row)
            inventory = [dict(item) for item in con.execute(
                "SELECT id,auto_number,published,status,review_status FROM cars ORDER BY auto_number,id"
            ).fetchall()]
            columns = [dict(item) for item in con.execute("PRAGMA table_info(cars)").fetchall()]
            conventions = {}
            for field in ("sea_container", "eta_manual"):
                if field in card:
                    values = [item[0] for item in con.execute("SELECT %s FROM cars" % field)]
                    conventions[field] = {
                        "null": sum(value is None for value in values),
                        "empty": sum(value == "" for value in values),
                        "nonempty": sum(value not in (None, "") for value in values),
                    }
            audit = [dict(item) for item in con.execute(
                "SELECT * FROM audit WHERE entity_id=? AND entity_type IN ('car','cars') "
                "ORDER BY id DESC LIMIT 40", (card["id"],)
            ).fetchall()]
        finally:
            con.close()
    if quick != "ok":
        raise RuntimeError("CRM_QUICK_CHECK:" + str(quick))
    photos = unpack_json(card.get("photos"))
    videos = unpack_json(card.get("videos"))
    condition_photos = unpack_json(card.get("condition_photos"))
    condition_videos = unpack_json(card.get("condition_videos"))
    media = []
    for kind, values in (
        ("photo", photos), ("video", videos),
        ("condition_photo", condition_photos), ("condition_video", condition_videos),
    ):
        for index, item in enumerate(values):
            normalized = item if isinstance(item, dict) else {"file_id": item}
            media.append({"kind": kind, "index": index, "value": normalized,
                          "sha256": scalar_hash(normalized)})
    excluded = set(TARGET_FIELDS)
    field_hashes = {key: scalar_hash(value) for key, value in sorted(card.items()) if key not in excluded}
    return {
        "quick_check": quick,
        "row": card,
        "columns": columns,
        "empty_conventions": conventions,
        "other_fields_sha256": field_hashes,
        "media_manifest": media,
        "media_counts": {
            "photos": len(photos), "videos": len(videos),
            "condition_photos": len(condition_photos),
            "condition_videos": len(condition_videos), "total": len(media),
        },
        "audit": audit,
        "inventory": inventory,
        "published_ids": [str(item.get("auto_number") or "").upper() for item in inventory
                          if int(item.get("published") or 0) == 1],
    }


def image_candidates(html: str):
    values = []
    for match in re.finditer(r"<(?:img|source)\b[^>]*>", html, re.I):
        tag = match.group(0)
        for attr in ("src", "data-src", "poster"):
            found = re.search(r"\b%s\s*=\s*['\"]([^'\"]+)" % attr, tag, re.I)
            if found and found.group(1) not in values:
                values.append(found.group(1))
    return values


def remote_image_path(variant: str, page_url: str, value: str):
    absolute = urllib.parse.urljoin(page_url, value)
    parsed = urllib.parse.urlparse(absolute)
    path = urllib.parse.unquote(parsed.path)
    if path.startswith("/video/") or path.startswith("/site/"):
        return ROOT + path, absolute
    relative = urllib.parse.urlparse(urllib.parse.urljoin(page_url, value)).path.lstrip("/")
    if relative.startswith(variant + "/"):
        return ROOT + "/" + relative, absolute
    return ROOT + "/" + variant + "/" + relative, absolute


def cover_evidence():
    pages = {}
    chosen = None
    cover_bytes = None
    for variant in ("video", "site"):
        raw = get_remote(ROOT + "/" + variant + "/" + TARGET + ".html")
        text = raw.decode("utf-8", "replace")
        candidates = image_candidates(text)
        page_url = "https://www.uaart.com.ua/%s/%s.html" % (variant, TARGET)
        pages[variant] = {"sha256": sha(raw), "bytes": len(raw), "image_candidates": candidates[:50]}
        if chosen is None:
            for value in candidates:
                path, absolute = remote_image_path(variant, page_url, value)
                try:
                    data = get_remote(path, missing=True, limit=12_000_000)
                except Exception:
                    data = None
                if data and len(data) > 1000:
                    chosen = {"variant": variant, "source": value, "absolute_url": absolute,
                              "remote_path": path, "sha256": sha(data), "bytes": len(data)}
                    cover_bytes = data
                    break
    if not chosen or cover_bytes is None:
        raise RuntimeError("UA0011_COVER_NOT_RESOLVED")
    extension = ".jpg"
    if cover_bytes.startswith(b"\x89PNG"):
        extension = ".png"
    elif cover_bytes.startswith((b"GIF87a", b"GIF89a")):
        extension = ".gif"
    cover_path = pathlib.Path(str(COVER_BASE) + extension)
    cover_path.parent.mkdir(parents=True, exist_ok=True)
    cover_path.write_bytes(cover_bytes)
    own = TARGET.lower() in (chosen["source"] + chosen["remote_path"]).lower()
    foreign = []
    for item in pages.values():
        for value in item["image_candidates"]:
            ids = re.findall(r"UA-[0-9]{4,}", value, re.I)
            foreign.extend(identifier.upper() for identifier in ids if identifier.upper() != TARGET)
    return {"pages": pages, "cover": chosen, "cover_artifact": str(cover_path),
            "first_media_is_own_cover": own, "foreign_card_refs": sorted(set(foreign))}


def sandbox(card: dict, other_hashes: dict):
    current = copy.deepcopy(card)
    snapshots = []
    for _ in range(10):
        candidate = copy.deepcopy(current)
        candidate.update(TARGET_FIELDS)
        snapshots.append(candidate)
        current = candidate
    first = snapshots[0]
    diff = {key: {"before": card.get(key), "after": first.get(key)}
            for key in sorted(set(card) | set(first)) if card.get(key) != first.get(key)}
    after_hashes = {key: scalar_hash(value) for key, value in sorted(first.items())
                    if key not in TARGET_FIELDS}
    return {
        "target": TARGET_FIELDS,
        "before_target": {key: card.get(key) for key in TARGET_FIELDS},
        "after_target": {key: first.get(key) for key in TARGET_FIELDS},
        "diff": diff,
        "other_fields_unchanged": after_hashes == other_hashes,
        "idempotent_10x": all(item == first for item in snapshots),
        "unique_states_after_first": len({json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
                                          for item in snapshots}),
    }


def source_writers(name: str, raw: bytes):
    text = raw.decode("utf-8", "replace")
    tree = ast.parse(text)
    lines = text.splitlines()
    functions = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        end = getattr(node, "end_lineno", node.lineno)
        source = "\n".join(lines[node.lineno - 1:end])
        folded = source.casefold()
        has_field = any(token in folded for token in ("status", "sea_container", "eta_manual", "sea_date_out"))
        has_write = any(token in folded for token in ("update_card_field", "set_field", "update cars", "execute(", "store("))
        if has_field and has_write:
            functions.append({"name": node.name, "lineno": node.lineno, "end_lineno": end,
                              "sha256": sha(source.encode()), "source": source[:16000]})
    return {"sha256": sha(raw), "bytes": len(raw), "writer_functions": functions}


def main() -> int:
    evidence = {
        "task_id": "task_084", "contract_id": "UA-0011-KOREA-CARD-RESET-001-V1.0",
        "mode": "FRESH_GET_ONLY_GATE_A", "status": "FAIL", "production_touched": False,
        "crm_write": False, "pythonanywhere_methods": ["GET"], "errors": [],
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    try:
        raw = get_remote(ROOT + "/crm.db")
        wal = get_remote(ROOT + "/crm.db-wal", missing=True)
        database = db_evidence(raw, wal)
        evidence["database"] = {"sha256": sha(raw), "wal_sha256": sha(wal) if wal else None,
                                **database}
        evidence["cover"] = cover_evidence()
        evidence["sandbox"] = sandbox(database["row"], database["other_fields_sha256"])
        evidence["sources"] = {}
        for name in SOURCE_FILES:
            source = get_remote(ROOT + "/" + name, missing=True, limit=8_000_000)
            if source is not None:
                evidence["sources"][name] = source_writers(name, source)
        row = database["row"]
        checks = {
            "vin": str(row.get("vin") or "").upper() == VIN,
            "status_field": "status" in row,
            "container_field": "sea_container" in row,
            "arrival_eta_field": "eta_manual" in row,
            "status_already_korea": row.get("status") == "kr_bought",
            "target_published": int(row.get("published") or 0) == 1,
            "ua0001_to_ua0011_present": all(
                "UA-%04d" % number in {str(item.get("auto_number") or "").upper()
                                       for item in database["inventory"]}
                for number in range(1, 12)
            ),
            "cover_resolved": evidence["cover"]["first_media_is_own_cover"],
            "no_foreign_media_refs": not evidence["cover"]["foreign_card_refs"],
            "media_present": database["media_counts"]["photos"] > 0,
            "sandbox_other_fields_unchanged": evidence["sandbox"]["other_fields_unchanged"],
            "sandbox_idempotent_10x": evidence["sandbox"]["idempotent_10x"],
        }
        evidence["checks"] = checks
        if not all(checks.values()):
            raise RuntimeError("GATE_A_CHECKS:" + ",".join(key for key, value in checks.items() if not value))
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
    evidence["finished_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
                        encoding="utf-8")
    print(json.dumps({"status": evidence["status"], "checks": evidence.get("checks"),
                      "errors": evidence["errors"]}, ensure_ascii=False))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
