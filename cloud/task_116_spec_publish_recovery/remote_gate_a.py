#!/usr/bin/env python3
"""TASK116 remote Gate A inventory probe.

The probe is deliberately observation-only:

* it does not import the application or any TASK116 runtime module;
* it performs no network requests;
* it creates no files, logs, caches, locks, backups or evidence artifacts;
* SQLite is opened with ``mode=ro&immutable=1`` and a write-denying authorizer;
* Git is queried only through ``rev-parse`` with optional locks disabled;
* stdout contains exactly one JSON object, including for configuration errors.

A successful probe is input to Gate A review.  It can never issue Gate B PASS.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote


sys.dont_write_bytecode = True

SCHEMA_VERSION = "task116.remote_gate_a/1.0"
PROBE_NAME = "remote_gate_a"
DEFAULT_ROOT = "/home/Carix"
DEFAULT_UID = "UA-0017"
UID_RE = re.compile(r"^UA-\d{4,5}$")
VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")

CODE_NAMES = frozenset(
    {
        "cars_ui.py",
        "konteyner.py",
        "source_policy.py",
        "vin_spec_service.py",
        "ua_additional_spec.py",
        "publikaciya.py",
        "ua116_runtime_bridge.py",
    }
)
DB_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3"})
EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".venv",
        "venv",
        "node_modules",
    }
)
PRIMARY_GROUPS = (
    ("brand",),
    ("model",),
    ("year",),
    ("vin",),
    ("fuel",),
    ("engine_cc", "engine"),
    ("gearbox",),
    ("drive",),
    ("mileage_km", "mileage"),
    ("color",),
)
LEGACY_STATUS_CODES = (
    "kr_bought",
    "sea_loaded",
    "sea_transit",
    "ua_handed",
)
WRITE_ACTION_NAMES = (
    "SQLITE_INSERT",
    "SQLITE_UPDATE",
    "SQLITE_DELETE",
    "SQLITE_CREATE_INDEX",
    "SQLITE_CREATE_TABLE",
    "SQLITE_CREATE_TEMP_INDEX",
    "SQLITE_CREATE_TEMP_TABLE",
    "SQLITE_CREATE_TEMP_TRIGGER",
    "SQLITE_CREATE_TEMP_VIEW",
    "SQLITE_CREATE_TRIGGER",
    "SQLITE_CREATE_VIEW",
    "SQLITE_DROP_INDEX",
    "SQLITE_DROP_TABLE",
    "SQLITE_DROP_TEMP_INDEX",
    "SQLITE_DROP_TEMP_TABLE",
    "SQLITE_DROP_TEMP_TRIGGER",
    "SQLITE_DROP_TEMP_VIEW",
    "SQLITE_DROP_TRIGGER",
    "SQLITE_DROP_VIEW",
    "SQLITE_ALTER_TABLE",
    "SQLITE_REINDEX",
    "SQLITE_ANALYZE",
    "SQLITE_ATTACH",
    "SQLITE_DETACH",
)
WRITE_ACTIONS = frozenset(
    value
    for name in WRITE_ACTION_NAMES
    for value in (getattr(sqlite3, name, None),)
    if isinstance(value, int)
)


class ConfigError(ValueError):
    """Invalid probe invocation; rendered as JSON instead of stderr text."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def normalized_vin(value: str) -> str:
    result = re.sub(r"[\s-]+", "", str(value or "")).upper()
    if not VIN_RE.fullmatch(result):
        raise ConfigError("invalid --vin")
    return result


def parse_positive(value: str, option: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"invalid {option}") from exc
    if result < 1:
        raise ConfigError(f"invalid {option}")
    return result


