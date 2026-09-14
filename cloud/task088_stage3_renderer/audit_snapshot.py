"""Read-only FINAL v5 snapshot audit; JSON on stdout, no candidate installation.

Run with Python -B. Only the reviewed modules beside this script are imported;
live generator sources are read as bytes and compiled, never imported/executed.
This audit cannot authorize deployment: browser, homepage and complete generator
chain checks remain explicitly unperformed even when every local check passes.
"""

import sys

sys.dont_write_bytecode = True

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from initial_html_prices import migrate_card, migrate_catalog, migrate_home
from patch_catalog_design_guard import EXPECTED_SHA256 as CATALOG_SHA, patch_catalog_design_guard
from patch_stranica import EXPECTED_SHA256 as STRANICA_SHA, patch_stranica
from patch_yadro import EXPECTED_SHA256 as YADRO_SHA, patch_yadro
from uaart_market_prices import render_market_prices


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def read_inside(root, relative):
    path = root / relative
    # A source/HTML link escaping the supplied root is not part of this audit.
    try:
        path.resolve(strict=True).relative_to(root)
    except ValueError as error:
        raise ValueError("PATH_ESCAPES_SNAPSHOT_ROOT") from error
    return path.read_bytes()


def reason(error):
    # Never emit raw DB rows, SQL values, or captured source/HTML contents.
    if isinstance(error, ValueError) and re.fullmatch(r"[A-Z][A-Z0-9_:]+", str(error)):
        return str(error)
    return type(error).__name__


def html_manifest(root):
    """Hash root HTML and all production HTML below video/ and site/."""
    entries, scope = {}, []
    for directory, recursive in ((root, False), (root / "video", True), (root / "site", True)):
        label = "." if directory == root else directory.name
        if not directory.is_dir():
            scope.append({"path": label, "status": "FAIL", "reason": "HTML_DIRECTORY_MISSING"})
            continue
        try:
            paths = directory.rglob("*.html") if recursive else directory.glob("*.html")
            for path in sorted(paths):
                relative = path.relative_to(root).as_posix()
                try:
                    entries[relative] = {"status": "PASS", "sha256": digest(read_inside(root, relative))}
                except (OSError, ValueError) as error:
                    entries[relative] = {"status": "FAIL", "reason": reason(error)}
            scope.append({"path": label, "status": "PASS"})
        except OSError as error:
            scope.append({"path": label, "status": "FAIL", "reason": reason(error)})
    return entries, scope


