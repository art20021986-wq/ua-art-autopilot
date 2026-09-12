#!/usr/bin/env python3
"""Run only isolated candidate tests from the fixed PythonAnywhere staging root.

From /home/Carix/spec_gate_b_restore_20260909:
  python3.10 -I -B cloud/spec_auto10_restore/server_gate.py

Seven existing production source files are read for hashes/copies only. No
production application is imported, no production database is read, and no
network/deploy/restart action is part of this runner. A successful result is a
Python 3.10 isolated test subgate; it never declares the overall Gate B passed.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time
import unittest
import urllib.parse

STAGE = Path('/home/Carix/spec_gate_b_restore_20260909')
SERVER_ROOT = Path('/home/Carix')
SOURCE_NAMES = (
    'cars_ui.py', 'publikaciya.py', 'ua_additional_spec.py', 'vin_spec_service.py',
    'source_policy.py', 'profile_library.py', 'publish_transaction_guard.py',
)
MAX_SOURCE_BYTES = 4 * 1024 * 1024
TMP_PARENT = Path('/tmp')
TMP_PREFIX = 'ua-art-spec-gate-'
LOCK_PROBE_SCRIPT = "import fcntl,sys; f=open(sys.argv[1],'a+'); fcntl.flock(f,fcntl.LOCK_EX); print('ready',flush=True); input()"


class GateError(RuntimeError):
    pass


def validate_owned_temp(path: Path) -> Path:
    """Accept only one privately owned direct child of the explicit temp root."""
    path = Path(path).absolute()
    if (path.is_symlink() or path.resolve() != path or path.parent != TMP_PARENT.resolve()
            or not path.name.startswith(TMP_PREFIX)):
        raise GateError('EXACT_OWNED_TEMP_DIRECTORY_REQUIRED')
    info = path.stat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o077):
        raise GateError('PRIVATE_OWNED_TEMP_DIRECTORY_REQUIRED')
    return path


def create_owned_temp() -> Path:
    return validate_owned_temp(Path(tempfile.mkdtemp(prefix=TMP_PREFIX, dir=str(TMP_PARENT))))


def failure_details(exc: Exception, phase: str) -> dict:
    """Keep errno and the phase without recording paths, source text or secrets."""
    result = {'failure_code': str(exc) if isinstance(exc, GateError) else type(exc).__name__,
              'failure_type': type(exc).__name__, 'failure_phase': phase}
    if isinstance(exc, OSError) and isinstance(exc.errno, int):
        result['failure_errno'] = exc.errno
    return result


def validate_stage(stage: Path, script: Path, cwd: Path) -> None:
    if stage != STAGE or stage.is_symlink() or stage.resolve() != stage or not stage.is_dir():
        raise GateError('EXACT_ISOLATED_STAGE_REQUIRED')
    if cwd != stage or cwd.resolve() != stage:
        raise GateError('CWD_MUST_BE_EXACT_ISOLATED_STAGE')
    if script.is_symlink() or script.resolve() != stage/'cloud/spec_auto10_restore/server_gate.py':
        raise GateError('RUNNER_MUST_BE_INSIDE_REVIEWED_PACKAGE')


def read_source_snapshot(server_root: Path, expected: dict) -> tuple[dict, dict]:
    if set(expected) != set(SOURCE_NAMES):
        raise GateError('EXPECTED_SEVEN_SOURCE_NAMES_REQUIRED')
    snapshots, contents = {}, {}
    for name in SOURCE_NAMES:
        if not re.fullmatch('[0-9a-f]{64}', str(expected[name])):
            raise GateError('EXPECTED_SOURCE_HASH_INVALID')
        path = server_root/name
        if path.is_symlink():
            raise GateError('PRODUCTION_SOURCE_SYMLINK:'+name)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_SOURCE_BYTES:
                raise GateError('PRODUCTION_SOURCE_TYPE_OR_SIZE:'+name)
            data = stream.read(MAX_SOURCE_BYTES+1)
            after = os.fstat(stream.fileno())
        current = path.stat()
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_mode')
        if any(getattr(before, key) != getattr(after, key) or getattr(after, key) != getattr(current, key)
               for key in fields):
            raise GateError('PRODUCTION_SOURCE_CHANGED_DURING_READ:'+name)
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected[name]:
            raise GateError('PRODUCTION_SOURCE_HASH_MISMATCH:'+name)
        snapshots[name] = {'sha256': digest, 'bytes': len(data), 'mtime_ns': after.st_mtime_ns,
                           'inode': after.st_ino, 'device': after.st_dev}
        contents[name] = data
    return snapshots, contents


def verify_package(stage: Path) -> dict:
    manifest = json.loads((stage/'server-gate-manifest.json').read_text())
    if manifest.get('required_stage') != str(STAGE):
        raise GateError('PACKAGE_STAGE_MISMATCH')
    members = manifest.get('files')
    if not isinstance(members, dict) or not members or len(members) > 400:
        raise GateError('PACKAGE_MANIFEST_INVALID')
    for name, info in members.items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise GateError('PACKAGE_PATH_INVALID')
        path = stage/relative
        if path.is_symlink() or not path.is_file() or stage not in path.resolve().parents:
            raise GateError('PACKAGE_FILE_MISSING_OR_SYMLINK')
        data = path.read_bytes()
        if len(data) != info['bytes'] or hashlib.sha256(data).hexdigest() != info['sha256']:
            raise GateError('PACKAGE_FILE_HASH_MISMATCH:'+name)
    actual_python = {path.relative_to(stage).as_posix()
                     for path in (stage/'cloud').rglob('*.py') if '__pycache__' not in path.parts}
    expected_python = {name for name in members if name.endswith('.py')}
    if actual_python != expected_python:
        raise GateError('UNMANIFESTED_OR_MISSING_PYTHON_MODULE')
    return manifest


def make_audit_guard(stage: Path, server_root: Path, *, owned_temp: Path | None = None):
    """Defence against accidental external I/O by these trusted local tests."""
    allowed_reads = {server_root/name for name in SOURCE_NAMES}
    write_roots = (stage,) if owned_temp is None else (stage, validate_owned_temp(owned_temp))
    counters = {'blocked_network_or_process_actions': 0, 'blocked_outside_stage_writes': 0,
                'blocked_production_reads': 0, 'isolated_lock_probe_processes': 0}
    def resolved(value, dir_fd=None):
        if isinstance(value, int) or value is None:
            return None
        path = Path(os.fsdecode(value))
        if not path.is_absolute() and dir_fd not in (None, -1, -100):
            path = Path(os.readlink('/proc/self/fd/' + str(dir_fd))) / path
        return path.absolute().resolve()
    def write_path(value, dir_fd=None):
        path = resolved(value, dir_fd)
        if path is not None and not inside(path):
            counters['blocked_outside_stage_writes'] += 1
            raise GateError('WRITE_OUTSIDE_ISOLATED_ROOTS_FORBIDDEN')
    def inside(path):
        return any(path == root or root in path.parents for root in write_roots)
    def read_path(value):
        path = resolved(value)
        if path is not None and server_root in path.parents and not inside(path) and path not in allowed_reads:
            counters['blocked_production_reads'] += 1
            raise GateError('PRODUCTION_DATA_READ_OR_IMPORT_FORBIDDEN')
    def guard(event, args):
        if event == 'subprocess.Popen':
            executable, command, cwd, env = args
            if (str(executable) == sys.executable and isinstance(command, (list, tuple))
                    and len(command) == 6 and str(command[0]) == sys.executable
                    and list(command[1:4]) == ['-I', '-B', '-c'] and command[4] == LOCK_PROBE_SCRIPT
                    and cwd is None and env is None):
                lock = resolved(command[5])
                if lock is not None and any(root in lock.parents for root in write_roots) and not lock.is_symlink():
                    counters['isolated_lock_probe_processes'] += 1
                    return
        if event.startswith(('socket.connect', 'socket.bind', 'socket.sendto', 'socket.getaddrinfo',
                             'subprocess.', 'os.system', 'os.posix_spawn', 'os.fork', 'os.exec')):
            counters['blocked_network_or_process_actions'] += 1
            raise GateError('NETWORK_AND_PROCESS_ACTIONS_FORBIDDEN')
        if event == 'open':
            path, mode, flags = args
            writing = (isinstance(mode, str) and any(char in mode for char in 'wax+')) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            write_path(path) if writing else read_path(path)
        elif event in {'os.remove', 'os.rmdir'}:
            write_path(args[0], args[1] if len(args) > 1 else None)
        elif event in {'os.mkdir', 'os.chmod'}:
            write_path(args[0], args[2] if len(args) > 2 else None)
        elif event == 'os.chown':
            write_path(args[0], args[3] if len(args) > 3 else None)
        elif event == 'os.utime':
            write_path(args[0], args[3] if len(args) > 3 else None)
        elif event == 'os.truncate':
            write_path(args[0])
        elif event in {'os.rename', 'os.link'}:
            write_path(args[0], args[2] if len(args) > 2 else None)
            write_path(args[1], args[3] if len(args) > 3 else None)
        elif event == 'os.symlink':
            write_path(args[1], args[2] if len(args) > 2 else None)
        elif event == 'sqlite3.connect':
            target = str(args[0])
            if target != ':memory:':
                if target.startswith('file:'):
                    target = urllib.parse.unquote(urllib.parse.urlsplit(target).path)
                write_path(target)
        elif event == 'import' and len(args) > 1 and args[1]:
            path = resolved(args[1])
            if path is not None and server_root in path.parents and not inside(path):
                raise GateError('PRODUCTION_APPLICATION_IMPORT_FORBIDDEN')
        elif event == 'compile' and len(args) > 1:
            path = resolved(args[1])
            if path is not None and server_root in path.parents and not inside(path):
                raise GateError('PRODUCTION_APPLICATION_COMPILE_FORBIDDEN')
    return guard, counters


class SanitizedResults(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scenarios = []
    def startTest(self, test):
        self.started = time.monotonic()
        super().startTest(test)
    def record(self, test, status, error=None):
        item = {'name': test.id(), 'status': status,
                'elapsed_seconds': round(time.monotonic()-self.started, 4)}
        if error:
            item['error_type'] = error[0].__name__
            item['error_phase'] = 'isolated_tests'
            if isinstance(error[1], OSError) and isinstance(error[1].errno, int):
                item['error_errno'] = error[1].errno
        self.scenarios.append(item)
    def addSuccess(self, test):
        self.record(test, 'PASS'); super().addSuccess(test)
    def addFailure(self, test, err):
        self.record(test, 'FAIL', err); super().addFailure(test, err)
    def addError(self, test, err):
        self.record(test, 'ERROR', err); super().addError(test, err)
    def addSkip(self, test, reason):
        self.record(test, 'SKIP'); super().addSkip(test, reason)


def main() -> int:
    report = {'task_id': 'UA-ART-SPEC-AUTO-10-RESTORE-001', 'status': 'NOT_RUN',
              'scope': 'PYTHON310_ISOLATED_TEST_SUBGATE', 'overall_gate_b': 'NOT_EVALUATED',
              'production_writes': 0, 'production_database_reads': 0,
              'production_application_imports': False, 'source_network_checks': 'NOT_RUN',
              'vin_decoder_network_check': 'NOT_RUN', 'live_crm_end_to_end': 'NOT_RUN',
              'python_version': '.'.join(map(str, sys.version_info[:3])),
              'execution_origin': 'PYTHONANYWHERE_ACCOUNT_ISOLATED_STAGE',
              'filesystem_scope': {'renameat2_noreplace': 'UNSUPPORTED_IN_PRIOR_SERVER_RUNS_ERRNO_22',
                  'home_candidate_commit': 'NOT_RUN', 'home_runtime_write_compatibility': 'NOT_ESTABLISHED'},
              'started_at_utc': dt.datetime.now(dt.timezone.utc).isoformat()}
    run = None
    phase = 'stage_validation'
    try:
        validate_stage(STAGE, Path(__file__).absolute(), Path.cwd())
        run = STAGE/('run-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        run.mkdir(mode=0o700)
        phase = 'python_version'
        if sys.version_info[:2] != (3, 10):
            raise GateError('PYTHON_3_10_REQUIRED')
        sys.dont_write_bytecode = True
        phase = 'package_verification'
        manifest = verify_package(STAGE)
        report['package_file_count'] = len(manifest['files'])
        expected = json.loads((STAGE/'server-expected-sources.json').read_text())['source_byte_hashes']
        phase = 'source_snapshot_before'
        before, contents = read_source_snapshot(SERVER_ROOT, expected)
        report['production_sources_before'] = before
        source_copy = run/'source-copy-readonly'
        source_copy.mkdir(mode=0o700)
        for name, data in contents.items():
            with (source_copy/name).open('xb') as handle:
                handle.write(data)
            os.chmod(source_copy/name, 0o600)
        phase = 'isolated_temp_creation'
        owned_temp = create_owned_temp()
        temp = owned_temp/'temporary-test-data'
        temp.mkdir(mode=0o700)
        tempfile.tempdir = str(temp)
        report['isolated_write_roots'] = [str(STAGE), str(owned_temp)]
        report['candidate_output_root'] = str(run/'compiled-candidate')
        # Do not retain the live home or any environment-supplied home path in
        # import search paths. No environment variables or secret files read.
        sys.path = [entry for entry in sys.path if entry and not (
            Path(entry).absolute() == SERVER_ROOT or SERVER_ROOT in Path(entry).absolute().parents)]
        sys.path.insert(0, str(STAGE/'cloud/spec_auto10_restore/runtime'))
        guard, counters = make_audit_guard(STAGE, SERVER_ROOT, owned_temp=owned_temp)
        sys.addaudithook(guard)
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            phase = 'candidate_compile'
            compiler_spec = importlib.util.spec_from_file_location(
                'isolated_server_candidate_compiler', STAGE/'cloud/spec_auto10_restore/prepare_candidate.py')
            compiler = importlib.util.module_from_spec(compiler_spec)
            compiler_spec.loader.exec_module(compiler)
            compiled = compiler.prepare(source_copy, run/'compiled-candidate')
            verified = compiler.verify_candidate(run/'compiled-candidate')
            if verified != compiled:
                raise GateError('CANDIDATE_READINESS_MANIFEST_MISMATCH')
            report['candidate'] = {'status': compiled['status'], 'module_count': compiled['module_count'],
                                   'files': compiled['files'], 'application_imported': False,
                                   'publication_mode': compiled['publication_mode'],
                                   'readiness_and_hashes_verified': True}
            report['filesystem_scope']['home_candidate_commit'] = 'PASS'
            phase = 'isolated_tests'
            tests = unittest.defaultTestLoader.discover(str(STAGE/'cloud/spec_auto10_restore/tests'), pattern='test_*.py')
            result = unittest.TextTestRunner(stream=captured, resultclass=SanitizedResults).run(tests)
        report['tests'] = {'run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
                           'skipped': len(result.skipped), 'expected_failures': len(result.expectedFailures),
                           'scenarios': result.scenarios}
        report['io_guard'] = counters
        phase = 'source_snapshot_after'
        after, _ = read_source_snapshot(SERVER_ROOT, expected)
        report['production_sources_after'] = after
        if before != after:
            raise GateError('PRODUCTION_SOURCE_HASH_OR_MTIME_CHANGED_DURING_TESTS')
        phase = 'package_recheck'
        verify_package(STAGE)
        report['production_source_bytes_and_mtimes_unchanged'] = True
        denied_actions = any(value for key, value in counters.items() if key.startswith('blocked_'))
        report['status'] = 'PASS' if (result.wasSuccessful() and not result.skipped
            and not result.expectedFailures and result.testsRun > 0 and not denied_actions) else 'FAIL'
        report['limitations'] = ['No live CRM/Telegram callbacks or deployed worker were executed.',
            'Seven source hashes establish a stable source snapshot, not current process import bindings.',
            'External sources and individual VIN verification were not requested and remain NOT_RUN.',
            'No install, database correction, deployment, restart, or production publication was performed.',
            'Only the exact isolated Python -I -B flock probe may create a child process; all other process/network actions are forbidden.',
            'The candidate is saved and verified in the isolated home staging folder; test databases/pages use one fresh private /tmp directory.',
            'Manifest-last mode commits readiness only after every file is complete; it does not claim atomic visibility of the whole directory.',
            'Candidate commit compatibility does not establish the running publisher, production write paths or the overall Gate B.',
            'This result cannot establish the overall Gate B or release permission.']
    except Exception as exc:
        report['status'] = 'FAIL'
        report.update(failure_details(exc, phase))
    report['finished_at_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
    if run is not None:
        output = run/'server-gate-result.json'
        with output.open('x', encoding='utf-8') as handle:
            json.dump(report, handle, ensure_ascii=True, indent=2)
            handle.write('\n')
        os.chmod(output, 0o600)
        result_path = str(output)
    else:
        result_path = None
    print(json.dumps({'status': report['status'], 'scope': report['scope'],
                      'overall_gate_b': 'NOT_EVALUATED', 'tests_run': report.get('tests', {}).get('run', 0),
                      'failures': report.get('tests', {}).get('failures'),
                      'errors': report.get('tests', {}).get('errors'),
                      'skipped': report.get('tests', {}).get('skipped'),
                      'candidate_mode': report.get('candidate', {}).get('publication_mode'),
                      'candidate_modules': report.get('candidate', {}).get('module_count'),
                      'candidate_verified': report.get('candidate', {}).get('readiness_and_hashes_verified'),
                      'sources_unchanged': report.get('production_source_bytes_and_mtimes_unchanged'),
                      'io_guard': report.get('io_guard'),
                      'failed_scenarios': [item for item in report.get('tests', {}).get('scenarios', [])
                                           if item['status'] != 'PASS'],
                      'failure_code': report.get('failure_code'), 'failure_errno': report.get('failure_errno'),
                      'failure_phase': report.get('failure_phase'), 'report': result_path}, ensure_ascii=True))
    return 0 if report['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
