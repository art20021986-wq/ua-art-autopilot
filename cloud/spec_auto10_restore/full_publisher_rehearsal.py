#!/usr/bin/env python3
"""Execute the trusted captured publisher closure in a new guarded rehearsal.

No production module is imported. Captured SHA-pinned bytes are token-relocated
from /home/Carix into an exclusive local directory before import. AST equality
proves the literal relocation scope. Optional explicitly named repair switches
apply the two separately pinned, reported pure patches.
The resulting evidence is an isolated synthetic-data rehearsal, never a live
site verification. Run with Python -I -B in a disposable process.
The Python audit guard covers audited Python I/O and process/network calls; it
is not a security sandbox for hostile native extensions or arbitrary code.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import sysconfig
import tokenize
import traceback
from urllib.parse import unquote, urlsplit

CURRENT_MODULES = ("stranica.py", "master_card.py", "catalog_design_guard.py", "db.py")
CANDIDATE_MODULES = ("publikaciya.py", "publish_transaction_guard.py", "ua_additional_spec.py",
                     "spec_publication.py", "card_shell.py", "vin_spec_service.py",
                     "source_policy.py", "profile_library.py", "card_lifecycle.py")
PRODUCTION_ROOT = "/home/Carix"


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def relocated(source: str, root: Path) -> tuple[str, list[dict]]:
    """Keep every original token except strings containing the reviewed root."""
    entries, changes = [], []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.STRING:
            try:
                value = ast.literal_eval(token.string)
            except (ValueError, SyntaxError):
                value = None
            if isinstance(value, str) and PRODUCTION_ROOT in value:
                changed = value.replace(PRODUCTION_ROOT, str(root))
                changes.append({"line": token.start[0], "literal_sha256": digest(value.encode()),
                                "occurrences": value.count(PRODUCTION_ROOT)})
                token = token._replace(string=repr(changed))
        entries.append(token)
    result = tokenize.untokenize(entries)

    class Relocate(ast.NodeTransformer):
        def visit_Constant(self, node):
            if isinstance(node.value, str):
                node.value = node.value.replace(PRODUCTION_ROOT, str(root))
            return node

    expected = Relocate().visit(ast.parse(source))
    if ast.dump(expected, include_attributes=False) != ast.dump(ast.parse(result), include_attributes=False):
        raise RuntimeError("RELOCATION_AST_SCOPE_MISMATCH")
    return result, changes


def make_guard(root: Path, library_roots: list[Path]):
    """Audit both reads and writes, sockets, processes, imports and SQLite."""
    roots = [p.resolve() for p in library_roots]
    counts = {"outside_read": 0, "outside_write": 0, "network": 0, "process": 0}

    def inside(path, parent):
        return path == parent or parent in path.parents

    def path_of(value, fd=None):
        if isinstance(value, int):
            if value in (0, 1, 2):
                return root
            value = os.readlink("/proc/self/fd/" + str(value))
        if value is None:
            return None
        path = Path(os.fsdecode(value))
        if not path.is_absolute() and fd not in (None, -1, -100):
            path = Path(os.readlink("/proc/self/fd/" + str(fd))) / path
        return path.absolute().resolve()

    def check(value, write=False, fd=None):
        path = path_of(value, fd)
        if path is None or inside(path, root):
            return
        if not write and any(inside(path, parent) for parent in roots):
            return
        key = "outside_write" if write else "outside_read"
        counts[key] += 1
        raise PermissionError("REHEARSAL_" + key.upper())

    def guard(event, args):
        if event.startswith("socket."):
            counts["network"] += 1
            raise PermissionError("REHEARSAL_NETWORK_FORBIDDEN")
        if event in {"subprocess.Popen", "os.system", "os.posix_spawn", "os.fork", "os.forkpty", "pty.spawn"}:
            counts["process"] += 1
            raise PermissionError("REHEARSAL_PROCESS_FORBIDDEN")
        if event == "open":
            value, mode, flags = args
            check(value, bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
        elif event in {"os.listdir", "os.scandir"}:
            check(args[0])
        elif event in {"os.remove", "os.rmdir"}:
            check(args[0], True, args[1] if len(args) > 1 else None)
        elif event == "os.mkdir":
            check(args[0], True, args[2] if len(args) > 2 else None)
        elif event in {"os.rename", "os.link"}:
            check(args[0], event == "os.rename", args[2] if len(args) > 2 else None)
            check(args[1], True, args[3] if len(args) > 3 else None)
        elif event == "os.symlink":
            raise PermissionError("REHEARSAL_SYMLINK_FORBIDDEN")
        elif event in {"os.chmod", "os.chown", "os.utime", "os.truncate"}:
            check(args[0], True)
        elif event == "os.chdir":
            check(args[0], True)
        elif event == "sqlite3.connect":
            # Python 3.10 can emit a bytes path for the SQLite audit event.
            # Decode through the filesystem codec before URI parsing; the
            # resolved path is still required to be inside this owned root.
            value = os.fsdecode(os.fspath(args[0]))
            if value == ":memory:":
                return
            if value.startswith("file:"):
                value = unquote(urlsplit(value).path)
            check(value, True)
        elif event in {"compile", "exec"}:
            filename = args[1] if event == "compile" else getattr(args[0], "co_filename", "")
            if filename and not str(filename).startswith("<"):
                check(filename)
    return guard, counts


def _manifest_entry(directory, name, manifest_path=None):
    manifest = json.loads((manifest_path or directory / "manifest.json").read_text())
    entry = manifest.get("files", manifest)[name]
    return entry.get("after_sha256", entry.get("sha256"))


def prepare(current, candidate, golden, output, master_shell_patch=False, public_contract_patch=False,
            current_manifest=None, candidate_manifest=None, golden_sha256=None):
    if output.is_symlink() or output.exists() or output.resolve() != output.absolute():
        raise RuntimeError("OUTPUT_MUST_BE_NEW_CANONICAL_DIRECTORY")
    captured = {}
    for directory, names, manifest in [(current, CURRENT_MODULES, current_manifest), (candidate, CANDIDATE_MODULES, candidate_manifest)]:
        for name in names:
            path = directory / name
            if path.is_symlink() or not path.is_file():
                raise RuntimeError("INPUT_MISSING_OR_SYMLINK:" + name)
            data = path.read_bytes()
            if digest(data) != _manifest_entry(directory, name, manifest):
                raise RuntimeError("INPUT_SHA_MISMATCH:" + name)
            captured[name] = data
    if golden.is_symlink() or not golden.is_file():
        raise RuntimeError("GOLDEN_MISSING_OR_SYMLINK")
    golden_bytes = golden.read_bytes()
    if golden_sha256 is not None and digest(golden_bytes) != golden_sha256:
        raise RuntimeError("GOLDEN_SHA_MISMATCH")
    output.mkdir(mode=0o700)
    root = output / "runtime"
    root.mkdir(mode=0o700)
    modules = {}
    for name, data in captured.items():
        candidate_source = data.decode("utf-8")
        if name == "master_card.py" and master_shell_patch:
            patcher = Path(__file__).with_name("repair_master_shell.py")
            namespace = {"__name__": "isolated_master_shell_patcher"}
            exec(compile(patcher.read_text(), str(patcher), "exec"), namespace)
            candidate_source = namespace["patch_master_shell"](candidate_source)
        if name == "ua_additional_spec.py" and public_contract_patch:
            patcher = Path(__file__).with_name("repair_public_contract.py")
            namespace = {"__name__": "isolated_public_contract_patcher"}
            exec(compile(patcher.read_text(), str(patcher), "exec"), namespace)
            candidate_source = namespace["patch_public_contract"](candidate_source)
        translated, changes = relocated(candidate_source, root)
        (root / name).write_text(translated)
        modules[name] = {"captured_sha256": digest(data), "staged_sha256": digest(translated.encode()),
                         "candidate_sha256_before_relocation": digest(candidate_source.encode()),
                         "reviewed_master_shell_patch": name == "master_card.py" and master_shell_patch,
                         "reviewed_public_contract_patch": name == "ua_additional_spec.py" and public_contract_patch,
                         "literal_relocations": changes}
    (root / "catalog_design_golden.html").write_bytes(golden_bytes)
    (root / "video").mkdir()
    (root / "site").mkdir()
    (root / "tmp").mkdir()
    (root / "bot_imya.txt").write_text("UA_artcompany_LLC_bot")
    (root / "video_sayt.txt").write_text("https://www.uaart.com.ua/video")
    return root, {"modules": modules, "golden_sha256": digest(golden_bytes)}


def seed_runtime(root):
    """Actual db.init_db/create_card allocator, with explicitly synthetic rows."""
    import db
    db.init_db()
    columns = {"auto_number": "TEXT", "make": "TEXT", "status": "TEXT", "engine_cc": "INTEGER",
               "mileage_km": "INTEGER", "price_uah": "INTEGER", "transmission": "TEXT",
               "drive": "TEXT", "cover_photo": "TEXT", "condition_text": "TEXT",
               "photos_json": "TEXT", "videos_json": "TEXT", "container": "TEXT",
               "departure_date": "TEXT", "arrival_date": "TEXT"}
    with db.connect() as con:
        present = {row[1] for row in con.execute("PRAGMA table_info(cars)")}
        for name, type_name in columns.items():
            if name not in present:
                con.execute("ALTER TABLE cars ADD COLUMN " + name + " " + type_name)
    ids = []
    for number in range(1, 3):
        identifier = "UA-%04d" % number
        card_id = db.create_card("cars", {"brand": "Hyundai", "model": "Sonata", "year": "2017",
                                "vin": "KMHE341CBHA00000" + str(number), "fuel": "LPG",
                                "color": "серебряный"}, 1)
        ids.append(card_id)
        with db.connect() as con:
            con.execute("UPDATE cars SET auto_number=?, make='Hyundai', status='sea_transit', "
                        "engine_cc=2000, mileage_km=100000, price_uah=15000, transmission='автомат', "
                        "drive='передний', published=1, photos_json='[]', videos_json='[]' WHERE id=?",
                        (identifier, card_id))
        photos = root / "video" / "foto" / identifier
        photos.mkdir(parents=True)
        # A synthetic image needs no remote/media content; >1KB is the actual
        # legacy gallery threshold. PIL recognizes its PPM magic when used.
        (photos / "001.jpg").write_bytes(b"P6\n64 48\n255\n" + bytes([80, 100, 120]) * (64 * 48))
    import vin_spec_service as service
    service.ensure_schema()
    for number in range(1, 3):
        code = "UA-%04d" % number
        with service.connect_spec(False) as con:
            con.execute("INSERT INTO additional_specification (car_uid,field_key,field_value,normalized_value,source,confidence) "
                        "VALUES (?,?,?,?,?,?)", (code, "length", "4855", "4855", "SYNTHETIC_REHEARSAL", 1.0))
            con.execute("INSERT INTO additional_specification_meta (car_uid,field_key,label_ru,category,unit,verification_status) "
                        "VALUES (?,?,?,?,?,?)", (code, "length", "Длина", "dimensions", "мм", "MANUAL_VERIFIED"))
    return ids


def scenario(root):
    ids = seed_runtime(root)
    import publikaciya as publisher
    import publish_transaction_guard as transaction
    import spec_publication as spec
    import catalog_design_guard as design
    result = {"synthetic_data": True, "production_imported": False, "checks": []}
    ok, message, proof = transaction.publish_batch(publisher._UA083_BASE_PUBLISH, ["UA-0001", "UA-0002"])
    result["publish"] = {"ok": ok, "message": message, "evidence": proof}
    if not ok:
        # Diagnostic generation deliberately does not publish or bypass a guard.
        # Keep the rejected candidate privately for comparing the real template.
        transaction._stage_diags(["UA-0001", "UA-0002"])
        generated, _, _ = publisher._UA_AUTO10_BASE_MASTER("UA-0001")
        (root / "rejected-primary.html").write_text(generated)
        import card_shell
        result["rejected_template"] = {
            "actual_assets": card_shell.validate_shell_assets(generated, generated),
            "expected_assets_sha256": spec.PINNED_SHELL_ASSETS_SHA256,
            "assets": [{"tag": tag, "sha256": digest(value.encode()), "bytes": len(value.encode())}
                       for tag, value in card_shell._shell_assets(generated)],
        }
        result["status"] = "FAIL"
        return result
    for folder in ("video", "site"):
        for code in ("UA-0001", "UA-0002"):
            path = root / folder / (code + ".html")
            audit = spec.validate_page(path.read_text(), code, spec.load_facts(code))
            result["checks"].append({"check": "primary_spec_and_single_vin", "path": str(path.relative_to(root)), "audit": audit})
        catalog = (root / folder / "katalog.html").read_text()
        result["checks"].append({"check": "catalog_shell", "folder": folder,
                                 "same": design.shell_fingerprint(catalog) == design.shell_fingerprint(design.GOLDEN_PATH.read_text())})
    def pages():
        return {str(p.relative_to(root)): p.read_bytes() for folder in ("video", "site")
                for p in (root / folder).glob("*.html")}

    def dynamic_tokens(source):
        source = re.sub(r"([?&]v=)[0-9]+", r"\1<generated-version>", source)
        return re.sub(r"обновлено [0-9]{2}\.[0-9]{2}\.[0-9]{4} [0-9]{2}:[0-9]{2}",
                      "обновлено <generated-time>", source)

    before = pages()
    ok, message = publisher.opublikovat("UA-0002")
    result["repeat"] = {"ok": ok, "message": message}
    after = pages()
    stable = set(before) == set(after) and all(dynamic_tokens(before[p].decode()) == dynamic_tokens(after[p].decode()) for p in before)
    result["repeat"]["byte_identical"] = before == after
    result["repeat"]["only_known_generation_timestamps_changed"] = stable
    result["repeat"]["generation_timestamp_fields"] = ["URL ?v= epoch", "обновлено date/time"]
    result["repeat"]["changed_paths"] = [p for p in before if before[p] != after[p]]
    for folder in ("video", "site"):
        source = (root / folder / "UA-0002.html").read_text()
        spec.validate_page(source, "UA-0002", spec.load_facts("UA-0002"))
    # Inject exactly one local disk error after primary/diagnostic writes and
    # the first catalog write. Everything else, including restore, is real.
    original_atomic = transaction._atomic
    failed = []
    import db
    with db.connect() as con:
        con.execute("UPDATE cars SET price_uah=16000 WHERE auto_number='UA-0002'")
    changed_at_failure = []

    def fail_second_catalog(path, data, mode=None):
        if Path(path) == root / "site" / "katalog.html" and not failed:
            failed.append(str(Path(path).relative_to(root)))
            changed_at_failure.extend(p for p, data_before in rollback_before.items()
                                      if (root / p).read_bytes() != data_before)
            raise OSError("SYNTHETIC_ONE_SHOT_SECOND_CATALOG_WRITE_FAILURE")
        return original_atomic(path, data, mode)

    transaction._atomic = fail_second_catalog
    rollback_before = pages()
    try:
        failed_ok, failed_message, failed_proof = transaction.publish_batch(publisher._UA083_BASE_PUBLISH, ["UA-0002"])
    finally:
        transaction._atomic = original_atomic
    rollback_after = pages()
    with db.connect() as con:
        con.execute("UPDATE cars SET price_uah=15000 WHERE auto_number='UA-0002'")
    rollback_pass = bool(not failed_ok and len(failed) == 1 and rollback_before == rollback_after
                         and len(changed_at_failure) >= 2 and failed_proof.get("rollback", {}).get("restored")
                         and not failed_proof.get("rollback_error"))
    result["fault_rollback"] = {"status": "PASS" if rollback_pass else "FAIL", "injected": failed,
                               "exact_all_html_restored": rollback_before == rollback_after,
                               "synthetic_change": "UA-0002 price_uah 15000 -> 16000 before publication; restored to 15000 after scenario",
                               "changed_html_at_failure": changed_at_failure,
                               "evidence": failed_proof}
    import ua_additional_spec as public_contract
    baseline = (root / "video" / "UA-0001.html").read_text()
    block = spec.render_block("UA-0001", spec.load_facts("UA-0001"))
    stage = public_contract._contract_marker_span(baseline, "STAGE")
    relocated_spec = baseline.replace(block, "")
    end_stage = public_contract._contract_marker_span(relocated_spec, "STAGE")[1]
    relocated_spec = relocated_spec[:end_stage] + block + relocated_spec[end_stage:]
    mutations = {
        "missing_spec": baseline.replace(block, ""),
        "duplicate_vin": baseline.replace("</body>", "<p>KMHE341CBHA000001</p></body>"),
        "wrong_single_vin": baseline.replace("KMHE341CBHA000001", "KMHE341CBHA000009"),
        "changed_fact": baseline.replace('data-spec-key="length"', 'data-spec-key="width"'),
        "missing_diagnostic_link": baseline.replace('href="UA-0001-diag.html"', 'href="#"'),
        "changed_primary_action": baseline.replace(">Задаток 500 $<", ">Другая кнопка<"),
        "extra_static_style": baseline.replace("</head>", "<style>.shell{display:none}</style></head>"),
        "spec_after_stage": relocated_spec,
    }
    checks = {name: public_contract.public_contract_errors(value, "UA-0001") for name, value in mutations.items()}
    clean_errors = public_contract.public_contract_errors(baseline, "UA-0001")
    negative_pass = not clean_errors and all(checks.values())
    result["public_contract_negative_controls"] = {"status": "PASS" if negative_pass else "FAIL",
                                                   "valid_page_errors": clean_errors, "rejections": checks}
    catalogs_pass = all(check.get("same") is True for check in result["checks"] if check["check"] == "catalog_shell")
    result["status"] = "PASS" if ok and stable and rollback_pass and negative_pass and catalogs_pass else "FAIL"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--golden", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--master-shell-patch", action="store_true")
    parser.add_argument("--public-contract-patch", action="store_true")
    parser.add_argument("--current-manifest", type=Path)
    parser.add_argument("--candidate-manifest", type=Path)
    parser.add_argument("--golden-sha256")
    args = parser.parse_args(argv)
    output = args.output.absolute()
    root, evidence = prepare(args.current.resolve(), args.candidate.resolve(), args.golden.resolve(), output,
                             args.master_shell_patch, args.public_contract_patch,
                             args.current_manifest.resolve() if args.current_manifest else None,
                             args.candidate_manifest.resolve() if args.candidate_manifest else None,
                             args.golden_sha256)
    report = {"scope": "ISOLATED_CAPTURED_FULL_PUBLISHER", "production_changed": False,
              "inputs": evidence, "status": "FAIL"}
    os.environ.clear()
    os.environ.update({"UA_ART_ROOT": str(root), "UA_ART_MAIN_DB": str(root / "crm.db"),
                       "UA_ART_SPEC_DB": str(root / "vin_specs_task111_v3.db"), "TMPDIR": str(root / "tmp")})
    os.chdir(root)
    library_roots = list({Path(sysconfig.get_path(key)).resolve() for key in ("stdlib", "platstdlib", "purelib", "platlib")})
    # Retain standard import locations and this staged module directory only.
    sys.path[:] = [str(root)] + [p for p in sys.path if p and any(Path(p).resolve() == lib or lib in Path(p).resolve().parents for lib in library_roots)]
    guard, counters = make_guard(output, library_roots)
    sys.addaudithook(guard)
    try:
        report.update(scenario(root))
    except BaseException as exc:
        report["error"] = type(exc).__name__ + ":" + str(exc)
        # Never reread a runner source outside the guarded output just to
        # pretty-print an error. Frame metadata is enough for localization.
        report["trace"] = [{"file": Path(frame.f_code.co_filename).name,
                            "line": line, "function": frame.f_code.co_name}
                           for frame, line in traceback.walk_tb(exc.__traceback__)]
    report["io_guard"] = counters
    if any(counters.values()):
        report["status"] = "FAIL"
    target = output / "result.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "report": str(target), "error": report.get("error"),
                      "io_guard": counters}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
