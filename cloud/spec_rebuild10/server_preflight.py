"""Observe live input drift without changing CRM, HTML, locks or processes."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import zipfile

META_ARCHIVE_SHA256 = "4c28295d96bd8047f7872921f9ae4cf7302d0933534f6b516b03d4ae15365517"
PLAN_ARCHIVE_SHA256 = "b8cd862c72708009539ac6ec4bc33ea92d723ef9c0e190c04e3de8918af81d42"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_regular(path, limit=64_000_000):
    for parent in path.parents:
        if parent.is_symlink():
            raise ValueError("SYMLINK_PARENT")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as f:
        st = os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > limit:
            raise ValueError("UNSAFE_INPUT_FILE")
        raw = f.read(limit + 1)
        end = path.lstat()
        if (end.st_dev, end.st_ino, end.st_size, end.st_mtime_ns) != (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns):
            raise ValueError("INPUT_CHANGED_DURING_READ")
        if len(raw) != st.st_size:
            raise ValueError("SHORT_READ")
    return raw


def row_hash(rows):
    safe = [{k: ({"bytes_hex": v.hex()} if isinstance(v, bytes) else v)
             for k, v in row.items()} for row in rows]
    return digest(json.dumps(safe, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode())


def observe(root, stage):
    root, stage = Path(root).absolute(), Path(stage).absolute()
    meta = stage / "manual16-metadata-20260909-r9.zip"
    plan = stage / "manual16-candidate-20260909-r9.zip"
    if digest(read_regular(meta)) != META_ARCHIVE_SHA256 or digest(read_regular(plan)) != PLAN_ARCHIVE_SHA256:
        raise ValueError("STAGED_REFERENCE_CHANGED")
    with zipfile.ZipFile(meta) as z:
        snapshot = json.loads(z.read("snapshot_manifest.json"))
    with zipfile.ZipFile(plan) as z:
        reviewed = json.loads(z.read("private-plan.json"))
    def journals():
        found = []
        for name in ("crm.db", "vin_specs_task111_v3.db"):
            for suffix in ("-wal", "-shm", "-journal"):
                p = root / (name + suffix)
                if p.is_symlink():
                    raise ValueError("UNSAFE_DATABASE_SIDECAR")
                if p.exists():
                    found.append({"path": p.name, "bytes": p.stat().st_size})
        return found
    sidecars = journals()
    if any(x["bytes"] and not x["path"].endswith("-shm") for x in sidecars):
        raise ValueError("DATABASE_SNAPSHOT_NOT_STABLE")
    before = {}
    changed = []
    for entry in snapshot["records"]:
        rel = PurePosixPath(entry["path"])
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("UNSAFE_REFERENCE_PATH")
        before[str(rel)] = digest(read_regular(root / rel))
        if before[str(rel)] != entry["sha256"]:
            changed.append(str(rel))
    with contextlib.closing(sqlite3.connect((root / "crm.db").as_uri() + "?mode=ro", uri=True, timeout=2)) as c:
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA query_only=ON")
        c.execute("BEGIN")
        rows = [dict(r) for r in c.execute("SELECT * FROM cars ORDER BY auto_number")]
    row_sha = row_hash(rows)
    draft_rows = [{"uid": r["auto_number"], "published": r["published"]}
                  for r in rows if r["auto_number"] in {"UA-0017", "UA-0018"}]
    drift = [rel for rel, value in before.items() if digest(read_regular(root / rel)) != value]
    stable = not drift and sidecars == journals()
    return {"schema": "UA-ART-SPEC-REBUILD10-READONLY-PREFLIGHT-1",
            "observed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "status": "REFERENCE_MATCH" if stable and not changed and row_sha == reviewed["crm_all_rows_sha256"] else "INPUT_DRIFT_OR_INCONSISTENCY",
            "files_checked": len(before), "changed_since_reference": changed,
            "changed_during_observation": drift, "stable_observation": stable,
            "crm_all_rows_sha256": row_sha, "crm_rows_match_reference": row_sha == reviewed["crm_all_rows_sha256"],
            "crm_rows": len(rows), "published_cards": sum(bool(r["published"]) for r in rows),
            "protected_drafts": draft_rows, "free_bytes": shutil.disk_usage(root).free,
            "read_only": True, "production_changed": False,
            "global_atomic_snapshot": False, "external_writers_verified": False,
            "installation_authorized": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--stage", type=Path, required=True)
    args = parser.parse_args()
    print("REBUILD10_PREFLIGHT " + json.dumps(observe(args.root, args.stage), ensure_ascii=False))
