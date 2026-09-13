#!/usr/bin/env python3
"""Guarded combined17 synthetic rehearsal, never a production installation.

Reuses both frozen, previously executed cycle helpers without editing them.
Only captured source literals are relocated; candidate functions are unchanged.
The two external writers are exercised against the same publication lock inode.
This proves cooperating code behavior, not that legacy production processes
have drained or that a cross-host platform fence has been established.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import sysconfig
import traceback
import types

MANIFEST_SHA = "12afce821b784771a2a8a0415cc289f5e713d53aabedf0ed3e2747a8c4d4e136"
FROZEN_HELPERS = {
    "complete15_cycle.py": "d6449d1c53a65d02371d00bab78cb3cf5fe7231d644964f312ce915dd1bf851d",
    "full_publisher_rehearsal.py": "8f8597a64c85f8b34ad36bc9855606b0bf8d45de5b3bcce9e5ea2b0d6bcd2f4f",
}
TASK083 = "autopilot_inbox/cloud/task_083_catalog_dedup/installer.py"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def prepare(candidate, dependencies, golden, output):
    if output.exists() or output.is_symlink() or output.resolve() != output.absolute():
        raise RuntimeError("OUTPUT_MUST_BE_NEW_CANONICAL_DIRECTORY")
    helpers = {}
    for name, expected in FROZEN_HELPERS.items():
        path = Path(__file__).with_name(name)
        if path.is_symlink() or path.resolve() != path.absolute():
            raise RuntimeError("FROZEN_HELPER_PATH_INVALID")
        data = path.read_bytes()
        if sha(data) != expected:
            raise RuntimeError("FROZEN_HELPER_CHANGED:" + name)
        module = types.ModuleType(name[:-3] + "_frozen")
        module.__file__ = str(path)
        exec(compile(data, str(path), "exec"), module.__dict__)
        helpers[name] = module
    old = helpers["complete15_cycle.py"]
    harness = helpers["full_publisher_rehearsal.py"]
    raw, receipt = old.read_input(candidate / "manifest.json")
    if sha(raw) != MANIFEST_SHA:
        raise RuntimeError("FINAL17_MANIFEST_MISMATCH")
    manifest = json.loads(raw)
    pins = {name: entry["after_sha256"] for name, entry in manifest["files"].items()}
    disk = {str(path.relative_to(candidate)) for path in candidate.rglob("*") if not path.is_dir()}
    if len(pins) != 17 or disk != set(pins) | {"manifest.json"}:
        raise RuntimeError("FINAL17_EXACT_FILE_SET_REQUIRED")
    watched = {candidate / "manifest.json": receipt}
    captured = {}
    for name, expected in pins.items():
        data, receipt = old.read_input(candidate / name)
        if sha(data) != expected:
            raise RuntimeError("FINAL17_MODULE_CHANGED:" + name)
        captured[name] = data
        watched[candidate / name] = receipt
    for name, expected in manifest["execution_dependency_pins"].items():
        path = golden if name.endswith(".html") else dependencies / name
        data, receipt = old.read_input(path)
        if sha(data) != expected:
            raise RuntimeError("EXECUTION_DEPENDENCY_CHANGED:" + name)
        captured[name] = data
        watched[path] = receipt
    output.mkdir(mode=0o700)
    root = output / "runtime"
    root.mkdir(mode=0o700)
    modules = {}
    for name, data in captured.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name.endswith(".py"):
            translated, relocations = harness.relocated(data.decode(), root)
            compile(translated, str(target), "exec")
            target.write_text(translated)
            modules[name] = {"before_relocation_sha256": sha(data),
                             "staged_sha256": sha(translated.encode()), "literal_relocations": relocations}
        else:
            target.write_bytes(data)
    for name in ("video", "site", "tmp"):
        (root / name).mkdir()
    (root / "bot_imya.txt").write_text("UA_artcompany_LLC_bot")
    (root / "video_sayt.txt").write_text("https://www.uaart.com.ua/video")
    if any(old.read_input(path)[1] != before for path, before in watched.items()):
        raise RuntimeError("INPUT_CHANGED_DURING_PREPARATION")
    return root, old, harness, {"manifest_sha256": MANIFEST_SHA, "modules": modules,
                              "install_module_count": 17, "frozen_helpers": FROZEN_HELPERS,
                              "unchanged_dependencies": manifest["execution_dependency_pins"],
                              "inputs_unchanged_after_preparation": True}


def load_relocated(path, name):
    loader = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


def html_snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes()
            for folder in ("video", "site") for path in (root / folder).glob("*.html")}


def verify_kernel_lock_held(path):
    descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        raise RuntimeError("EXPECTED_SHARED_KERNEL_LOCK_NOT_HELD")
    finally:
        os.close(descriptor)


def writers_cycle(root):
    import publish_transaction_guard as publisher_guard
    import spec_publication as specification
    import card_shell
    import catalog_design_guard as design
    analytics = load_relocated(root / "analitika_wsgi.py", "isolated_analytics_writer")
    task = load_relocated(root / TASK083, "isolated_task083_writer")
    for name in (".task082_catalog_stage_repair.lock", ".task082_catalog_stage_guard.lock", ".task083_catalog_dedup.lock"):
        (root / name).touch(exist_ok=False)
    lock = root / ".ua_art_publish_transaction.lock"
    lock_identity = [lock.stat().st_dev, lock.stat().st_ino]
    protected_data = {name: sha((root / name).read_bytes()) for name in ("crm.db", "vin_specs_task111_v3.db")}
    protected_media = {str(path.relative_to(root)): sha(path.read_bytes())
                       for path in (root / "video" / "foto").rglob("*") if path.is_file()}
    canonical = html_snapshot(root)
    probe = root / "video" / "analytics-probe.html"
    probe_before = b"<html><head><style>body{color:black}</style></head><body>synthetic optional maintenance probe</body></html>"
    probe.write_bytes(probe_before)
    blocked_entries = []
    with publisher_guard._exclusive_lock():
        verify_kernel_lock_held(lock)
        analytics._FON[0] = 0
        analytics._storozh()
        if probe.read_bytes() != probe_before or analytics._FON[0] != 0:
            raise RuntimeError("ANALYTICS_WROTE_DURING_PUBLICATION_LOCK")
        for name in ("run_install", "run_rollback", "main"):
            try:
                getattr(task, name)()
            except task.Blocked as exc:
                if str(exc) != "TASK083_DEFERRED_WRITER_COORDINATION":
                    raise
                blocked_entries.append(name)
            else:
                raise RuntimeError("TASK083_ENTERED_WHILE_PUBLISHER_HELD:" + name)
    if html_snapshot(root) != dict(canonical, **{"video/analytics-probe.html": probe_before}):
        raise RuntimeError("BUSY_WRITERS_CHANGED_HTML")
    # Observe the real analytics os.replace while its original guard is active.
    # The audit hook only inspects an independently opened OS lock descriptor.
    analytics_lock_observations = []
    def observe(event, arguments):
        if event == "os.rename" and Path(os.fsdecode(arguments[1])) == probe:
            analytics_lock_observations.append(verify_kernel_lock_held(lock))
    sys.addaudithook(observe)
    analytics._FON[0] = 0
    analytics._storozh()
    expected_probe = probe_before.replace(b"</body>", analytics.STROKA.encode() + b"</body>", 1)
    if probe.read_bytes() != expected_probe or analytics_lock_observations != [True]:
        raise RuntimeError("ANALYTICS_OPTIONAL_WRITE_OR_LOCK_MISSING")
    changed = [name for name, value in canonical.items() if (root / name).read_bytes() != value]
    if changed:
        raise RuntimeError("ANALYTICS_CHANGED_CANONICAL_SHELL:" + ",".join(changed))
    # Actual decorated installer entry has been tested above. A two-card
    # rehearsal cannot pass the old installer's >=11/UA9/UA11 fleet contract.
    # Exercise its exact unchanged admission decorator around its real atomic
    # writer and pure generator patch, explicitly not a full TASK083 install.
    scheduled_probe = root / "tmp" / "task083-probe.txt"
    scheduled_lock_observations = []
    master_before = (root / "master_card.py").read_text()
    def admitted_work():
        scheduled_lock_observations.append(verify_kernel_lock_held(lock))
        analytics._FON[0] = 0
        before = html_snapshot(root)
        analytics._storozh()
        if analytics._FON[0] != 0 or html_snapshot(root) != before:
            raise RuntimeError("ANALYTICS_ENTERED_DURING_TASK083_LOCK")
        task._ua083_guard(task.atomic_write)(scheduled_probe, b"synthetic coordinated writer\n", 0o600)
        patched = task.patch_generator_source(master_before)
        task.validate_source(patched)
        if patched != master_before or task.patch_generator_source(patched) != patched:
            raise RuntimeError("TASK083_WOULD_OVERWRITE_FINAL_MASTER")
    task._ua083_guard(admitted_work)()
    if scheduled_probe.read_bytes() != b"synthetic coordinated writer\n" or scheduled_lock_observations != [True]:
        raise RuntimeError("TASK083_ACTUAL_ATOMIC_WRITE_MISSING")
    # Durable intent independently blocks both cooperating writers while the
    # publication lock is free; removing this synthetic fixture is not HALT.
    intent_dir = root / ".uaart_writer_coordination"
    intent_dir.mkdir()
    intent = intent_dir / "active-intent.json"
    intent.write_text('{"scope":"SYNTHETIC_REHEARSAL_ONLY"}\n')
    before = html_snapshot(root)
    analytics._FON[0] = 0
    analytics._storozh()
    if analytics._FON[0] != 0 or html_snapshot(root) != before:
        raise RuntimeError("ANALYTICS_IGNORED_DURABLE_INTENT")
    try:
        task.run_install()
    except task.Blocked as exc:
        if str(exc) != "TASK083_DEFERRED_DURABLE_WRITER_INTENT":
            raise
    else:
        raise RuntimeError("TASK083_IGNORED_DURABLE_INTENT")
    # Ordinary WSGI responses still delegate under writer coordination.
    calls = []
    def app(environ, start_response):
        calls.append(environ["PATH_INFO"])
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"synthetic application response"]
    statuses = []
    response = analytics.obolochka(app)({"PATH_INFO": "/catalog-test"}, lambda status, headers: statuses.append(status))
    if response != [b"synthetic application response"] or calls != ["/catalog-test"] or statuses != ["200 OK"]:
        raise RuntimeError("ORDINARY_WSGI_RESPONSE_CHANGED")
    if analytics._FON[0] != 0 or html_snapshot(root) != before:
        raise RuntimeError("ORDINARY_WSGI_RESPONSE_BYPASSED_DURABLE_INTENT")
    intent.unlink()
    final_checks = []
    for folder in ("video", "site"):
        for number in ("UA-0001", "UA-0003"):
            path = root / folder / (number + ".html")
            page = path.read_text()
            audit = specification.validate_page(page, number, specification.load_facts(number))
            assets = card_shell.validate_shell_assets(page, page)
            if assets["ordered_static_assets_sha256"] != specification.PINNED_SHELL_ASSETS_SHA256:
                raise RuntimeError("POST_WRITER_CARD_SHELL_CHANGED")
            final_checks.append({"path": str(path.relative_to(root)), "audit": audit})
        catalog = (root / folder / "katalog.html").read_text()
        if design.shell_fingerprint(catalog) != design.shell_fingerprint(design.GOLDEN_PATH.read_text()):
            raise RuntimeError("POST_WRITER_CATALOG_SHELL_CHANGED")
        if set(publisher_guard._href_counts(catalog)) != {"UA-0001", "UA-0003"}:
            raise RuntimeError("POST_WRITER_CATALOG_IDENTITIES_CHANGED")
    if any((root / name).read_bytes() != data for name, data in canonical.items()):
        raise RuntimeError("POST_WRITER_CANONICAL_HTML_CHANGED")
    if lock_identity != [lock.stat().st_dev, lock.stat().st_ino]:
        raise RuntimeError("SHARED_LOCK_INODE_REPLACED")
    if any(sha((root / name).read_bytes()) != digest for name, digest in protected_data.items()):
        raise RuntimeError("EXTERNAL_WRITERS_CHANGED_CRM_OR_SPEC_DATABASE")
    after_media = {str(path.relative_to(root)): sha(path.read_bytes())
                   for path in (root / "video" / "foto").rglob("*") if path.is_file()}
    if after_media != protected_media:
        raise RuntimeError("EXTERNAL_WRITERS_CHANGED_SAVED_MEDIA")
    return {"status": "PASS", "canonical_html_unchanged": len(canonical),
            "crm_and_spec_database_bytes_unchanged": True, "preserved_media_files": len(protected_media),
            "publisher_blocked_task083_entries": blocked_entries, "publisher_deferred_analytics": True,
            "analytics_atomic_write_kernel_lock_observations": analytics_lock_observations,
            "task083_atomic_write_kernel_lock_observations": scheduled_lock_observations,
            "task083_generator_patch_idempotent": True, "durable_intent_denies_both": True,
            "ordinary_wsgi_response_preserved": True, "final_primary_checks": final_checks,
            "lock_relative_path": lock.name, "lock_identity": lock_identity,
            "task083_scope": "Real guarded entries reject on contention/intent; admitted real atomic_write and pure generator patch. Full historical TASK083 installer not run.",
            "process_scope": "One isolated Python process; competing independent file descriptors use actual kernel flock, no flock stub.",
            "external_production_writer_verification": "NOT_EVALUATED"}


def source_identity_cycle():
    """Actual new policy with injected in-memory HTTP response, no network."""
    import source_policy as policy
    vin = "KNAXX0000J0000001"
    car = {"vin": vin, "brand": "Kia", "model": "K5", "year": "2018", "fuel": "LPI", "engine_cc": 1999}
    row = {"VIN": vin, "Make": "KIA", "Model": "K5", "ModelYear": "2018", "ErrorCode": "0", "Doors": "4"}
    if not policy.vpic_identity_matches(car, row):
        raise RuntimeError("SOURCE_EXACT_VIN_REJECTED")
    rejected = []
    for returned in ("KNAXX0000J0000002", "", "NHP10-1234567", "KNAXX0000J000000I"):
        if policy.vpic_identity_matches(car, dict(row, VIN=returned)):
            raise RuntimeError("SOURCE_WRONG_OR_INVALID_VIN_ACCEPTED")
        rejected.append(returned)
    class Response(io.BytesIO):
        status = 200
        def geturl(self):
            return "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/"
    requests = []
    def opener(request, **kwargs):
        requests.append(request.full_url)
        return Response(json.dumps({"Results": [dict(row, VIN="KNAXX0000J0000002")]}).encode())
    identity, facts = policy.decode_vpic(car, opener=opener)
    if identity.get("VIN") != "KNAXX0000J0000002" or not facts or len(requests) != 1:
        raise RuntimeError("DECODED_SOURCE_IDENTITY_NOT_PRESERVED")
    if policy.vpic_identity_matches(car, identity):
        raise RuntimeError("DECODED_FOREIGN_VIN_ACCEPTED")
    return {"status": "PASS", "scope": "OFFLINE_IN_MEMORY_RESPONSE_BINDING_ONLY", "network_requests": 0,
            "source10_live_acceptance": "NOT_EVALUATED", "wrong_or_invalid_vins_rejected": len(rejected),
            "decoded_foreign_identity_preserved_and_rejected": True, "configured_source_count": len(policy.SOURCE_DOMAINS)}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--dependencies", type=Path, required=True)
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.absolute()
    root, old, harness, inputs = prepare(args.candidate.absolute(), args.dependencies.absolute(), args.golden.absolute(), output)
    report = {"scope": "ISOLATED_FINAL17_COMBINED_SYNTHETIC_CYCLE", "status": "FAIL", "inputs": inputs,
              "production_changed": False, "overall_gate_b": "NOT_EVALUATED", "python_version": sys.version,
              "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "limitations": ["Synthetic cards only; no UA-0017/UA-0018 publication.",
                              "No Telegram callbacks, live worker, external source requests, service restart or production installation.",
                              "All seventeen modules staged and compiled; cars_ui not imported; ai_filter uses frozen listed AST functions.",
                              "Cooperative writer interaction is not proof of legacy process drain or full TASK083 fleet installation."]}
    os.environ.clear()
    os.environ.update({"UA_ART_ROOT": str(root), "UA_ART_MAIN_DB": str(root / "crm.db"),
                       "UA_ART_SPEC_DB": str(root / "vin_specs_task111_v3.db"), "TMPDIR": str(root / "tmp")})
    os.chdir(root)
    libraries = list({Path(sysconfig.get_path(key)).resolve() for key in ("stdlib", "platstdlib", "purelib", "platlib")})
    sys.path[:] = [str(root)] + [entry for entry in sys.path if entry and any(Path(entry).resolve() == lib or lib in Path(entry).resolve().parents for lib in libraries)]
    io_guard, counters = harness.make_guard(output, libraries)
    sys.addaudithook(io_guard)
    try:
        harness.seed_runtime = old.seed_runtime
        report["publisher"] = harness.scenario(root)
        if report["publisher"]["status"] != "PASS":
            raise RuntimeError("FROZEN_PUBLISHER_SCENARIO_FAILED")
        report["lifecycle"] = old.lifecycle_cycle(root)
        report["writers"] = writers_cycle(root)
        report["source_identity"] = source_identity_cycle()
        for name, entry in inputs["modules"].items():
            if sha((root / name).read_bytes()) != entry["staged_sha256"]:
                raise RuntimeError("STAGED_EXECUTION_SOURCE_CHANGED:" + name)
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
