#!/usr/bin/env python3
"""Exact final-15 integration rehearsal; never an installer or live Gate B.

The frozen publisher-v2 harness remains unchanged. Its ordinary synthetic seed
is replaced only in its test namespace so creation uses actual final db and
recognition functions. Every production source is relocated into a new stage;
the inherited Python I/O guard forbids external reads/writes, sockets/processes.
This is an audited-code test harness, not a hostile-native-code security sandbox.
"""
from __future__ import annotations

import argparse
import ast
from datetime import date, datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import stat
import sys
import sysconfig
import traceback
import types

MANIFEST_SHA = "c4f75a818156e29426c9d601552ab0de56663e965233f2a56c01f5aaa111de07"
PUBLISHER_HARNESS_SHA = "8f8597a64c85f8b34ad36bc9855606b0bf8d45de5b3bcce9e5ea2b0d6bcd2f4f"
AI_FUNCTIONS = {"_norm", "flatten", "_pick", "_all_text", "_cc", "_km", "_year", "_map",
                "_log_parsed", "clean", "find_by_vin", "store", "_ua_auto10_card_number"}
AI_CONSTANTS = {"ALLOWED", "FUEL", "GEARBOX", "DRIVE", "COLOR", "SKIP", "FALLBACK"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_input(path):
    """Reject symlinks, non-regular files and a replaced/changed input inode."""
    if path.is_symlink() or path.resolve() != path.absolute():
        raise RuntimeError("INPUT_PATH_NOT_CANONICAL:" + path.name)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > 4 * 1024 * 1024:
            raise RuntimeError("INPUT_TYPE_OR_SIZE:" + path.name)
        with os.fdopen(os.dup(fd), "rb") as handle:
            data = handle.read()
        after = os.fstat(fd)
        linked = path.lstat()
        identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
        if identity(before) != identity(after) or identity(after) != identity(linked):
            raise RuntimeError("INPUT_CHANGED_DURING_READ:" + path.name)
        return data, {"sha256": digest(data), "identity": list(identity(after))}
    finally:
        os.close(fd)


def prepare(candidate, dependencies, golden, output):
    if output.exists() or output.is_symlink() or output.resolve() != output.absolute():
        raise RuntimeError("OUTPUT_MUST_BE_NEW_CANONICAL_DIRECTORY")
    manifest_bytes, manifest_receipt = read_input(candidate / "manifest.json")
    if digest(manifest_bytes) != MANIFEST_SHA:
        raise RuntimeError("FINAL15_MANIFEST_SHA_MISMATCH")
    manifest = json.loads(manifest_bytes)
    pins = {name: value["after_sha256"] for name, value in manifest["files"].items()}
    if len(pins) != 15 or set(p.name for p in candidate.iterdir()) != set(pins) | {"manifest.json"}:
        raise RuntimeError("FINAL15_EXACT_FILE_SET_REQUIRED")
    helper_path = Path(__file__).with_name("full_publisher_rehearsal.py")
    helper, helper_receipt = read_input(helper_path)
    if digest(helper) != PUBLISHER_HARNESS_SHA:
        raise RuntimeError("FROZEN_PUBLISHER_HARNESS_CHANGED")
    watched = {candidate / "manifest.json": manifest_receipt, helper_path: helper_receipt}
    captured = {}
    for name, expected in pins.items():
        path = candidate / name
        data, receipt = read_input(path)
        if digest(data) != expected:
            raise RuntimeError("FINAL15_MODULE_SHA_MISMATCH:" + name)
        captured[name] = data
        watched[path] = receipt
    for name, expected in manifest["execution_dependency_pins"].items():
        path = golden if name.endswith(".html") else dependencies / name
        data, receipt = read_input(path)
        if digest(data) != expected:
            raise RuntimeError("DEPENDENCY_SHA_MISMATCH:" + name)
        captured[name] = data
        watched[path] = receipt
    harness = types.ModuleType("frozen_publisher_rehearsal")
    harness.__file__ = str(helper_path)
    exec(compile(helper, str(helper_path), "exec"), harness.__dict__)
    output.mkdir(mode=0o700)
    root = output / "runtime"
    root.mkdir(mode=0o700)
    modules = {}
    for name, data in captured.items():
        if name.endswith(".py"):
            translated, relocations = harness.relocated(data.decode(), root)
            compile(translated, str(root / name), "exec")
            (root / name).write_text(translated)
            modules[name] = {"before_relocation_sha256": digest(data),
                             "staged_sha256": digest(translated.encode()),
                             "literal_relocations": relocations}
        else:
            (root / name).write_bytes(data)
    for name in ("video", "site", "tmp"):
        (root / name).mkdir()
    (root / "bot_imya.txt").write_text("UA_artcompany_LLC_bot")
    (root / "video_sayt.txt").write_text("https://www.uaart.com.ua/video")
    if any(read_input(path)[1] != receipt for path, receipt in watched.items()):
        raise RuntimeError("INPUT_CHANGED_DURING_PREPARATION")
    return root, harness, {"manifest_sha256": MANIFEST_SHA, "modules": modules,
                           "install_module_count": 15, "unchanged_dependencies": manifest["execution_dependency_pins"],
                           "inputs_unchanged_after_preparation": True}


def recognition(root):
    """Execute actual selected AST nodes; no fake Telegram module or AI output."""
    import db
    import cars_schema
    path = root / "ai_filter.py"
    tree = ast.parse(path.read_text())
    selected, functions, constants = [], set(), set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in AI_FUNCTIONS:
            selected.append(node)
            functions.add(node.name)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in AI_CONSTANTS:
                selected.append(node)
                constants.add(name)
    if functions != AI_FUNCTIONS or constants != AI_CONSTANTS:
        raise RuntimeError("RECOGNITION_AST_EXACT_SCOPE_REQUIRED")
    namespace = {"__name__": "reviewed_recognition_functions", "__file__": str(path), "db": db,
                 "S": cars_schema, "json": json, "re": re, "_re": re, "date": date,
                 "datetime": datetime, "log": logging.getLogger("synthetic-recognition")}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


def fixture_card(root, card_id, number, *, published):
    import db
    with db.connect() as connection:
        actual = connection.execute("SELECT auto_number FROM cars WHERE id=?", (card_id,)).fetchone()[0]
        if actual != number:
            raise RuntimeError("ACTUAL_ALLOCATED_NUMBER_MISMATCH")
        connection.execute("UPDATE cars SET make='Hyundai',status='sea_transit',engine_cc=2000,"
                           "mileage_km=100000,price_uah=15000,transmission='автомат',drive='передний',"
                           "published=?,photos_json='[]',videos_json='[]' WHERE id=?", (published, card_id))
    photos = root / "video" / "foto" / number
    photos.mkdir(parents=True)
    (photos / "001.jpg").write_bytes(b"P6\n64 48\n255\n" + bytes([80, 100, 120]) * (64 * 48))
    import vin_spec_service as service
    service.ensure_schema()
    with service.connect_spec(False) as connection:
        connection.execute("INSERT INTO additional_specification (car_uid,field_key,field_value,normalized_value,source,confidence) "
                           "VALUES (?,?,?,?,?,?)", (number, "length", "4855", "4855", "SYNTHETIC_REHEARSAL", 1.0))
        connection.execute("INSERT INTO additional_specification_meta (car_uid,field_key,label_ru,category,unit,verification_status) "
                           "VALUES (?,?,?,?,?,?)", (number, "length", "Длина", "dimensions", "мм", "MANUAL_VERIFIED"))


def seed_runtime(root):
    import db
    import cars_schema
    db.init_db()
    with db.connect() as connection:
        cars_schema.migrate(connection)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(cars)")}
        for name, kind in {"make": "TEXT", "transmission": "TEXT", "cover_photo": "TEXT", "photos_json": "TEXT",
                           "videos_json": "TEXT", "container": "TEXT", "departure_date": "TEXT", "arrival_date": "TEXT"}.items():
            if name not in columns:
                connection.execute("ALTER TABLE cars ADD COLUMN " + name + " " + kind)
    ai = recognition(root)
    first = db.create_card("cars", {"brand": "Hyundai", "model": "Sonata", "year": "2017", "vin": "KMHE341CBHA000001",
                                     "fuel": "LPG", "color": "серебряный"}, 1)
    parsed = {"brand": "Hyundai", "model": "Sonata", "year": "2017", "vin": "KMHE341CBHA000002",
              "fuel": "LPG", "color": "серебряный", "price_uah": 999999, "auto_number": "UA-0999"}
    data = ai["clean"](parsed)
    if "price_uah" in data or "auto_number" in data:
        raise RuntimeError("RECOGNITION_PROTECTED_FIELDS_LEAKED")
    second, number, created = ai["store"](data, 1)
    if (number, created) != ("UA-0002", True):
        raise RuntimeError("RECOGNITION_CREATE_FAILED")
    fixture_card(root, first, "UA-0001", published=1)
    fixture_card(root, second, "UA-0002", published=1)
    return [first, second]


def lifecycle_cycle(root):
    import db
    import card_lifecycle as lifecycle
    import publikaciya as publisher
    import spec_publication as spec
    import card_shell
    import catalog_design_guard as design
    import publish_transaction_guard as guard
    ai = recognition(root)
    report = {"status": "FAIL", "recognition_scope": "actual clean/store/find_by_vin/helper AST nodes; no Telegram callbacks or remote AI"}
    retired_checks = []
    def retired_absent(phase):
        present = [folder + "/" + name for folder in ("video", "site")
                   for name in ("UA-0002.html", "UA-0002-diag.html") if (root / folder / name).exists()]
        retired_checks.append({"phase": phase, "present": present})
        if present:
            raise RuntimeError("RETIRED_PAGES_RECREATED:" + phase + ":" + ",".join(present))
    with db.connect() as connection:
        row = dict(connection.execute("SELECT * FROM cars WHERE auto_number='UA-0002'").fetchone())
    card_id = row["id"]
    db.update_card_field("cars", card_id, "condition_text", "Ручное описание сохранено", 1)
    db.update_card_field("cars", card_id, "mileage_km", 101234, 1)
    recognized = ai["clean"]({"vin": row["vin"], "model": "WRONG_RECOGNIZED_MODEL", "mileage_km": 999999,
                               "condition_text": "Нельзя заменить ручное описание", "gearbox": "automatic"})
    same_id, same_number, created = ai["store"](recognized, 1)
    preserved = db.get_card("cars", card_id)
    manual_pass = (same_id == card_id and same_number == "UA-0002" and created is False
                   and preserved["condition_text"] == "Ручное описание сохранено" and preserved["model"] == "Sonata"
                   and preserved["mileage_km"] == 101234 and preserved["gearbox"] == "автомат")
    if not manual_pass:
        raise RuntimeError("EXISTING_RECOGNITION_MANUAL_FIELDS_NOT_PRESERVED")
    facts_before_edit = spec.load_facts("UA-0002")
    ok, message = publisher.opublikovat("UA-0002")
    if not ok:
        raise RuntimeError("EDIT_PUBLICATION_FAILED:" + message)
    edited = []
    for folder in ("video", "site"):
        page = (root / folder / "UA-0002.html").read_text()
        spec.validate_page(page, "UA-0002", spec.load_facts("UA-0002"))
        if "Ручное описание сохранено" not in page or not re.search(
                r"<tr><td\b[^>]*>Пробег</td><td\b[^>]*>101[ \u00a0\u202f]234 км</td></tr>", page):
            raise RuntimeError("EDITED_FIELDS_MISSING_FROM_PAGE")
        edited.append(folder + "/UA-0002.html")
    if spec.load_facts("UA-0002") != facts_before_edit:
        raise RuntimeError("MANUAL_SPEC_CHANGED_DURING_EDIT")
    media_path = root / "video/foto/UA-0002/001.jpg"
    media_sha = digest(media_path.read_bytes())
    deleted_ok, deleted_message = lifecycle.delete_card(card_id, 1)
    if not deleted_ok:
        raise RuntimeError("ACTUAL_LIFECYCLE_DELETE_FAILED:" + deleted_message)
    with db.connect() as connection:
        archive = [dict(value) for value in connection.execute(
            "SELECT auto_number,action,state FROM ua_spec_lifecycle_archive WHERE auto_number='UA-0002'")]
        sequence = connection.execute("SELECT high_water FROM ua_card_number_sequence WHERE prefix='UA-'").fetchone()[0]
    if db.get_card("cars", card_id) is not None or sequence != 2:
        raise RuntimeError("DELETE_IDENTITY_OR_SEQUENCE_FAILED")
    for folder in ("video", "site"):
        if any((root / folder / name).exists() for name in ("UA-0002.html", "UA-0002-diag.html")):
            raise RuntimeError("DELETE_PAGES_REMAIN")
        if "UA-0002" in guard._href_counts((root / folder / "katalog.html").read_text()):
            raise RuntimeError("DELETE_CATALOG_REFERENCE_REMAINS")
    if digest(media_path.read_bytes()) != media_sha:
        raise RuntimeError("DELETE_MEDIA_CHANGED")
    # Query saved specification directly: the public facts loader must refuse a
    # deleted identity rather than make retired facts available for a new car.
    import vin_spec_service as service
    with service.connect_spec(False) as connection:
        saved = connection.execute("SELECT field_value FROM additional_specification WHERE car_uid='UA-0002' AND field_key='length'").fetchone()
    if not saved or saved[0] != "4855" or not any(item["state"] == "COMPLETED" for item in archive):
        raise RuntimeError("DELETE_ARCHIVE_OR_SPEC_LOSS")
    def retired_write_audit(event, arguments):
        path = None
        if event == "open" and isinstance(arguments[0], (str, bytes, os.PathLike)):
            if arguments[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                path = Path(os.fsdecode(arguments[0]))
        elif event in {"os.rename", "os.link"}:
            path = Path(os.fsdecode(arguments[1]))
        if path and path.name in {"UA-0002.html", "UA-0002-diag.html"} and path.parent in {root / "video", root / "site"}:
            trace = [{"file": Path(frame.f_code.co_filename).name, "line": line, "function": frame.f_code.co_name}
                     for frame, line in traceback.walk_stack(None)]
            with (root / "retired-write-audit.jsonl").open("a") as handle:
                handle.write(json.dumps({"event": event, "path": str(path), "trace": trace}) + "\n")
    sys.addaudithook(retired_write_audit)
    try:
        stale_ok, stale_message = publisher.opublikovat("UA-0002")
    except spec.SpecError as exc:
        if str(exc) != "LIFECYCLE_CARD_MISSING_OR_DUPLICATE_UID":
            raise
        stale_ok, stale_message = False, str(exc)
    if stale_ok:
        raise RuntimeError("RETIRED_CARD_REPUBLISHED")
    retired_absent("after_stale_publication_rejection")
    data = ai["clean"]({"brand": "Hyundai", "model": "Sonata", "year": "2017", "vin": "KMHE341CBHA000003", "fuel": "LPG", "color": "серебряный"})
    third_id, third_number, created = ai["store"](data, 1)
    if third_number != "UA-0003" or not created:
        raise RuntimeError("RETIRED_NUMBER_REUSED")
    fixture_card(root, third_id, third_number, published=0)
    published_ok, published_message = lifecycle.set_visibility(third_id, True, 1)
    if not published_ok:
        raise RuntimeError("NEW_LIFECYCLE_PUBLICATION_FAILED:" + published_message)
    retired_absent("after_next_card_publication")
    checks = []
    for folder in ("video", "site"):
        for number in ("UA-0001", "UA-0003"):
            page = (root / folder / (number + ".html")).read_text()
            audit = spec.validate_page(page, number, spec.load_facts(number))
            assets = card_shell.validate_shell_assets(page, page)
            if assets["ordered_static_assets_sha256"] != spec.PINNED_SHELL_ASSETS_SHA256:
                raise RuntimeError("FINAL_SHELL_CHANGED")
            checks.append({"path": folder + "/" + number + ".html", "audit": audit})
        catalog = (root / folder / "katalog.html").read_text()
        if design.shell_fingerprint(catalog) != design.shell_fingerprint(design.GOLDEN_PATH.read_text()):
            raise RuntimeError("FINAL_CATALOG_SHELL_CHANGED")
        if set(guard._href_counts(catalog)) != {"UA-0001", "UA-0003"}:
            raise RuntimeError("FINAL_CATALOG_IDENTITIES_CHANGED")
    before = {str(path.relative_to(root)): path.read_text() for folder in ("video", "site") for path in (root / folder).glob("*.html")}
    repeat_ok, repeat_message = publisher.opublikovat("UA-0003")
    retired_absent("after_next_card_repeat")
    after = {str(path.relative_to(root)): path.read_text() for folder in ("video", "site") for path in (root / folder).glob("*.html")}
    def stable(source):
        source = re.sub(r"([?&]v=)[0-9]+", r"\1<generated-version>", source)
        return re.sub(r"обновлено [0-9]{2}\.[0-9]{2}\.[0-9]{4} [0-9]{2}:[0-9]{2}", "обновлено <generated-time>", source)
    if not repeat_ok or set(before) != set(after) or any(stable(before[name]) != stable(after[name]) for name in before):
        raise RuntimeError("FINAL_REPEAT_UNEXPECTED_MUTATION")
    # Repeat the non-vacuous disk-failure/rollback check after a completed
    # deletion, so rollback cannot silently resurrect a retired direct URL.
    rollback_before = {name: (root / name).read_bytes() for name in after}
    original_atomic = guard._atomic
    injected, changed = [], []
    db.update_card_field("cars", third_id, "price_uah", 16000, 1)
    def fail_catalog(path, data, mode=None):
        if Path(path) == root / "site/katalog.html" and not injected:
            injected.append("site/katalog.html")
            changed.extend(name for name, value in rollback_before.items() if (root / name).read_bytes() != value)
            raise OSError("SYNTHETIC_FINAL15_AFTER_DELETE_CATALOG_FAILURE")
        return original_atomic(path, data, mode)
    guard._atomic = fail_catalog
    try:
        failed_ok, failed_message, failed_proof = guard.publish_batch(publisher._UA083_BASE_PUBLISH, [third_number])
    finally:
        guard._atomic = original_atomic
    rollback_after = {str(path.relative_to(root)): path.read_bytes() for folder in ("video", "site")
                      for path in (root / folder).glob("*.html")}
    db.update_card_field("cars", third_id, "price_uah", 15000, 1)
    retired_absent("after_next_card_fault_rollback")
    if failed_ok or injected != ["site/katalog.html"] or len(changed) < 2 or rollback_before != rollback_after:
        raise RuntimeError("AFTER_DELETE_NONVACUOUS_ROLLBACK_FAILED")
    if not failed_proof.get("rollback", {}).get("restored") or failed_proof.get("rollback_error"):
        raise RuntimeError("AFTER_DELETE_ROLLBACK_RECEIPT_FAILED")
    report.update({"status": "PASS", "actual_creation_routes": ["db.create_card", "ai_filter.clean/store"],
                   "manual_fields_preserved_on_recognition": manual_pass, "edited_pages_validated": edited,
                   "delete": {"ok": deleted_ok, "archive": archive, "media_preserved": True, "spec_preserved": True,
                              "sequence_after_delete": sequence, "retired_publication_rejected": not stale_ok},
                   "next_created_uid": third_number, "next_publication_ok": published_ok,
                   "next_repeat_ok": repeat_ok, "retired_page_absence_checks": retired_checks,
                   "after_delete_fault_rollback": {"status": "PASS", "changed_at_failure": changed,
                                                    "exact_html_restored": True, "evidence": failed_proof},
                   "final_primary_checks": checks, "final_catalog_uids": ["UA-0001", "UA-0003"]})
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--dependencies", type=Path, required=True)
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.absolute()
    root, harness, inputs = prepare(args.candidate.absolute(), args.dependencies.absolute(), args.golden.absolute(), output)
    report = {"scope": "ISOLATED_FINAL15_COMBINED_SYNTHETIC_CYCLE", "status": "FAIL", "inputs": inputs,
              "production_changed": False, "overall_gate_b": "NOT_EVALUATED", "python_version": sys.version,
              "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "limitations": ["Synthetic cards only; no UA-0017/UA-0018 publication.",
                              "No Telegram callbacks, live worker, external source requests, service restart or production installation.",
                              "All fifteen modules staged and compiled; cars_ui is not imported; ai_filter uses listed actual AST functions."]}
    os.environ.clear()
    os.environ.update({"UA_ART_ROOT": str(root), "UA_ART_MAIN_DB": str(root / "crm.db"),
                       "UA_ART_SPEC_DB": str(root / "vin_specs_task111_v3.db"), "TMPDIR": str(root / "tmp")})
    os.chdir(root)
    libraries = list({Path(sysconfig.get_path(key)).resolve() for key in ("stdlib", "platstdlib", "purelib", "platlib")})
    sys.path[:] = [str(root)] + [entry for entry in sys.path if entry and any(Path(entry).resolve() == lib or lib in Path(entry).resolve().parents for lib in libraries)]
    io_guard, counters = harness.make_guard(output, libraries)
    sys.addaudithook(io_guard)
    try:
        harness.seed_runtime = seed_runtime  # test fixture only; no candidate function patched
        report["publisher"] = harness.scenario(root)
        if report["publisher"]["status"] != "PASS":
            raise RuntimeError("FROZEN_PUBLISHER_SCENARIO_FAILED")
        report["lifecycle"] = lifecycle_cycle(root)
        report["status"] = "PASS"
    except BaseException as exc:
        report["error"] = type(exc).__name__ + ":" + str(exc)
        report["trace"] = [{"file": Path(frame.f_code.co_filename).name, "line": line, "function": frame.f_code.co_name}
                           for frame, line in traceback.walk_tb(exc.__traceback__)]
    report["io_guard"] = counters
    if any(counters.values()):
        report["status"] = "FAIL"
    report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    target = output / "result.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "result": str(target), "error": report.get("error"), "io_guard": counters}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
