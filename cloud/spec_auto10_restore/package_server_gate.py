#!/usr/bin/env python3
"""Build a self-contained, inert ZIP for the isolated PythonAnywhere test gate.

No upload, server connection, deployment or process operation is performed.
Run this after the final candidate modules/tests have been combined.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
SOURCE_NAMES = (
    'cars_ui.py', 'publikaciya.py', 'ua_additional_spec.py', 'vin_spec_service.py',
    'source_policy.py', 'profile_library.py', 'publish_transaction_guard.py',
)
LEGACY_FIXTURES = (
    'cloud/task_111_vin_spec_10src/integration_patcher.py',
    'cloud/task_099_site_crm_repair/task099_patches.py',
    'cloud/task_099_site_crm_repair/ua_additional_spec.py',
    'cloud/task_083_publish_transaction/publish_transaction_guard.py',
)


def build(output: Path) -> dict:
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('OUTPUT_ALREADY_EXISTS')
    if not output.parent.is_dir():
        raise ValueError('OUTPUT_PARENT_MISSING')
    evidence = json.loads((HERE/'evidence/runtime-verified-readonly.json').read_text())
    hashes = {name: evidence['source_byte_hashes'][name] for name in SOURCE_NAMES}
    if any(not re.fullmatch('[0-9a-f]{64}', value) for value in hashes.values()):
        raise ValueError('EXPECTED_SOURCE_HASH_INVALID')
    expected = {'source': 'runtime-verified-readonly.json', 'checked_at': evidence['checked_at'],
                'server_root': '/home/Carix', 'source_byte_hashes': hashes}
    members = {}
    paths = list(HERE.rglob('*.py')) + [REPOSITORY/name for name in LEGACY_FIXTURES]
    paths.append(HERE/'tests/fixtures/reviewed_shell_assets.html')
    for path in sorted(paths):
        if '__pycache__' in path.parts or path.is_symlink() or not path.is_file():
            if path.is_symlink():
                raise ValueError('SYMLINK_INPUT_FORBIDDEN')
            continue
        relative = path.relative_to(REPOSITORY).as_posix()
        if relative.startswith('/') or '..' in Path(relative).parts:
            raise ValueError('INVALID_ARCHIVE_PATH')
        members[relative] = path.read_bytes()
    if not all(name in members for name in LEGACY_FIXTURES):
        raise ValueError('LEGACY_FIXTURE_MISSING')
    members['server-expected-sources.json'] = (json.dumps(expected, ensure_ascii=True, indent=2)+'\n').encode()
    # The packager's own offline tests need only these seven reviewed hashes;
    # do not include unrelated database metadata from the original evidence.
    members['cloud/spec_auto10_restore/evidence/runtime-verified-readonly.json'] = members['server-expected-sources.json']
    manifest = {'task_id': 'UA-ART-SPEC-AUTO-10-RESTORE-001',
                'kind': 'ISOLATED_PYTHON310_TEST_PACKAGE_NOT_A_DEPLOYMENT',
                'required_stage': '/home/Carix/spec_gate_b_restore_20260909',
                'entrypoint': 'cloud/spec_auto10_restore/server_gate.py',
                'files': {name: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
                          for name, data in sorted(members.items())}}
    members['server-gate-manifest.json'] = (json.dumps(manifest, sort_keys=True, indent=2)+'\n').encode()
    # Exclusive creation prevents replacement of an earlier reviewable package.
    with output.open('xb') as stream:
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(members.items()):
                info = zipfile.ZipInfo(name, date_time=(2026, 9, 9, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100600 << 16
                archive.writestr(info, data)
    return {'status': 'PACKAGE_CREATED', 'file': str(output), 'member_count': len(members),
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'server_executed': False,
            'production_changed': False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output), ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
