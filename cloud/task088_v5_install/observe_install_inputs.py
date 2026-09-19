"""Read-only hash/count observation; never copies sources, prices or credentials.

Run alongside the reviewed install_package.py with its exact hash. Account quota
is an independent authenticated observation supplied as a file, never guessed.
Only stdout is written; the caller may save it in private staging.
"""
from datetime import datetime, timezone
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3


def observe(engine, quota=None, *, test_root=None):
    root = Path(test_root) if test_root else Path("/home/Carix")
    if test_root and root == Path("/home/Carix"):
        raise ValueError("TEST_ROOT_CANNOT_BE_PRODUCTION")
    observed = datetime.now(timezone.utc)
    if quota is not None:
        engine._fresh(quota.get("observed_at"), observed.timestamp())
        if (quota.get("source") != "PYTHONANYWHERE_AUTHENTICATED_ACCOUNT" or quota.get("account") != "Carix"
                or type(quota.get("used_bytes")) is not int or type(quota.get("limit_bytes")) is not int
                or not 0 <= quota["used_bytes"] < quota["limit_bytes"]):
            raise ValueError("AUTHENTICATED_ACCOUNT_QUOTA_REQUIRED")
    sources = {name: engine.sha(engine._read(engine._path(root, name))) for name in sorted(engine.SOURCES)}
    dependencies = {name: engine.sha(engine._read(engine._path(root, name))) for name in sorted(engine.DEPENDENCIES)}
    inventory = engine.system_inventory(root)
    db_path = engine._path(root, "crm.db")
    conn = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True, timeout=10)
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        database = engine.database_snapshot(conn)
        schema = engine.sha(engine.encoded(conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()))
        statuses = conn.execute("SELECT status FROM cars WHERE published=1 ORDER BY id").fetchall()
    finally:
        conn.close()
    counts = {"korea": 0, "sea": 0, "georgia": 0, "kiev": 0}
    for (status,) in statuses:
        value = str(status or "").lower()
        key = ("korea" if value.startswith("kr_") else "sea" if value.startswith(("sea_", "sold_transit"))
               else "georgia" if value.startswith("ge_") else "kiev" if value.startswith("ua_") or value in ("sold", "archive") else None)
        if key is None:
            raise ValueError("UNRECOGNIZED_PUBLIC_STAGE")
        counts[key] += 1
    independent = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True, timeout=10)
    try:
        independent.execute("PRAGMA query_only=ON")
        if (engine.database_snapshot(independent) != database or
                engine.sha(engine.encoded(independent.execute(
                    "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall())) != schema):
            raise ValueError("INDEPENDENT_DB_OBSERVATION_DRIFT")
    finally:
        independent.close()
    if (engine.system_inventory(root) != inventory or
            any(engine.sha(engine._read(engine._path(root, name))) != value for name, value in dependencies.items())):
        raise ValueError("SYSTEM_DRIFT_DURING_OBSERVATION")
    return {"contract": "TASK088-V5-INSTALL-OBSERVATION-1", "status": "PASS" if quota else "OBSERVED_QUOTA_PENDING", "read_only": True,
        "environment": "TEST" if test_root else "PRODUCTION_READ_ONLY", "observed_at": observed.isoformat(),
        "source_sha256": sources, "dependency_sha256": dependencies, "system_inventory": inventory,
        "database": database, "schema_sha256": schema, "stage_counts": counts, "quota_evidence": quota,
        "full_backup_source_bytes": sum(entry["bytes"] for entry in inventory.values()),
        "live_files_written": False, "crm_written": False, "bot_restarted": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", required=True)
    parser.add_argument("--engine-sha256", required=True)
    parser.add_argument("--quota-json")
    args = parser.parse_args()
    path = Path(args.engine)
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != args.engine_sha256:
        raise ValueError("EXACT_REVIEWED_ENGINE_REQUIRED")
    spec = importlib.util.spec_from_file_location("task088_reviewed_install_engine", path)
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    report = observe(engine, json.loads(Path(args.quota_json).read_bytes()) if args.quota_json else None)
    print(json.dumps(report, ensure_ascii=True, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