def read_published(root):
    path = root / "crm.db"
    path.resolve(strict=True).relative_to(root)
    # mode=ro cannot create the database or commit changes to it. query_only and
    # the SQL authorizer are independent restrictions on this connection.
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        connection.execute("PRAGMA query_only=ON")
        if connection.execute("PRAGMA query_only").fetchone()[0] != 1:
            raise ValueError("DB_QUERY_ONLY_NOT_ACTIVE")
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
        connection.set_authorizer(lambda action, *args: sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)
        connection.row_factory = sqlite3.Row
        rows = [dict(row) for row in connection.execute(
            "SELECT id, auto_number, price_uah, price_georgia, status "
            "FROM cars WHERE published=1 ORDER BY id"
        )]
    finally:
        connection.close()
    if not rows:
        raise ValueError("PUBLISHED_SET_EMPTY")
    identifiers = [row["auto_number"] for row in rows]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("PUBLISHED_CAR_ID_DUPLICATE")
    for row in rows:
        render_market_prices(row, require_car_id=True)
    fingerprint = digest(json.dumps(rows, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())
    return rows, fingerprint


def compare_manifests(before, after):
    checks = []
    for path in sorted(set(before) | set(after)):
        first, last = before.get(path), after.get(path)
        if first is None or last is None:
            checks.append({"path": path, "status": "FAIL", "reason": "HTML_ADDED_OR_REMOVED_DURING_AUDIT"})
        elif first.get("status") != "PASS" or last.get("status") != "PASS":
            checks.append({"path": path, "status": "FAIL", "reason": first.get("reason") or last.get("reason")})
        elif first["sha256"] != last["sha256"]:
            checks.append({"path": path, "status": "FAIL", "reason": "HTML_DRIFT_DURING_AUDIT",
                           "before_sha256": first["sha256"], "after_sha256": last["sha256"]})
        else:
            checks.append({"path": path, "status": "PASS", "sha256": first["sha256"],
                           "same_before_after": True})
    return checks


def audit_snapshot(root):
    root = root.resolve(strict=True)
    report = {"audit": "UA-ART-GE-UA-MARKET-PRICE-001 FINAL v5.0 snapshot",
              "started_at": timestamp(), "root": str(root), "read_only": True,
              "published_count": None, "sources": [], "pages": []}
    before, scope_before = html_manifest(root)
    report["html_scope"] = scope_before
    rows = None
    try:
        rows, row_hash = read_published(root)
        report["published_count"] = len(rows)
        report["db"] = {"status": "PASS", "mode": "ro", "query_only": True,
                        "published_set_sha256": row_hash}
    except (OSError, ValueError, sqlite3.Error, TypeError) as error:
        report["db"] = {"status": "FAIL", "reason": reason(error)}

    for filename, expected, patcher in (
        ("yadro.py", YADRO_SHA, patch_yadro),
        ("stranica.py", STRANICA_SHA, patch_stranica),
        ("catalog_design_guard.py", CATALOG_SHA, patch_catalog_design_guard),
    ):
        check = {"path": filename, "expected_sha256": expected}
        try:
            raw = read_inside(root, filename)
            check["sha256"] = digest(raw)
            candidate, evidence = patcher(raw)
            check.update(status="PASS", candidate_sha256=digest(candidate),
                         candidate_compiles=evidence["candidate_compiles"])
        except (OSError, ValueError, SyntaxError) as error:
            check.update(status="FAIL", reason=reason(error))
        report["sources"].append(check)

    if rows is not None:
        for directory in ("video", "site"):
            targets = [(directory + "/" + row["auto_number"] + ".html", row, "CARD") for row in rows]
            targets.append((directory + "/katalog.html", None, "CATALOG"))
            targets.append((directory + "/index.html", None, "HOME"))
            for relative, row, surface in targets:
                check = {"path": relative}
                try:
                    raw = read_inside(root, relative)
                    current_hash = digest(raw)
                    check["sha256"] = current_hash
                    if before.get(relative, {}).get("sha256") != current_hash:
                        raise ValueError("HTML_DRIFT_BEFORE_CANDIDATE")
                    source = raw.decode("utf-8")
                    if surface == "CARD":
                        candidate, evidence = migrate_card(source, row)
                    elif surface == "CATALOG":
                        candidate, evidence = migrate_catalog(source, rows)
                    else:
                        candidate, evidence = migrate_home(source, rows)
                    if not evidence.get("outside_price_unchanged"):
                        raise ValueError("PROTECTED_HTML_CHANGED")
                    check.update(status="PASS", candidate_sha256=digest(candidate.encode("utf-8")),
                                 protected_bytes_unchanged=True,
                                 price_regions_changed=evidence["price_regions_changed"])
                    if surface == "HOME":
                        check.update(topology=evidence["topology"], no_car_price_surfaces=evidence["no_car_price_surfaces"],
                                     all_bytes_unchanged=evidence["all_bytes_unchanged"])
                except (OSError, ValueError, UnicodeError, AssertionError, TypeError) as error:
                    check.update(status="FAIL", reason=reason(error), protected_bytes_unchanged=None)
                report["pages"].append(check)
    else:
        report["pages"].append({"path": "video|site/published-cards-and-catalog",
                                "status": "NOT_RUN", "reason": "PUBLISHED_DB_SNAPSHOT_UNAVAILABLE"})

    # A second independent read-only connection detects price/set drift. It does
    # not claim a server-wide writer lock or eliminate subsequent changes.
    if rows is not None:
        try:
            final_rows, final_hash = read_published(root)
            if final_hash != row_hash:
                raise ValueError("PUBLISHED_DB_DRIFT_DURING_AUDIT")
            report["db"]["same_before_after"] = True
        except (OSError, ValueError, sqlite3.Error, TypeError) as error:
            report["db"].update(status="FAIL", reason=reason(error), same_before_after=False)
    for check in report["sources"]:
        try:
            final_hash = digest(read_inside(root, check["path"]))
            if final_hash != check.get("sha256"):
                check.update(status="FAIL", reason="SOURCE_DRIFT_DURING_AUDIT", after_sha256=final_hash)
            else:
                check["same_before_after"] = True
        except (OSError, ValueError) as error:
            check.update(status="FAIL", reason=reason(error))
    after, scope_after = html_manifest(root)
    report["html_manifest"] = compare_manifests(before, after)
    report["html_count"] = len(before)
    report["html_scope_after"] = scope_after
    checked = [report["db"]] + report["sources"] + report["pages"] + report["html_manifest"] + scope_before + scope_after
    report["snapshot_checks"] = "PASS" if all(check["status"] == "PASS" for check in checked) else "FAIL"
    report["preview_gate"] = {
        "status": "FAIL", "production_allowed": False,
        "unperformed_required_checks": [
            "CURRENT_HOMEPAGE_ROUTE_AND_PRICE_ONLY_MIGRATION",
            "ACTUAL_RU_UA_GE_LANGUAGE_SWITCHING",
            "DESKTOP_MOBILE_LAYOUT_AND_INTERACTION",
            "COMPLETE_CURRENT_GENERATOR_PUBLICATION_CHAIN",
            "FULL_CRM_PROTECTED_ROW_VERIFICATION",
            "SHARED_WRITER_EXCLUSION_AND_DEPLOYMENT_RECOVERY_BINDING",
        ],
    }
    report["finished_at"] = timestamp()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_snapshot(args.root)
    except Exception as error:
        report = {"audit": "UA-ART-GE-UA-MARKET-PRICE-001 FINAL v5.0 snapshot",
                  "read_only": True, "snapshot_checks": "FAIL", "reason": reason(error),
                  "preview_gate": {"status": "FAIL", "production_allowed": False}}
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    # Unperformed mandatory checks are never converted into a green exit code.
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
