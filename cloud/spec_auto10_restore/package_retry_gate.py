#!/usr/bin/env python3
"""Package an exact allowlist for the v8 worker delta, never other gate code."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
INPUTS = (
    'cloud/spec_auto10_restore/lifecycle_integration.py',
    'cloud/spec_auto10_restore/tests/test_worker_recovery.py',
    'cloud/spec_auto10_restore/tests/test_worker_lifecycle_wiring.py',
    'cloud/spec_auto10_restore/tests/test_lifecycle.py',
    'cloud/spec_auto10_restore/tests/test_card_lifecycle.py',
    'cloud/spec_auto10_restore/tests/fixtures/lifecycle_current_handlers.py',
    'cloud/task_083_publish_transaction/publish_transaction_guard.py',
)


def build(output):
    output = Path(output).absolute()
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise ValueError('EXCLUSIVE_OUTPUT_REQUIRED')
    spec = importlib.util.spec_from_file_location('retry_gate_constants', HERE/'retry_gate.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    paths = {f'inputs/{name}': REPO/name for name in INPUTS}
    paths.update({'retry_gate.py': HERE/'retry_gate.py',
                  'guard_support.py': HERE/'server_gate.py',
                  'payload/vin_spec_service.py': HERE/'runtime/vin_spec_service.py'})
    members = {}
    for name, path in paths.items():
        if path.is_symlink() or not path.is_file():
            raise ValueError('PACKAGE_INPUT_MISSING_OR_SYMLINK')
        members[name] = path.read_bytes()
    if hashlib.sha256(members['payload/vin_spec_service.py']).hexdigest() != runner.V8_SHA:
        raise ValueError('FROZEN_SERVICE_CHANGED_REVIEW_REQUIRED')
    manifest = {'kind': 'ISOLATED_V8_WORKER_DELTA_ONLY', 'stage': str(runner.STAGE),
                'entrypoint': 'retry_gate.py', 'expected_tests': 50,
                'files': {name: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
                          for name, data in sorted(members.items())}}
    members['retry-gate-manifest.json'] = (json.dumps(manifest, sort_keys=True, indent=2)+'\n').encode()
    with output.open('xb') as handle:
        with zipfile.ZipFile(handle, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(members.items()):
                info = zipfile.ZipInfo(name, date_time=(2026, 9, 9, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100600 << 16
                archive.writestr(info, data)
    return {'status': 'PACKAGE_CREATED', 'file': str(output),
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'member_count': len(members), 'expected_tests': 50,
            'server_executed': False, 'production_changed': False,
            'stage': str(runner.STAGE), 'command': 'python3.10 -I -B retry_gate.py'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output)))