def parse_args(argv: list[str]) -> dict[str, Any]:
    values: dict[str, Any] = {
        "root": DEFAULT_ROOT,
        "uid": DEFAULT_UID,
        "vin": None,
        "max_files": 50_000,
        "max_hash_bytes": 268_435_456,
    }
    options = {
        "--root": "root",
        "--uid": "uid",
        "--vin": "vin",
        "--max-files": "max_files",
        "--max-hash-bytes": "max_hash_bytes",
    }
    index = 0
    while index < len(argv):
        option = argv[index]
        if option == "--help":
            raise ConfigError(
                "required: --vin; options: --root --uid --max-files "
                "--max-hash-bytes"
            )
        if option not in options or index + 1 >= len(argv):
            raise ConfigError("unknown or incomplete option")
        values[options[option]] = argv[index + 1]
        index += 2

    root = Path(str(values["root"])).expanduser()
    if not root.is_absolute():
        raise ConfigError("--root must be absolute")
    uid = str(values["uid"] or "").strip().upper()
    if not UID_RE.fullmatch(uid):
        raise ConfigError("invalid --uid")
    if values["vin"] is None:
        raise ConfigError("--vin is required and must be the exact CRM VIN for --uid")
    return {
        "root": root,
        "uid": uid,
        "vin": normalized_vin(str(values["vin"])),
        "max_files": parse_positive(str(values["max_files"]), "--max-files"),
        "max_hash_bytes": parse_positive(
            str(values["max_hash_bytes"]), "--max-hash-bytes"
        ),
    }


def clean_error(exc: BaseException, vin: str = "") -> str:
    message = re.sub(r"\s+", " ", str(exc or "")).strip()
    if vin:
        message = message.replace(vin, "<VIN>")
    return (type(exc).__name__ + (":" + message if message else ""))[:300]


def sha256_file(path: Path, max_bytes: int) -> tuple[str | None, str]:
    size = path.stat(follow_symlinks=False).st_size
    if size > max_bytes:
        return None, "SKIPPED_SIZE_LIMIT"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest(), "COMPLETE"


