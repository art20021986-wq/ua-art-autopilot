"""Run all isolated release suites and bind their receipt to unchanged code."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
CHILD = '''import json,sys,unittest
suite=unittest.defaultTestLoader.discover(sys.argv[1],pattern=sys.argv[2])
result=unittest.TextTestRunner(stream=sys.stderr,verbosity=1).run(suite)
print(json.dumps(dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped))))
raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)
'''


def hashes():
    return {str(path.relative_to(HERE)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(HERE.rglob('*')) if path.is_file()
            and (path.suffix in ('.py', '.txt') or
                 path == HERE / 'writer_patch/offline_validation.json' or
                 path == HERE / 'deploy/source_map.json' or
                 (path.suffix == '.json' and path.is_relative_to(HERE / 'deploy/recipe')))
            and '__pycache__' not in path.parts}


def verify_source_closure():
    """The admitted runtime snapshots must equal their reviewed source files."""
    receipt = json.loads((HERE / 'deploy/source_map.json').read_bytes())
    if receipt.get('status') != 'SOURCE_CLOSURE_MATERIALIZED' or not receipt.get('files'):
        raise ValueError('MATERIALIZED_SOURCE_CLOSURE_REQUIRED')
    for item in receipt['files']:
        paths = [HERE / item[key] for key in ('destination', 'source')]
        if any(path.is_symlink() or path.resolve(strict=True) != path or
               not path.is_relative_to(HERE) for path in paths):
            raise ValueError('MATERIALIZED_SOURCE_SCOPE')
        expected = item['sha256']
        if any(hashlib.sha256(path.read_bytes()).hexdigest() != expected for path in paths):
            raise ValueError('MATERIALIZED_SOURCE_DRIFT:' + item['destination'])
    return len(receipt['files'])


def validate(sources, receipt):
    sources = Path(sources).resolve(strict=True)
    fixtures = sources / 'public_fixture_tree'
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
        UA_DELETE_CURRENT_SOURCES=str(sources), UA_DELETE_PUBLIC_FIXTURES=str(fixtures),
        BASELINE_CARS_UI=str(sources / 'cars_ui.py'),
        BASELINE_CATALOG_MODULE=str(sources / 'ua_crm_catalog_folders.py'),
        UA_DELETE_WSGI_SOURCE=str(sources / 'www_uaart_com_ua_wsgi.py'),
        UA_TEST_FENCE_SOURCE=str(sources / 'publication_fence.py'),
        UA_TEST_PUBLISH_SOURCE=str(sources / 'publikaciya.py'),
        UA_TEST_SPEC_SOURCE=str(sources / 'ua_spec84_runtime.py'),
        UA_TEST_STAGE_SOURCE=str(sources / 'ua_stage_catalog_sync.py'),
        UA_TEST_CARS_SOURCE=str(sources / 'cars_ui.py'),
        UA_TEST_KADRY_SOURCE=str(sources / 'kadry_diagnostiki.py'),
        UA_TEST_PRIVATE_ROOT=str(sources))
    closure_count = verify_source_closure()
    before = hashes()
    for name in before:
        if name.endswith('.py'):
            ast.parse((HERE / name).read_bytes(), filename=name, feature_version=(3, 10))
    results = {}
    for folder in ('list_patch', 'deletion_core', 'writer_patch', 'route_patch', 'bot_patch',
                   'install', 'deploy', '.'):
        pattern = 'test_release.py' if folder == '.' else 'test_*.py'
        proc = subprocess.run([sys.executable, '-B', '-c', CHILD, str(HERE / folder), pattern],
            env=env, capture_output=True, text=True, timeout=180)
        key = 'composed_release' if folder == '.' else folder
        try:
            result = json.loads(proc.stdout.splitlines()[-1])
        except (ValueError, IndexError):
            result = {'tests': 0, 'failures': 0, 'errors': 1, 'skipped': 0}
        result['exit_code'] = proc.returncode
        results[key] = result
        print(json.dumps({key: result}), flush=True)
        if proc.returncode:
            print(proc.stderr[-16000:], file=sys.stderr)
    stable = before == hashes()
    passed = stable and all(value['exit_code'] == 0 and value['tests'] > 0 for value in results.values())
    value = {'task': 'UA-ART-CRM-DELETE-RECOVERY-002-v1.0',
             'status': 'OFFLINE_SUITE_PASS' if passed else 'OFFLINE_SUITE_FAILED',
             'observed_epoch': time.time(), 'source_stable_during_validation': stable,
             'materialized_source_closure_files': closure_count,
             'test_python': sys.version.split()[0], 'python_310_syntax': 'PASS',
             'suites': results, 'tests': sum(item['tests'] for item in results.values()),
             'code_sha256': before, 'production_installed': False,
             'live_telegram_acceptance': False, 'production_gate_b_pass': False}
    receipt = Path(receipt)
    if receipt.exists():
        raise ValueError('FRESH_RECEIPT_PATH_REQUIRED')
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    return passed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', required=True, type=Path)
    parser.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(0 if validate(args.sources, args.receipt) else 1)
