#!/usr/bin/env python3
"""Read-only reconciliation of UA-0011 photo counters."""
from __future__ import annotations

import collections
import hashlib
import json
import os
import pathlib
import sqlite3
import tempfile
import urllib.error
import urllib.parse
import urllib.request


API = "https://www.pythonanywhere.com/api/v0/user/Carix/"
OUT = pathlib.Path("cloud/task_065/evidence/ua0011_counts.json")
MAX_DB = 80_000_000


def get_remote(path: str, missing=False, limit=MAX_DB):
    request = urllib.request.Request(
        API + "files/path" + urllib.parse.quote(path, safe="/"),
        headers={"Authorization": "Token " + os.environ["PYTHONANYWHERE_API_TOKEN"],
                 "User-Agent": "ua-art-task065-ua0011-read/1"},
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


def digest(value) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def media_ids(value):
    if not value:
        return []
    try:
        items = json.loads(value) if isinstance(value, str) else value
    except Exception:
        items = []
    result = []
    for item in items or []:
        file_id = item.get("file_id") if isinstance(item, dict) else item
        if file_id:
            result.append(str(file_id))
    return result


def duplicate_hashes(values):
    counts = collections.Counter(values)
    return sorted(digest(value) for value, count in counts.items() if count > 1)


def main():
    evidence = {"task_id": "task_065", "mode": "READ_ONLY_UA0011_RECONCILIATION",
                "production_touched": False, "llm_tokens": 0, "errors": []}
    with tempfile.TemporaryDirectory(prefix="task065-ua0011-") as directory:
        base = pathlib.Path(directory) / "crm.db"
        base.write_bytes(get_remote("/home/Carix/crm.db"))
        wal = get_remote("/home/Carix/crm.db-wal", missing=True)
        if wal:
            pathlib.Path(str(base) + "-wal").write_bytes(wal)
        con = sqlite3.connect("file:%s?mode=ro" % base, uri=True)
        con.row_factory = sqlite3.Row
        try:
            evidence["quick_check"] = con.execute("PRAGMA quick_check").fetchone()[0]
            cards = [dict(row) for row in con.execute(
                "SELECT * FROM cars WHERE auto_number=? ORDER BY id", ("UA-0011",)).fetchall()]
            evidence["cards_found"] = len(cards)
            if len(cards) != 1:
                raise RuntimeError("UA0011_CARD_COUNT_%d" % len(cards))
            card = cards[0]
            photos = media_ids(card.get("photos"))
            condition = media_ids(card.get("condition_photos"))
            evidence["card"] = {
                "id": card["id"], "photos_total": len(photos),
                "photos_unique": len(set(photos)),
                "photos_duplicate_hashes": duplicate_hashes(photos),
                "condition_total": len(condition),
                "condition_unique": len(set(condition)),
                "updated_at": str(card.get("updated_at") or ""),
                "photo_hashes_ordered": [digest(value) for value in photos],
            }
            columns = [row[1] for row in con.execute("PRAGMA table_info(media)").fetchall()]
            if columns:
                rows = [dict(row) for row in con.execute(
                    "SELECT * FROM media WHERE car_id=? OR auto_number=? ORDER BY id",
                    (card["id"], "UA-0011")).fetchall()]
            else:
                rows = []
            file_values = [str(row.get("file_id") or "") for row in rows if row.get("file_id")]
            by_vid = collections.Counter(str(row.get("vid") or "") for row in rows)
            by_status = collections.Counter(str(row.get("status") or "") for row in rows)
            evidence["media_table"] = {
                "rows_total": len(rows), "unique_file_ids": len(set(file_values)),
                "duplicate_hashes": duplicate_hashes(file_values),
                "by_vid": dict(sorted(by_vid.items())),
                "by_status": dict(sorted(by_status.items())),
                "orphan_vs_card_hashes": sorted(
                    digest(value) for value in set(file_values) - set(photos) - set(condition)),
                "missing_vs_media_hashes": sorted(
                    digest(value) for value in set(photos) - set(file_values)),
            }
        finally:
            con.close()

    spool = get_remote("/home/Carix/.crm_media_spool.jsonl", missing=True, limit=10_000_000)
    spool_rows = []
    for line in (spool or b"").decode("utf-8", "replace").splitlines():
        try:
            row = json.loads(line)
            if row.get("card_id") == evidence["card"]["id"]:
                spool_rows.append(row)
        except Exception:
            continue
    evidence["spool"] = {
        "rows_for_card": len(spool_rows),
        "unique_file_ids": len({row.get("file_id") for row in spool_rows}),
        "targets": dict(sorted(collections.Counter(
            str(row.get("target") or "") for row in spool_rows).items())),
    }
    source = get_remote("/home/Carix/cars_ui.py", limit=3_000_000).decode("utf-8")
    evidence["runtime"] = {
        "cars_ui_sha256": digest(source),
        "fastpath_marker": "CRM-PHOTO-FASTPATH-001" in source,
        "drain_lock_marker": "_V165_DRAIN_LOCK" in source,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print("TASK065_UA0011_RECONCILIATION_PASS")


if __name__ == "__main__":
    main()
