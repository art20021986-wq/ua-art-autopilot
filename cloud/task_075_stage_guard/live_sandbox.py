#!/usr/bin/env python3
"""GET-only live audit and local GitHub-runner canary for TASK 075."""
from __future__ import annotations

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

from stage_guard import CONTRACT_ID, StageGuardError, audit_catalog, enforce_catalog, extract_main_photo, stage_number


ROOT = pathlib.Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence" / "sandbox.json"
REPORT = ROOT / "TASK_075_REPORT.md"
CANARY = ROOT / "canary"
API = "https://www.pythonanywhere.com/api/v0/user/Carix/files/path"
REMOTE_ROOT = "/home/Carix"
PUBLIC = "https://www.uaart.com.ua"
MAX_FILE = 80_000_000


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get_remote(path: str, missing: bool = False, limit: int = MAX_FILE) -> bytes | None:
    request = urllib.request.Request(
        API + urllib.parse.quote(path, safe="/"),
        method="GET",
        headers={"Authorization": "Token " + os.environ["PYTHONANYWHERE_API_TOKEN"],
                 "User-Agent": "ua-art-task075-get-only/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        if missing and exc.code == 404:
            return None
        raise
    if len(data) > limit:
        raise RuntimeError("REMOTE_FILE_TOO_LARGE:" + pathlib.PurePosixPath(path).name)
    return data


def probe_photo(url: str) -> dict:
    request = urllib.request.Request(
        url, method="GET",
        headers={"Range": "bytes=0-65535", "User-Agent": "ua-art-task075-photo-probe/1"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read(65_536)
        status = int(response.status)
        content_type = str(response.headers.get_content_type() or "")
    if status not in (200, 206) or not content_type.startswith("image/") or len(data) < 128:
        raise StageGuardError("PHOTO_HTTP_INVALID")
    return {"status": status, "content_type": content_type, "sample_bytes": len(data)}


def load_rows(db_bytes: bytes, wal_bytes: bytes | None):
    with tempfile.TemporaryDirectory(prefix="task075-db-") as directory:
        db_path = pathlib.Path(directory) / "crm.db"
        db_path.write_bytes(db_bytes)
        if wal_bytes:
            pathlib.Path(str(db_path) + "-wal").write_bytes(wal_bytes)
        con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA query_only=ON")
            quick = con.execute("PRAGMA quick_check").fetchone()[0]
            rows = [dict(row) for row in con.execute(
                "SELECT * FROM cars WHERE published=1 ORDER BY auto_number, id").fetchall()]
        finally:
            con.close()
    return quick, rows


def sanitized_row(row):
    return {
        "auto_number": row.get("auto_number"), "status": row.get("status"),
        "stage": stage_number(row), "brand": row.get("brand"), "model": row.get("model"),
        "year": row.get("year"), "photos": len(json.loads(row.get("photos") or "[]")),
        "videos": len(json.loads(row.get("videos") or "[]")),
    }


def write_json(path: pathlib.Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def add_base(source: str, base: str) -> str:
    source = re.sub(r"<base\b[^>]*>", "", source, flags=re.I)
    opening = re.search(r"<head\b[^>]*>", source, re.I)
    if opening is None:
        raise StageGuardError("CANARY_HEAD_MISSING")
    # The base must precede stylesheet links; inserting it at </head> is too
    # late for parser-initiated CSS requests in the mobile screenshot.
    position = opening.end()
    return source[:position] + '<base href="%s/">' % base.rstrip("/") + source[position:]


def main() -> int:
    evidence = {
        "task_id": "task_075", "contract_id": CONTRACT_ID, "status": "FAIL",
        "mode": "BACKUP_GET_ONLY_LOCAL_SANDBOX_CANARY", "production_touched": False,
        "pythonanywhere_methods": ["GET"], "crm_write": False, "site_write": False,
        "media_write": False, "runtime_llm_tokens": 0, "errors": [],
        "started_at_utc": now(),
    }
    try:
        paths = {
            "crm_db": REMOTE_ROOT + "/crm.db",
            "crm_wal": REMOTE_ROOT + "/crm.db-wal",
            "video_catalog": REMOTE_ROOT + "/video/katalog.html",
            "site_catalog": REMOTE_ROOT + "/site/katalog.html",
            "stranica": REMOTE_ROOT + "/stranica.py",
            "master_card": REMOTE_ROOT + "/master_card.py",
            "yadro": REMOTE_ROOT + "/yadro.py",
            "publikaciya": REMOTE_ROOT + "/publikaciya.py",
        }
        blobs = {}
        for name, path in paths.items():
            blobs[name] = get_remote(path, missing=(name == "crm_wal"))
        evidence["backup"] = {
            "captured_before_transform": True,
            "files": {name: ({"path": paths[name], "sha256": sha(data), "bytes": len(data)}
                              if data is not None else {"path": paths[name], "missing": True})
                      for name, data in blobs.items()},
        }
        quick, rows = load_rows(blobs["crm_db"], blobs["crm_wal"])
        identifiers = [str(row.get("auto_number") or "").upper() for row in rows]
        if quick != "ok":
            raise StageGuardError("CRM_QUICK_CHECK:" + str(quick))
        if len(rows) < 11 or len(set(identifiers)) != len(rows):
            raise StageGuardError("EXPECTED_AT_LEAST_11_UNIQUE_CARDS:%d:%d" %
                                  (len(rows), len(set(identifiers))))
        if "UA-0009" not in identifiers or "UA-0011" not in identifiers:
            raise StageGuardError("MANDATORY_CARD_MISSING")
        evidence["database"] = {"quick_check": quick, "published": len(rows),
                                "unique_ids": len(set(identifiers)),
                                "rows": [sanitized_row(row) for row in rows],
                                "ua0009_safe": True}

        photos = {}
        photo_http = {}
        page_manifest = {}
        for identifier in identifiers:
            # New CRM cards may have uploaded media before their public detail
            # page exists.  Resolve the established public media convention
            # first, then retain existing detail pages as a compatibility
            # fallback.  Every selected URL is still verified with a real GET.
            candidates = [
                ("%s/video/foto/%s/m/001.jpg" %
                 (PUBLIC, urllib.parse.quote(identifier, safe="")), "crm_public_media"),
                ("%s/site/foto/%s/m/001.jpg" %
                 (PUBLIC, urllib.parse.quote(identifier, safe="")), "crm_public_media"),
            ]
            for variant in ("video", "site"):
                remote = "%s/%s/%s.html" % (REMOTE_ROOT, variant, identifier)
                page = get_remote(remote, missing=True, limit=3_000_000)
                page_manifest[variant + ":" + identifier] = (
                    {"sha256": sha(page), "bytes": len(page)} if page else {"missing": True})
                if page:
                    candidate = extract_main_photo(
                        page.decode("utf-8", "replace"),
                        "%s/%s/%s.html" % (PUBLIC, variant, identifier), identifier)
                    if candidate and candidate not in [value for value, _source in candidates]:
                        candidates.append((candidate, "existing_detail_page"))
            selected = ""
            failures = []
            for candidate, source in candidates:
                try:
                    check = probe_photo(candidate)
                    selected = candidate
                    photo_http[identifier] = {**check, "source": source}
                    break
                except Exception as exc:
                    failures.append(type(exc).__name__)
            if not selected:
                raise StageGuardError("PUBLIC_PHOTO_HTTP_FAILED:%s:%s" %
                                      (identifier, ",".join(failures) or "NO_CANDIDATE"))
            photos[identifier] = selected
        evidence["backup"]["pages"] = page_manifest
        evidence["photo_resolution"] = {
            identifier: {"resolved": bool(value), "url_sha256": sha(value.encode()) if value else None,
                         **photo_http.get(identifier, {})}
            for identifier, value in sorted(photos.items())
        }
        ua11 = next(row for row in rows if row.get("auto_number") == "UA-0011")
        if len(json.loads(ua11.get("photos") or "[]")) < 1:
            raise StageGuardError("UA0011_CRM_PHOTOS_EMPTY")
        if not photos.get("UA-0011"):
            raise StageGuardError("UA0011_PUBLIC_PHOTO_UNRESOLVED")

        CANARY.mkdir(parents=True, exist_ok=True)
        catalogs = {}
        for variant, key in (("video", "video_catalog"), ("site", "site_catalog")):
            original = blobs[key].decode("utf-8", "replace")
            candidate = enforce_catalog(original, rows, photos)
            audit = audit_catalog(candidate, rows)
            if audit["status"] != "PASS":
                raise StageGuardError("%s_CANARY:%s" % (variant, ";".join(audit["errors"])))
            canary = add_base(candidate, "%s/%s" % (PUBLIC, variant))
            target = CANARY / (variant + "-katalog.html")
            target.write_text(canary, encoding="utf-8")
            catalogs[variant] = {
                "before_sha256": sha(blobs[key]), "after_sha256": sha(candidate.encode()),
                "changed": candidate.encode() != blobs[key], "audit": audit,
                "canary_path": str(target.relative_to(ROOT)),
            }
        evidence["canary"] = catalogs
        evidence["ua0011"] = {
            "crm_photos": len(json.loads(ua11.get("photos") or "[]")),
            "resolved_main_photo": True, "stage": stage_number(ua11),
            "category": {1: "korea", 2: "more", 3: "gruzia", 4: "kiev"}[stage_number(ua11)],
            "video_catalog_photo": catalogs["video"]["audit"]["cards"]["UA-0011"]["photo"],
            "site_catalog_photo": catalogs["site"]["audit"]["cards"]["UA-0011"]["photo"],
        }
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
    evidence["finished_at_utc"] = now()
    write_json(EVIDENCE, evidence)
    report = [
        "# CRM-CATALOG-STAGE-GUARD-003 v1.0 — SANDBOX/CANARY",
        "", "STATUS: **%s**" % evidence["status"], "",
        "- Production touched: **NO**",
        "- PythonAnywhere access: **GET only**",
        "- CRM writes: **NO**",
        "- Site/media writes: **NO**",
    ]
    if evidence["status"] == "PASS":
        report.extend([
            "- Backup manifest captured before transform: **PASS**",
            "- Current published cards: **%d/%d unique**" % (
                evidence["database"]["published"], evidence["database"]["unique_ids"]),
            "- UA-0009 protected check: **PASS**",
            "- UA-0011 photo restored in both local canaries: **PASS**",
            "- Unified card template and absolute main photo: **%d/%d PASS**" % (
                evidence["database"]["published"], evidence["database"]["published"]),
            "- Native stage filter compatibility and ordered placement: **%d/%d PASS**" % (
                evidence["database"]["published"], evidence["database"]["published"]),
            "- Public photo HTTP probes: **%d/%d PASS**" % (
                evidence["database"]["published"], evidence["database"]["published"]),
            "- Stage routing and universal category filter: **PASS**",
            "- Old ferry route / internal state leakage: **0**",
            "", "Production remains locked pending a separate owner command.",
        ])
    else:
        report.extend(["- Errors: `%s`" % "; ".join(evidence["errors"]),
                       "", "Production remains locked."])
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("TASK075_SANDBOX_" + evidence["status"])
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