def relative_name(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return "<outside-root>"


def fingerprint(root: Path, path: Path, max_bytes: int) -> dict[str, Any]:
    info = path.stat(follow_symlinks=False)
    digest, hash_status = sha256_file(path, max_bytes)
    return {
        "path": relative_name(root, path),
        "size": int(info.st_size),
        "mtime_utc": dt.datetime.fromtimestamp(
            info.st_mtime, tz=dt.timezone.utc
        ).isoformat().replace("+00:00", "Z"),
        "sha256": digest,
        "hash_status": hash_status,
    }


def scan_tree(root: Path, max_files: int) -> dict[str, Any]:
    code: list[Path] = []
    databases: list[Path] = []
    html: list[Path] = []
    symlinks: list[str] = []
    seen = 0
    truncated = False

    for current_text, dir_names, file_names in os.walk(
        root, topdown=True, followlinks=False
    ):
        current = Path(current_text)
        kept_dirs: list[str] = []
        for name in sorted(dir_names):
            candidate = current / name
            if name in EXCLUDED_DIRS:
                continue
            if candidate.is_symlink():
                symlinks.append(relative_name(root, candidate))
                continue
            kept_dirs.append(name)
        dir_names[:] = kept_dirs

        for name in sorted(file_names):
            seen += 1
            if seen > max_files:
                truncated = True
                break
            path = current / name
            if path.is_symlink():
                symlinks.append(relative_name(root, path))
                continue
            lowered = name.casefold()
            if name in CODE_NAMES:
                code.append(path)
            if path.suffix.casefold() in DB_SUFFIXES:
                databases.append(path)
            if lowered in {
                "index.html",
                "katalog.html",
                "ua-0017.html",
                "ua-0017-diag.html",
            } or re.fullmatch(r"ua-\d{4,5}(?:-diag)?\.html", lowered):
                html.append(path)
        if truncated:
            break
    code = sorted(set(code))
    databases = sorted(set(databases))
    html = sorted(set(html))
    candidate_lists_truncated = len(code) > 64 or len(databases) > 32 or len(html) > 512
    return {
        "files_seen": seen,
        "truncated": truncated,
        "candidate_lists_truncated": candidate_lists_truncated,
        "code_candidates_seen": len(code),
        "database_candidates_seen": len(databases),
        "html_candidates_seen": len(html),
        "code": code[:64],
        "databases": databases[:32],
        "html": html[:512],
        "symlinks_skipped": sorted(set(symlinks))[:128],
    }


def git_value(root: Path, arguments: Iterable[str]) -> tuple[str | None, str | None]:
    environment = dict(os.environ)
    environment.update(
        {
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_PAGER": "cat",
            "LC_ALL": "C",
        }
    )
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            check=False,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, clean_error(exc)
    if completed.returncode != 0:
        return None, "git_rev_parse_failed"
    return completed.stdout.strip(), None


def inspect_git(root: Path) -> dict[str, Any]:
    """Observe local metadata if present; GitHub evidence verifies the branch."""

    marker = root / ".git"
    if not marker.exists():
        return {
            "metadata_present": False,
            "repository_verified": False,
            "branch": None,
            "branch_verified": False,
            "commit": None,
            "commit_verified": False,
            "verification_source_required": "github_branch_commit_evidence",
            "reason": "production_root_git_metadata_not_required_or_missing",
        }
    inside, error = git_value(root, ("--is-inside-work-tree",))
    if error or inside != "true":
        return {
            "metadata_present": True,
            "repository_verified": False,
            "branch": None,
            "branch_verified": False,
            "commit": None,
            "commit_verified": False,
            "verification_source_required": "github_branch_commit_evidence",
            "reason": error or "not_a_work_tree",
        }
    branch, branch_error = git_value(root, ("--abbrev-ref", "HEAD"))
    commit, commit_error = git_value(root, ("HEAD",))
    commit = commit.lower() if commit else None
    reasons = [value for value in (branch_error, commit_error) if value]
    reasons.append("observation_only_verify_with_github")
    return {
        "metadata_present": True,
        "repository_verified": False,
        "branch": branch,
        "branch_verified": False,
        "commit": commit,
        "commit_verified": False,
        "verification_source_required": "github_branch_commit_evidence",
        "reason": ",".join(reasons),
    }


def sqlite_authorizer(
    action: int, _one: str | None, _two: str | None,
    _database: str | None, _trigger: str | None,
) -> int:
    if action in WRITE_ACTIONS:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def quoted_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def is_present(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [
        str(row[1])
        for row in connection.execute(
            "PRAGMA table_info(" + quoted_identifier(table) + ")"
        ).fetchall()
    ]


def inspect_cars_table(
    connection: sqlite3.Connection, uid: str, vin: str
) -> dict[str, Any]:
    columns = table_columns(connection, "cars")
    key = "auto_number" if "auto_number" in columns else "uid" if "uid" in columns else None
    result: dict[str, Any] = {
        "columns_present": sorted(
            set(columns)
            & {
                "id", "auto_number", "uid", "vin", "status", "published",
                "brand", "model", "year", "fuel", "engine_cc", "engine",
                "gearbox", "drive", "mileage_km", "mileage", "color",
            }
        ),
        "target_rows": 0,
        "target": [],
        "legacy_status_counts": {},
    }
    if key:
        selected = [
            name
            for name in (
                key, "vin", "status", "published", "brand", "model", "year",
                "fuel", "engine_cc", "engine", "gearbox", "drive",
                "mileage_km", "mileage", "color",
            )
            if name in columns
        ]
        query = (
            "SELECT " + ",".join(quoted_identifier(name) for name in selected)
            + " FROM cars WHERE UPPER(" + quoted_identifier(key) + ")=? LIMIT 3"
        )
        rows = connection.execute(query, (uid,)).fetchall()
        result["target_rows"] = len(rows)
        for row in rows:
            item = dict(zip(selected, row))
            normalized_row_vin = re.sub(
                r"[\s-]+", "", str(item.get("vin") or "")
            ).upper()
            primary_presence: dict[str, bool] = {}
            for group in PRIMARY_GROUPS:
                available = [name for name in group if name in columns]
                if available:
                    primary_presence["/".join(group)] = any(
                        is_present(item.get(name)) for name in available
                    )
            result["target"].append(
                {
                    "uid_matches": str(item.get(key) or "").strip().upper() == uid,
                    "vin_matches_expected": normalized_row_vin == vin,
                    "status": str(item.get("status")) if "status" in item else None,
                    "published": item.get("published"),
                    "primary_presence": primary_presence,
                }
            )
    if "status" in columns:
        placeholders = ",".join("?" for _ in LEGACY_STATUS_CODES)
        rows = connection.execute(
            "SELECT status,COUNT(*) FROM cars WHERE status IN ("
            + placeholders + ") GROUP BY status ORDER BY status",
            LEGACY_STATUS_CODES,
        ).fetchall()
        result["legacy_status_counts"] = {str(row[0]): int(row[1]) for row in rows}
    return result


def inspect_database(
    root: Path, path: Path, uid: str, vin: str, max_hash_bytes: int
) -> dict[str, Any]:
    item = fingerprint(root, path, max_hash_bytes)
    wal = Path(str(path) + "-wal")
    shm = Path(str(path) + "-shm")
    item.update(
        {
            "open_mode": "mode=ro&immutable=1",
            "wal_present": wal.is_file(),
            "wal_size": wal.stat().st_size if wal.is_file() else 0,
            "shm_present": shm.is_file(),
            "inspection_status": "UNKNOWN",
            "tables": [],
            "cars": None,
            "task116_table_counts": {},
        }
    )
    uri = "file:" + quote(str(path.resolve(strict=True)), safe="/") + "?mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=1.0)
        try:
            connection.row_factory = sqlite3.Row
            connection.set_authorizer(sqlite_authorizer)
            tables = [
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
            ]
            item["tables"] = tables
            if "cars" in tables:
                item["cars"] = inspect_cars_table(connection, uid, vin)
            for table in tables:
                if table.startswith("ua116_") or table == "vin_spec_jobs":
                    count = connection.execute(
                        "SELECT COUNT(*) FROM " + quoted_identifier(table)
                    ).fetchone()[0]
                    item["task116_table_counts"][table] = int(count)
            item["inspection_status"] = (
                "UNVERIFIED_WAL_PRESENT" if item["wal_present"] else "OBSERVED"
            )
        finally:
            connection.close()
    except Exception as exc:
        item["inspection_status"] = "ERROR"
        item["error"] = clean_error(exc, vin)
    return item


def inspect_code(
    root: Path, path: Path, max_hash_bytes: int
) -> dict[str, Any]:
    item = fingerprint(root, path, max_hash_bytes)
    if item["hash_status"] != "COMPLETE":
        item["inspection_status"] = "SKIPPED_SIZE_LIMIT"
        return item
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        item["task116_marker"] = "UA-ART-CRM-SPEC-PUBLISH-RECOVERY-001-V1.0" in source
        item["legacy_codes_mentioned"] = sorted(
            code for code in LEGACY_STATUS_CODES if code in source
        )
        item["production_path_mentioned"] = "/home/Carix" in source
    except Exception as exc:
        item["inspection_error"] = clean_error(exc)
    return item


def inspect_html(
    root: Path, path: Path, uid: str, vin: str, max_hash_bytes: int
) -> dict[str, Any]:
    item = fingerprint(root, path, max_hash_bytes)
    if item["hash_status"] != "COMPLETE":
        item["inspection_status"] = "SKIPPED_SIZE_LIMIT"
        return item
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        item.update(
            {
                "target_uid_tokens": len(
                    re.findall(r"(?<![A-Z0-9])" + re.escape(uid) + r"(?![A-Z0-9])", source, re.I)
                ),
                "target_vin_tokens": len(
                    re.findall(r"(?<![A-Z0-9])" + re.escape(vin) + r"(?![A-Z0-9])", source, re.I)
                ),
                "additional_spec_rows": len(
                    re.findall(r"\bua-addspec-row\b", source, re.I)
                ),
                "spec_digest_markers": len(
                    re.findall(r"\bdata-ua-spec-sha256\s*=", source, re.I)
                ),
                "generic_fallback_marker": "Открыть все автомобили" in source,
                "exact_catalog_links": len(
                    re.findall(
                        r"href\s*=\s*(['\"])(?:[^'\"]*/)?"
                        + re.escape(uid)
                        + r"\.html(?:[?#][^'\"]*)?\1",
                        source,
                        re.I,
                    )
                ),
            }
        )
    except Exception as exc:
        item["inspection_error"] = clean_error(exc, vin)
    return item


def check(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def run(values: dict[str, Any], started: str) -> tuple[dict[str, Any], int]:
    supplied_root: Path = values["root"]
    uid: str = values["uid"]
    vin: str = values["vin"]
    root_exists = supplied_root.is_dir()
    root = supplied_root.resolve(strict=False)
    if not root_exists:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "probe": PROBE_NAME,
            "mode": "read_only",
            "started_at_utc": started,
            "finished_at_utc": utc_now(),
            "target": {
                "root_supplied": str(supplied_root),
                "root_resolved": str(root),
                "uid": uid,
                "vin_sha256": hashlib.sha256(vin.encode()).hexdigest(),
            },
            "git": {
                "metadata_present": False,
                "repository_verified": False,
                "branch": None,
            "branch_verified": False,
            "commit": None,
            "commit_verified": False,
            "verification_source_required": "github_branch_commit_evidence",
            "reason": "root_missing",
            },
            "checks": [check("root_exists", "FAIL", "target root is missing")],
            "gate_a": {"status": "FAIL", "decision_scope": "read_only_inventory"},
            "gate_b": {"status": "NOT_RUN", "eligible": False},
            "production": {
                "mutated_by_probe": False,
                "write_attempts": 0,
                "service_reloads": 0,
            },
            "summary": {"fatal_error": "root_missing"},
        }
        return payload, 1

    inventory = scan_tree(root, values["max_files"])
    git = inspect_git(root)
    code = [
        inspect_code(root, path, values["max_hash_bytes"])
        for path in inventory["code"]
    ]
    html = [
        inspect_html(root, path, uid, vin, values["max_hash_bytes"])
        for path in inventory["html"]
    ]
    databases = [
        inspect_database(root, path, uid, vin, values["max_hash_bytes"])
        for path in inventory["databases"]
    ]

    target_db_rows = sum(
        int((database.get("cars") or {}).get("target_rows") or 0)
        for database in databases
    )
    target_vin_matches = sum(
        1
        for database in databases
        for target in ((database.get("cars") or {}).get("target") or [])
        if target.get("vin_matches_expected") is True
    )
    target_vin_mismatches = sum(
        1
        for database in databases
        for target in ((database.get("cars") or {}).get("target") or [])
        if target.get("vin_matches_expected") is False
    )
    target_card_files = [
        item for item in html if Path(str(item.get("path"))).name.casefold() == (uid + ".html").casefold()
    ]
    wal_databases = [item["path"] for item in databases if item.get("wal_present")]
    db_errors = [item["path"] for item in databases if item.get("inspection_status") == "ERROR"]

    checks: list[dict[str, str]] = [
        check("root_exists", "PASS", "target root resolved and was read only"),
        check(
            "scan_complete",
            "FAIL" if inventory["truncated"] or inventory["candidate_lists_truncated"] else "PASS",
            "files_seen=%d candidate_lists_truncated=%s"
            % (inventory["files_seen"], inventory["candidate_lists_truncated"]),
        ),
        check(
            "application_modules_observed",
            "PASS" if code else "UNKNOWN",
            f"matching_modules={len(code)}",
        ),
        check(
            "sqlite_candidates_observed",
            "PASS" if databases else "UNKNOWN",
            f"databases={len(databases)} errors={len(db_errors)}",
        ),
        check(
            "target_db_identity_observed",
            "UNKNOWN",
            "target_rows_observed=%d exact_vin_matches=%d vin_mismatches=%d"
            % (target_db_rows, target_vin_matches, target_vin_mismatches),
        ),
        check(
            "target_html_observed",
            "UNKNOWN",
            "filename candidates=%d; authoritative roots and visible DOM not yet bound"
            % len(target_card_files),
        ),
        check(
            "sqlite_wal_absent",
            "PASS" if not wal_databases else "UNKNOWN",
            "immutable read may not include uncheckpointed WAL" if wal_databases else "no WAL companions observed",
        ),
        check(
            "github_branch_commit_evidence",
            "UNKNOWN",
            "out of probe scope; verify the separate branch and commit in GitHub",
        ),
        check(
            "authoritative_remote_binding",
            "UNKNOWN",
            "operator must bind exact main DB, spec DB and both web roots before Gate A",
        ),
    ]
    required = {
        "root_exists",
        "scan_complete",
        "target_db_identity_observed",
        "target_html_observed",
        "sqlite_wal_absent",
    }
    required_statuses = [
        item["status"] for item in checks if item["name"] in required
    ]
    if "FAIL" in required_statuses or db_errors:
        gate_a_status = "FAIL"
        exit_code = 1
    else:
        gate_a_status = "UNKNOWN"
        # Inventory observations cannot authenticate which of several backup,
        # test and live-looking candidates are authoritative.  UNKNOWN is
        # intentionally non-zero so automation cannot treat it as a passed gate.
        exit_code = 1

    own_path = Path(__file__).resolve(strict=True)
    own_digest, own_hash_status = sha256_file(own_path, values["max_hash_bytes"])
    payload = {
        "schema_version": SCHEMA_VERSION,
        "probe": PROBE_NAME,
        "probe_source_sha256": own_digest,
        "probe_source_hash_status": own_hash_status,
        "mode": "read_only",
        "started_at_utc": started,
        "finished_at_utc": utc_now(),
        "target": {
            "root_supplied": str(supplied_root),
            "root_resolved": str(root),
            "uid": uid,
            "vin_sha256": hashlib.sha256(vin.encode()).hexdigest(),
        },
        "git": git,
        "checks": checks,
        "inventory": {
            "files_seen": inventory["files_seen"],
            "truncated": inventory["truncated"],
            "candidate_lists_truncated": inventory["candidate_lists_truncated"],
            "code_candidates_seen": inventory["code_candidates_seen"],
            "database_candidates_seen": inventory["database_candidates_seen"],
            "html_candidates_seen": inventory["html_candidates_seen"],
            "symlinks_skipped": inventory["symlinks_skipped"],
            "code": code,
            "html": html,
            "databases": databases,
        },
        "gate_a": {
            "status": gate_a_status,
            "decision_scope": "read_only_inventory",
            "note": "inventory cannot PASS Gate A until authoritative paths are externally bound",
        },
        "gate_b": {
            "status": "NOT_RUN",
            "eligible": False,
            "note": "this probe cannot issue Gate B PASS",
        },
        "production": {
            "mutated_by_probe": False,
            "write_attempts": 0,
            "service_reloads": 0,
            "network_requests": 0,
            "files_created": 0,
            "application_modules_imported": 0,
            "sqlite_mode": "mode=ro&immutable=1 plus write-denying authorizer",
        },
        "summary": {
            "code_files": len(code),
            "html_files": len(html),
            "database_files": len(databases),
            "database_errors": len(db_errors),
            "target_rows_observed": target_db_rows,
            "target_vin_matches": target_vin_matches,
            "target_vin_mismatches": target_vin_mismatches,
            "target_card_files": len(target_card_files),
            "wal_databases": wal_databases,
            "ua0017_release_state": "BLOCKED_PENDING_VERIFIED_GATE_B_AND_OWNER_COMMAND",
        },
    }
    return payload, exit_code


def error_payload(started: str, exc: BaseException, exit_code: int) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "probe": PROBE_NAME,
        "mode": "read_only",
        "started_at_utc": started,
        "finished_at_utc": utc_now(),
        "target": {},
        "git": {
            "metadata_present": False,
            "repository_verified": False,
            "branch": None,
            "branch_verified": False,
            "commit": None,
            "commit_verified": False,
            "verification_source_required": "github_branch_commit_evidence",
            "reason": "probe_error",
        },
        "checks": [],
        "gate_a": {"status": "FAIL", "decision_scope": "read_only_inventory"},
        "gate_b": {"status": "NOT_RUN", "eligible": False},
        "production": {
            "mutated_by_probe": False,
            "write_attempts": 0,
            "service_reloads": 0,
            "network_requests": 0,
            "files_created": 0,
            "application_modules_imported": 0,
        },
        "summary": {
            "fatal_error": clean_error(exc),
            "exit_code": exit_code,
        },
    }


def main() -> int:
    started = utc_now()
    try:
        values = parse_args(sys.argv[1:])
        payload, exit_code = run(values, started)
    except ConfigError as exc:
        exit_code = 3
        payload = error_payload(started, exc, exit_code)
    except Exception as exc:
        exit_code = 2
        payload = error_payload(started, exc, exit_code)
    sys.stdout.write(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
