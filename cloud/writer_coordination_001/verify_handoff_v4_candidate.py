#!/usr/bin/env python3
"""One local admission/install/rollback check with real final17 v3 payload bytes.

Authority, quota, session and thirteen legacy fixture files are deliberately
synthetic. Four fixture files start absent, matching the observation's shape.
This harness provides no live verifier, owner command or production evidence.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
OLD_MANIFEST = '12afce821b784771a2a8a0415cc289f5e713d53aabedf0ed3e2747a8c4d4e136'
NEW_CARS_UI = '57ad5acc340d412aa9d95e1ef56c7de85d4346ad6bbc755fda311763f3637a42'


def check(value, reason):
    if not value:
        raise AssertionError(reason)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def install_guard():
    """Install before project imports or candidate inspection; no live transport."""
    blocked = {'network': 0, 'subprocess': 0, 'production_access': 0}
    def audit(event, values):
        key = None
        if event in ('socket.__new__', 'socket.connect', 'socket.connect_ex',
                     'socket.getaddrinfo', 'socket.bind', 'socket.sendto'):
            key = 'network'
        elif event.startswith(('subprocess.', 'os.exec', 'os.spawn')) or event in ('os.system', 'os.fork', 'os.forkpty'):
            key = 'subprocess'
        elif event == 'open' or event in ('os.remove', 'os.unlink', 'os.rename', 'os.replace',
                'os.chmod', 'os.utime', 'os.mkdir', 'os.rmdir', 'os.link', 'os.symlink',
                'os.truncate', 'os.scandir', 'os.listdir', 'os.chdir'):
            paths = values[:2] if event in ('os.rename', 'os.replace', 'os.link', 'os.symlink') else values[:1]
            for value in paths:
                if isinstance(value, (str, bytes, os.PathLike)):
                    path = os.path.abspath(os.fsdecode(value))
                    if path == '/home/Carix' or path.startswith('/home/Carix/'):
                        key = 'production_access'
        if key:
            blocked[key] += 1
            raise RuntimeError('FORBIDDEN_FIXTURE_IO:' + key)
    sys.addaudithook(audit)
    return blocked


def reject(module, candidate):
    try:
        module.inspect_candidate(candidate)
    except module.HandoffError as error:
        check(str(error) == 'EXACT_COMPLETE17_MANIFEST_REQUIRED', 'wrong rejection')
        return str(error)
    raise AssertionError('wrong candidate admitted')


class FixtureAuthority:
    """FAKE TEST AUTHORITY: digest-shaped strings are not authenticated proof."""
    def __init__(self):
        self.phases = []

    def __call__(self, plan, challenge, phase):
        self.phases.append(phase)
        now = time.time()
        return {
            'status': handoff.PROOF_STATUS, 'challenge': challenge,
            'session': plan['session'], 'install_plan_sha256': plan['install_plan_sha256'],
            'coordination_plan_sha256': plan['coordination_plan_sha256'],
            'candidate_manifest_sha256': handoff.MANIFEST_SHA256,
            'issued_at': now, 'expires_at': now + 20,
            'authorization_receipt_sha256': 'a' * 64,
            'pause_readback_sha256': 'b' * 64, 'drain_receipt_sha256': 'c' * 64,
            'storage_quota': {
                'source': 'AUTHENTICATED_PYTHONANYWHERE_ACCOUNT_QUOTA',
                'used_bytes': 1_000_000_000, 'quota_bytes': 35_000_000_000,
                'observed_at': now, 'receipt_sha256': 'd' * 64,
            },
        }


def run(args):
    global previous, handoff, server_fence
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    blocked = install_guard()
    live_path = HERE / 'evidence/live17-preconditions-20260909.json'
    inputs = [HERE / name for name in ('code_handoff_v3.py', 'code_handoff_v4.py',
              'server_fence.py', 'prepare_maintenance_v3.py', Path(__file__).name)]
    inputs += [live_path]
    inputs += sorted(path for tree in (args.candidate, args.previous_candidate)
                     for path in tree.rglob('*') if path.is_file())
    inputs_before = {str(path): digest(path) for path in inputs}
    import code_handoff_v3 as previous
    import code_handoff_v4 as handoff
    import server_fence
    old_source = (HERE / 'code_handoff_v3.py').read_bytes()
    expected = old_source.replace(OLD_MANIFEST.encode(), handoff.MANIFEST_SHA256.encode()).replace(
        b'UA-ART-COMPLETE17-CODE-HANDOFF-3', b'UA-ART-COMPLETE17-CODE-HANDOFF-4').replace(
        b'UA-ART-SPEC-AUTO10-COMPLETE-17-V2', b'UA-ART-SPEC-AUTO10-COMPLETE-17-V3')
    check(expected == (HERE / 'code_handoff_v4.py').read_bytes(), 'installer algorithm delta')
    check(previous.MANIFEST_SHA256 == OLD_MANIFEST, 'old installer pin changed')
    for name in ('code_handoff_v4.py', 'prepare_maintenance_v3.py', Path(__file__).name):
        compile((HERE / name).read_bytes(), name, 'exec')

    old_manifest, old_payload = previous.inspect_candidate(args.previous_candidate)
    manifest, payload = handoff.inspect_candidate(args.candidate)
    check(set(payload) == set(old_payload) and len(payload) == 17, 'candidate file set delta')
    changed = sorted(name for name in payload if payload[name] != old_payload[name])
    check(changed == ['cars_ui.py'], 'unexpected application byte changes')
    check(handoff.sha(payload['cars_ui.py']) == NEW_CARS_UI, 'cars_ui patch pin')
    check(manifest['execution_dependency_pins'] == old_manifest['execution_dependency_pins'],
          'dependency pin delta')
    rejections = {
        'old_installer_rejects_new_candidate': reject(previous, args.candidate),
        'new_installer_rejects_old_candidate': reject(handoff, args.previous_candidate),
    }
    live = json.loads(live_path.read_bytes())
    absent = {name for name, value in live['hashes'].items() if value is None}
    check(set(live['hashes']) == set(payload) and len(absent) == 4, 'live capture shape')
    dependency_bytes = {}
    for name, expected_sha in manifest['execution_dependency_pins'].items():
        path = args.golden if name == 'catalog_design_golden.html' else args.dependencies / name
        raw = path.read_bytes()
        check(handoff.sha(raw) == expected_sha, 'dependency bytes:' + name)
        dependency_bytes[name] = raw

    # The only target files below live in a new local TemporaryDirectory.
    with tempfile.TemporaryDirectory(prefix='handoff-v4-actual17-fixture-') as temp:
        base = Path(temp).resolve()
        root, control = base / 'fixture', base / 'control'
        root.mkdir(); control.mkdir()
        nonce = '1' * 64
        (control / 'sessions' / nonce).mkdir(parents=True)
        session = {
            'repository': 'art20021986-wq/ua-art-autopilot', 'account': 'Carix',
            'production_root': '/home/Carix', 'task_id': 'HANDOFF-V4-ISOLATED-FIXTURE',
            'expected_main': '2' * 40, 'plan_sha256': '3' * 64,
            'run_id': '123', 'run_attempt': 1, 'nonce': nonce, 'epoch': 1,
            'source_sha256': digest(HERE / 'server_fence.py'),
        }
        for name in server_fence.LOCK_NAMES:
            (root / name).write_bytes(b'')
        before = {}
        for index, name in enumerate(sorted(payload)):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if name in absent:
                before[name] = None
            else:
                path.write_bytes(('# SYNTHETIC LEGACY FILE %d\n' % index).encode())
                path.chmod(0o640)
                os.utime(path, ns=(123_000_000_000, 123_000_000_000))
                before[name] = digest(path)
        for name, raw in dependency_bytes.items():
            (root / name).write_bytes(raw)
        lease = server_fence.FenceLease(root, control, session)
        lease.acquire()
        authority = FixtureAuthority()
        try:
            plan = handoff.make_install_plan(session, args.candidate, before,
                                            coordination_plan_sha256='4' * 64)
            def new_worker():
                return handoff.CodeHandoff(lease, args.candidate, plan, verify_window=authority)
            worker = new_worker()
            installed = worker.install()
            check(installed['status'] == 'CODE_INSTALLED_READBACK', 'installation terminal')
            check(new_worker().read_terminal() == installed, 'installation terminal readback')
            check(all((root / name).read_bytes() == data for name, data in payload.items()), 'actual17 readback')
            restored = new_worker().rollback_only()
            check(restored['status'] == 'CODE_ROLLED_BACK_READBACK', 'rollback terminal')
            check(new_worker().read_terminal() == restored, 'current rollback readback')
            for name, expected_sha in before.items():
                path = root / name
                if expected_sha is None:
                    check(not path.exists(), 'absent rollback:' + name)
                else:
                    check(digest(path) == expected_sha and path.stat().st_mode & 0o777 == 0o640
                          and path.stat().st_mtime_ns == 123_000_000_000, 'exact legacy rollback:' + name)
            check(all((root / name).read_bytes() == raw for name, raw in dependency_bytes.items()), 'dependency drift')
            lease._check()
            check(lease.held and len(lease.handles) == 6, 'fixture lock continuity')
            for receipt in (installed, restored):
                check(receipt['unpause_authorized'] is False and receipt['tasks_resumed'] is False
                      and receipt['loaded_runtime_verified'] is False and receipt['crm_html_media_writes'] == 0,
                      'receipt scope')
            check({'BEFORE_HANDOFF', 'STORAGE_PREFLIGHT', 'BEFORE_INSTALL', 'INSTALL_READBACK',
                   'BEFORE_CRASH_RECOVERY', 'BEFORE_ROLLBACK', 'ROLLBACK_READBACK',
                   'TERMINAL_READBACK'} <= set(authority.phases), 'missing authority phases')
            for name in payload:
                check(authority.phases.count('BEFORE_WRITE:' + name) == 1
                      and authority.phases.count('BEFORE_ROLLBACK_WRITE:' + name) == 1,
                      'per-target fixture authorization:' + name)
        finally:
            lease.close()
    check(inputs_before == {str(path): digest(path) for path in inputs}, 'input bytes changed')
    check(not any(blocked.values()), 'forbidden IO attempted')
    application_modules = {Path(name).stem for name in payload}
    check(not application_modules.intersection(sys.modules), 'application module imported')
    return {
        'schema': 'UA-ART-HANDOFF-V4-ACTUAL17-LOCAL-ADMISSION-1', 'status': 'PASS',
        'started_at': started, 'finished_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'python_version': sys.version, 'candidate_id': manifest['candidate_id'],
        'candidate_manifest_sha256': handoff.MANIFEST_SHA256,
        'installer_sha256': digest(HERE / 'code_handoff_v4.py'),
        'validation_source_sha256': {name: digest(HERE / name) for name in
            ('code_handoff_v3.py', 'code_handoff_v4.py', 'server_fence.py',
             'prepare_maintenance_v3.py', Path(__file__).name)},
        'algorithm_byte_identical_after_three_admission_literal_substitutions': True,
        'compiled_actual_candidate_modules': len(payload), 'changed_application_files': changed,
        'cars_ui_sha256': NEW_CARS_UI, 'unchanged_application_file_count': 16,
        'candidate_pin_was_patched_for_test': False, 'candidate_source_inputs_unchanged': True,
        'candidate_after_sha256': {name: handoff.sha(raw) for name, raw in sorted(payload.items())},
        'wrong_candidate_rejections': rejections,
        'fixture_install_rollback_cycles': 1, 'fixture_before_present': 13, 'fixture_before_absent': 4,
        'fixture_legacy_bytes': 'SYNTHETIC; NOT ACTUAL LIVE17 PRECONDITION BYTES',
        'fixture_authority_quota_and_session': 'SYNTHETIC; NOT AUTHENTICATED',
        'fixture_install_status': installed['status'], 'fixture_rollback_status': restored['status'],
        'fixture_six_locks_held_through_readback': True, 'original_modes_mtime_and_absence_restored': True,
        'unchanged_execution_dependency_pins': manifest['execution_dependency_pins'],
        'fixture_authority_phase_count': len(authority.phases), 'blocked_io_attempts': blocked,
        'production_changed': False, 'production_lock_files_opened': False, 'real_task_api_called': False,
        'application_imported': False, 'real_external_writers_verified': False,
        'unpause_authorized': False, 'overall_gate_b': 'NOT_EVALUATED',
        'validation_scope': 'LOCAL_TARGETED_ADMISSION_AND_ONE_ACTUAL17_BYTE_FIXTURE_INSTALL_ROLLBACK',
        'historical_v3_server_30_tests_rerun': False,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--previous-candidate', type=Path, required=True)
    parser.add_argument('--dependencies', type=Path, required=True)
    parser.add_argument('--golden', type=Path, required=True)
    arguments = parser.parse_args()
    for key in ('candidate', 'previous_candidate', 'dependencies', 'golden'):
        setattr(arguments, key, getattr(arguments, key).resolve())
    print(json.dumps(run(arguments), sort_keys=True, indent=2, ensure_ascii=False))
