#!/usr/bin/env python3
"""Create an isolated, reviewable Gate B input snapshot without live writes."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import zipfile
from pathlib import Path


sys_root = Path("/home/Carix")
sandbox = sys_root / "task116_gate_a_sandbox"
output = sandbox / "gate_b_inputs.zip"
manifest_path = sandbox / "gate_b_inputs_manifest.json"

db_sources = {
    "main_snapshot.db": sys_root / "crm.db",
    "spec_snapshot.db": sys_root / "vin_specs_task111_v3.db",
}
runtime_names = (
    "cars_ui.py",
    "vin_spec_service.py",
    "ua_additional_spec.py",
    "master_card.py",
    "stranica.py",
    "yadro.py",
    "client_ui.py",
    "publikaciya.py",
)
web_roots = (sys_root / "site", sys_root / "video")
web_suffixes = {".html", ".css", ".js", ".json", ".svg", ".ico", ".woff", ".woff2", ".ttf"}


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def sqlite_snapshot(source: Path, destination: Path) -> None:
    source_uri = "file:" + str(source) + "?mode=ro"
    source_db = sqlite3.connect(source_uri, uri=True)
    destination_db = sqlite3.connect(destination)
    try:
        source_db.backup(destination_db)
    finally:
        destination_db.close()
        source_db.close()


def main() -> None:
    sandbox.mkdir(parents=True, exist_ok=True)
    for destination in (output, manifest_path, *(sandbox / name for name in db_sources)):
        if destination.exists():
            raise SystemExit(f"refusing to overwrite {destination}")
    entries: list[dict[str, object]] = []
    snapshots: list[Path] = []
    for name, source in db_sources.items():
        destination = sandbox / name
        sqlite_snapshot(source, destination)
        snapshots.append(destination)

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        candidates = snapshots + [sys_root / name for name in runtime_names]
        for root in web_roots:
            for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
                dirs[:] = sorted(name for name in dirs if not (Path(current) / name).is_symlink())
                for name in sorted(files):
                    path = Path(current) / name
                    if path.is_symlink() or path.suffix.casefold() not in web_suffixes:
                        continue
                    candidates.append(path)

        seen: set[Path] = set()
        for path in candidates:
            if path in seen or not path.is_file() or path.is_symlink():
                continue
            seen.add(path)
            if path.parent == sandbox and path.name.endswith("_snapshot.db"):
                archive_name = "db/" + path.name
            else:
                archive_name = path.relative_to(sys_root).as_posix()
            archive.write(path, archive_name)
            entries.append({"path": archive_name, "size": path.stat().st_size, "sha256": digest(path)})

        manifest = {
            "schema": "task116.gate_b_snapshot/1.0",
            "production_mutated": False,
            "database_source_mode": "mode=ro plus sqlite backup API",
            "web_roots": [str(path) for path in web_roots],
            "entries": entries,
        }
        payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
        archive.writestr("snapshot_manifest.json", payload)
        manifest_path.write_bytes(payload)

    print(json.dumps({"status": "OK", "entries": len(entries), "zip_bytes": output.stat().st_size}, sort_keys=True))


if __name__ == "__main__":
    main()
