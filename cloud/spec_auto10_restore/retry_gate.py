#!/usr/bin/env python3
"""Fixed-path, isolated v8 worker delta gate. This is never a deployment."""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest

STAGE = Path('/home/Carix/spec_retry_v8_20260909')
OLD = Path('/home/Carix/spec_gate_b_restore_20260909/run-20260909T055742431417Z/compiled-candidate')
ROOT = Path('/home/Carix')
TESTS = ('test_worker_recovery.py', 'test_worker_lifecycle_wiring.py', 'test_lifecycle.py')
V8_SHA = 'a4468d2de5fd35d0778dea0ee15ad382dcb680ec4aa344da217cfce67f088c16'
V7_PINS = {
    'card_lifecycle.py': 'a0f65fedcf91cbe01f0b891ddde31b97186e9c7ae77e51cef905cf29a81b55b7',
    'card_shell.py': '9d764eae5f73e8b75e8c863abb9c3ae8c3a44f0bd1fa2918a28a80e996556b0a',
    'cars_ui.py': '32dfec40ca2e6badfab222fd811fa710c52708fc0ff6bad80cbce79c0df5a0ec',
    'profile_library.py': '6784b5641a1bd6f8e094a0bc7ca4769596f91082f46891515463a933d2225eb6',
    'publikaciya.py': '224d140151e26ff597962f17f45ec928f0716fb873e139e9686aac0256de87e8',
    'publish_transaction_guard.py': 'eb8a37c5bba85b74cf3d6ed4c326d20d69a92274dee1e75f80108b5fa9834912',
    'source_policy.py': 'e9590c1630a8c81bcacf05d620e273a341aaf407f39c3a1bd184258c17ce3f0d',
    'spec_publication.py': '3e2ed470ebc06a9cbf03357858aeaf63cc6262045384867fca6b7b95bb181718',
    'ua_additional_spec.py': '5a03cb99d1f4514539956f32a75e09e119e2e9049a91da6326adb32877518e56',
    'vin_spec_service.py': 'b3a90347c15e3063abe072f4b159b78e392a2da8f2e15f2bf9a37ba59bc9e7a7',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_exact(path, expected=None):
    path = Path(path)
    if path.is_symlink() or path.resolve() != path:
        raise RuntimeError('INPUT_SYMLINK')
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > 4 * 1024 * 1024:
        raise RuntimeError('INPUT_TYPE_OR_SIZE')
    with path.open('rb') as handle:
        data = handle.read(4 * 1024 * 1024 + 1)
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise RuntimeError('INPUT_CHANGED_DURING_READ')
    digest = sha(data)
    if expected is not None and digest != expected:
        raise RuntimeError('INPUT_HASH_MISMATCH:' + path.name)
    return data, {'sha256': digest, 'bytes': len(data), 'mtime_ns': after.st_mtime_ns}


def verify_package():
    raw, _ = read_exact(STAGE/'retry-gate-manifest.json')
    manifest = json.loads(raw)
    if manifest.get('stage') != str(STAGE) or manifest.get('kind') != 'ISOLATED_V8_WORKER_DELTA_ONLY':
        raise RuntimeError('PACKAGE_SCOPE_MISMATCH')
    expected = set(manifest['files']) | {'retry-gate-manifest.json'}
    actual = {str(path.relative_to(STAGE)) for path in STAGE.rglob('*')
              if path.is_file() and not path.relative_to(STAGE).parts[0].startswith('run-')}
    if expected != actual:
        raise RuntimeError('PACKAGE_MEMBER_SET_MISMATCH')
    values = {}
    for name, item in manifest['files'].items():
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise RuntimeError('PACKAGE_PATH_INVALID')
        values[name], _ = read_exact(STAGE/name, item['sha256'])
        if len(values[name]) != item['bytes']:
            raise RuntimeError('PACKAGE_LENGTH_MISMATCH')
    if sha(values['payload/vin_spec_service.py']) != V8_SHA:
        raise RuntimeError('FROZEN_V8_MISMATCH')
    return manifest, values


def old_snapshot():
    if OLD.is_symlink() or OLD.resolve() != OLD:
        raise RuntimeError('V7_DIRECTORY_SYMLINK')
    if {path.name for path in OLD.iterdir()} != set(V7_PINS) | {'manifest.json'}:
        raise RuntimeError('V7_MODULE_SET_MISMATCH')
    contents, metadata = {}, {}
    for name, digest in V7_PINS.items():
        contents[name], metadata[name] = read_exact(OLD/name, digest)
    raw, metadata['manifest.json'] = read_exact(OLD/'manifest.json')
    manifest = json.loads(raw)
    if manifest.get('module_count') != 10 or set(manifest.get('files', {})) != set(V7_PINS):
        raise RuntimeError('V7_MANIFEST_SCOPE_MISMATCH')
    if any(manifest['files'][name]['after_sha256'] != digest for name, digest in V7_PINS.items()):
        raise RuntimeError('V7_MANIFEST_HASH_MISMATCH')
    return contents, metadata


def main():
    if (STAGE.is_symlink() or STAGE.resolve() != STAGE or Path.cwd() != STAGE
            or Path(__file__).resolve() != STAGE/'retry_gate.py'):
        raise RuntimeError('EXACT_PRIVATE_STAGE_REQUIRED')
    if stat.S_IMODE(STAGE.stat().st_mode) & 0o077:
        raise RuntimeError('PRIVATE_STAGE_MODE_REQUIRED')
    if sys.version_info[:2] != (3, 10):
        raise RuntimeError('PYTHON310_REQUIRED')
    manifest, payload = verify_package()
    contents, before = old_snapshot()
    spec = importlib.util.spec_from_file_location('pinned_gate_support', STAGE/'guard_support.py')
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run = STAGE/('run-' + stamp)
    run.mkdir(mode=0o700)
    temp = support.create_owned_temp()
    tempfile.tempdir = str(temp)
    base_guard, counters = support.make_audit_guard(STAGE, ROOT, owned_temp=temp)
    allowed_old = {OLD/name for name in set(V7_PINS) | {'manifest.json'}}
    def guard(event, args):
        if event == 'open' and not isinstance(args[0], int):
            path, mode, flags = args
            writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            target = Path(os.fsdecode(path)).absolute().resolve()
            if not writing and target in allowed_old:
                return  # Exact frozen candidate byte reads only; never import.
            if not writing and ROOT in target.parents and not (STAGE in target.parents or target == STAGE):
                counters['blocked_production_reads'] += 1
                raise support.GateError('LIVE_HOME_DATA_READ_FORBIDDEN')
        if event.startswith(('subprocess.', 'os.system', 'os.posix_spawn', 'os.fork', 'os.exec')):
            counters['blocked_network_or_process_actions'] += 1
            raise support.GateError('ALL_CHILD_PROCESSES_FORBIDDEN')
        base_guard(event, args)
    sys.addaudithook(guard)
    report = {'scope': 'PYTHON310_V8_WORKER_DELTA_ONLY', 'status': 'NOT_RUN',
              'started_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'overall_gate_b': 'NOT_EVALUATED', 'production_changed': False,
              'source_checks': 'NOT_RUN', 'live_crm_executed': False,
              'v7_input': str(OLD), 'v8_service_sha256': V8_SHA, 'io_guard': counters}
    try:
        for name, data in payload.items():
            if name.startswith('inputs/'):
                target = run/name.removeprefix('inputs/')
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as handle:
                    handle.write(data)
        package = run/'cloud/spec_auto10_restore'
        runtime = package/'runtime'
        runtime.mkdir(mode=0o700)
        candidate = dict(contents)
        candidate['vin_spec_service.py'] = payload['payload/vin_spec_service.py']
        for name, data in candidate.items():
            with (runtime/name).open('xb') as handle:
                handle.write(data)
            compile(data, str(runtime/name), 'exec')
        candidate_manifest = {name: sha(data) for name, data in candidate.items()}
        with (run/'candidate-manifest.json').open('x') as handle:
            json.dump({'scope': 'ISOLATED_V8_SHADOW_ONLY', 'files': candidate_manifest}, handle, sort_keys=True)
        sys.path = [p for p in sys.path if p and not (Path(p).absolute() == ROOT or ROOT in Path(p).absolute().parents)]
        sys.path.insert(0, str(runtime))
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            suite = unittest.TestSuite()
            for pattern in TESTS:
                suite.addTests(unittest.defaultTestLoader.discover(str(package/'tests'), pattern=pattern))
            result = unittest.TextTestRunner(stream=captured, resultclass=support.SanitizedResults).run(suite)
        _, after = old_snapshot()
        verify_package()
        runtime_after = {name: sha(read_exact(runtime/name)[0]) for name in candidate}
        if before != after or runtime_after != candidate_manifest:
            raise RuntimeError('FROZEN_INPUT_OR_CANDIDATE_CHANGED')
        report.update({'tests_run': result.testsRun, 'failures': len(result.failures),
                       'errors': len(result.errors), 'skipped': len(result.skipped),
                       'scenarios': result.scenarios, 'v7_bytes_and_mtimes_unchanged': True,
                       'candidate_files': candidate_manifest, 'candidate_unchanged_during_test': True,
                       'candidate_root': str(runtime)})
        report['status'] = 'PASS' if (result.wasSuccessful() and result.testsRun == 50
            and not result.skipped and not result.expectedFailures and not any(counters.values())) else 'FAIL'
    except Exception as exc:
        report.update({'status': 'FAIL', 'failure_type': type(exc).__name__,
                       'failure_code': str(exc) if isinstance(exc, (RuntimeError, support.GateError)) else type(exc).__name__})
    report['completed_at_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
    report['report_path'] = str(run/'retry-gate-result.json')
    with (run/'retry-gate-result.json').open('x') as handle:
        json.dump(report, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write('\n')
    print(json.dumps({key: report.get(key) for key in ('status', 'tests_run', 'failures', 'errors',
        'skipped', 'v7_bytes_and_mtimes_unchanged', 'io_guard', 'failure_code', 'report_path')}, ensure_ascii=True))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
