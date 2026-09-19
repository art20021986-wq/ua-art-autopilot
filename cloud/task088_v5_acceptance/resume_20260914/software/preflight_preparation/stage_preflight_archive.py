#!/usr/bin/env python3
"""Stage one exact reviewed archive; never execute preflight or write live files."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import zipfile

ROOT = Path('/home/Carix/autopilot_inbox/cloud')
CONTRACT = 'TASK088-PRICE-SYNC-READONLY-PREFLIGHT-5'
CODE_NAMES = frozenset({
    'uaart_market_prices.py', 'uaart_price_sync_outbox.py',
    'uaart_price_sync_runtime.py', 'uaart_price_sync_binding.py',
    'uaart_price_sync_confirmation.py', 'uaart_price_control_reader.py',
    'preflight.py', 'install_package.py', 'patch_cars_ui.py', 'patch_guard.py',
    'patch_yadro.py', 'patch_stranica.py', 'patch_catalog_design_guard.py',
    'patch_stage_catalog_sync.py', 'initial_html_prices.py',
    'owner_policy.py', 'price_publication.py',
})
MEMBERS = CODE_NAMES | {'preflight_bundle.json'}
MAX_ARCHIVE = 4 * 1024 * 1024
MAX_MEMBER = 2 * 1024 * 1024
MAX_UNPACKED = 16 * 1024 * 1024
HASH = re.compile(r'[0-9a-f]{64}')


class StagingError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise StagingError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def open_directory(path):
    """Walk every ancestor using openat and O_NOFOLLOW, including the leaf."""
    require(path.is_absolute() and '..' not in path.parts,
            'ABSOLUTE_NONTRAVERSING_PATH_REQUIRED')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open('/', flags)
    try:
        for part in path.parts[1:]:
            next_descriptor = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def read_archive(path):
    require(path.is_absolute() and path.name not in ('', '.', '..'),
            'ABSOLUTE_ARCHIVE_PATH_REQUIRED')
    parent = open_directory(path.parent)
    descriptor = None
    try:
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=parent)
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= MAX_ARCHIVE,
                'BOUNDED_REGULAR_ARCHIVE_REQUIRED')
        with os.fdopen(descriptor, 'rb', closefd=False) as handle:
            raw = handle.read(MAX_ARCHIVE + 1)
        after = os.fstat(descriptor)
        current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        require(len(raw) == before.st_size and all(
            getattr(before, key) == getattr(after, key) == getattr(current, key)
            for key in ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns')),
            'ARCHIVE_CHANGED_DURING_READ')
        return raw
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'DUPLICATE_JSON_KEY')
        value[key] = item
    return value


def fresh(value, now, label):
    require(isinstance(value, str), label + '_TIME_REQUIRED')
    instant = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(instant.tzinfo is not None and
            0 <= (now - instant).total_seconds() <= 1800,
            label + '_STALE_OR_FUTURE')


def validate_archive(raw, archive_sha, bundle_sha, now):
    """Validate everything in memory before any destination is created."""
    require(HASH.fullmatch(archive_sha) and HASH.fullmatch(bundle_sha),
            'EXACT_FULL_ARCHIVE_AND_BUNDLE_HASHES_REQUIRED')
    require(0 < len(raw) <= MAX_ARCHIVE, 'ARCHIVE_SIZE_LIMIT')
    require(digest(raw) == archive_sha, 'ARCHIVE_SHA256_MISMATCH')
    with zipfile.ZipFile(io.BytesIO(raw)) as packed:
        infos = packed.infolist()
        names = [info.filename for info in infos]
        require(len(names) == len(set(names)) == 18 and set(names) == MEMBERS,
                'EXACT_EIGHTEEN_LEAF_MEMBERS_REQUIRED')
        require(sum(info.file_size for info in infos) <= MAX_UNPACKED,
                'UNPACKED_SIZE_LIMIT')
        for info in infos:
            kind = stat.S_IFMT(info.external_attr >> 16)
            require(not info.is_dir() and '/' not in info.filename and
                    '\\' not in info.filename and kind in (0, stat.S_IFREG) and
                    not (info.flag_bits & 1), 'REGULAR_UNENCRYPTED_LEAF_REQUIRED')
            require(0 < info.file_size <= MAX_MEMBER and
                    info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                    'MEMBER_SIZE_OR_COMPRESSION_INVALID')
        payload = {info.filename: packed.read(info) for info in infos}
        require(all(len(payload[info.filename]) == info.file_size for info in infos),
                'MEMBER_SIZE_MISMATCH')  # Each read also checks its CRC.
    bundle_raw = payload['preflight_bundle.json']
    require(digest(bundle_raw) == bundle_sha, 'BUNDLE_SHA256_MISMATCH')
    bundle = json.loads(bundle_raw, object_pairs_hook=unique_object)
    require(isinstance(bundle, dict) and bundle.get('contract') == CONTRACT,
            'BUNDLE_CONTRACT_MISMATCH')
    require(bundle.get('authority_status') == 'READONLY_PREFLIGHT_NOT_A_PRODUCTION_GATE',
            'READONLY_BUNDLE_AUTHORITY_REQUIRED')
    pins = bundle.get('package_sha256')
    require(isinstance(pins, dict) and set(pins) == CODE_NAMES,
            'EXACT_CODE_HASH_SET_REQUIRED')
    for name in sorted(CODE_NAMES):
        require(isinstance(pins[name], str) and HASH.fullmatch(pins[name]) and
                digest(payload[name]) == pins[name], 'CODE_SHA256_MISMATCH:' + name)
        compile(payload[name], name, 'exec')  # No module imports or execution.
    fresh(bundle.get('created_at'), now, 'BUNDLE')
    quota = bundle.get('quota_evidence')
    require(isinstance(quota, dict) and
            quota.get('source') == 'PYTHONANYWHERE_AUTHENTICATED_ACCOUNT' and
            quota.get('account') == 'Carix' and
            type(quota.get('used_bytes')) is int and
            type(quota.get('limit_bytes')) is int and
            0 <= quota['used_bytes'] < quota['limit_bytes'],
            'AUTHENTICATED_ACCOUNT_QUOTA_REQUIRED')
    fresh(quota.get('observed_at'), now, 'QUOTA')
    require(sum(map(len, payload.values())) + 65536 <= quota['limit_bytes'] - quota['used_bytes'],
            'ACCOUNT_SPACE_INSUFFICIENT_FOR_STAGING')
    return payload, bundle


def stage(archive, expected_archive_sha256, expected_bundle_sha256, staging_id):
    require(re.fullmatch(r'[A-Za-z0-9_-]{8,90}', staging_id),
            'FRESH_STAGING_ID_REQUIRED')
    raw = read_archive(Path(archive))
    payload, bundle = validate_archive(raw, expected_archive_sha256,
                                       expected_bundle_sha256, datetime.now(timezone.utc))
    parent = open_directory(ROOT)  # Existing approved parent; never mkdir parents.
    destination = 'task088_price_sync_' + staging_id
    target = ROOT / destination
    directory = None
    created = False
    try:
        try:
            os.stat(destination, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise StagingError('DESTINATION_ALREADY_EXISTS')
        # Repeat age checks immediately before the first filesystem mutation.
        now = datetime.now(timezone.utc)
        fresh(bundle['created_at'], now, 'BUNDLE')
        fresh(bundle['quota_evidence']['observed_at'], now, 'QUOTA')
        free = os.fstatvfs(parent)
        require(sum(map(len, payload.values())) + 65536 <= free.f_bavail * free.f_frsize,
                'FILESYSTEM_SPACE_INSUFFICIENT_FOR_STAGING')
        os.mkdir(destination, mode=0o700, dir_fd=parent)
        created = True
        directory = os.open(destination, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=parent)
        os.fchmod(directory, 0o700)
        for name, data in sorted(payload.items()):
            descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=directory)
            with os.fdopen(descriptor, 'wb') as handle:
                os.fchmod(handle.fileno(), 0o600)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        require(set(os.listdir(directory)) == MEMBERS, 'STAGED_MEMBER_SET_MISMATCH')
        for name, expected in sorted(payload.items()):
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 dir_fd=directory)
            with os.fdopen(descriptor, 'rb') as handle:
                info = os.fstat(handle.fileno())
                require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600 and
                        info.st_size == len(expected) and handle.read(MAX_MEMBER + 1) == expected,
                        'STAGED_FILE_READBACK_MISMATCH:' + name)
        os.fsync(directory)
        os.fsync(parent)
        on_path = os.stat(destination, dir_fd=parent, follow_symlinks=False)
        opened = os.fstat(directory)
        require((on_path.st_dev, on_path.st_ino) == (opened.st_dev, opened.st_ino) and
                stat.S_IMODE(opened.st_mode) == 0o700, 'STAGING_DIRECTORY_CHANGED')
    except BaseException:
        if created:
            print(json.dumps({'status': 'STAGING_FAILED', 'private_partial_directory': str(target),
                              'preflight_executed': False, 'production_changed': False}), file=sys.stderr)
        raise
    finally:
        if directory is not None:
            os.close(directory)
        os.close(parent)
    return {
        'status': 'STAGED_READONLY_PREFLIGHT', 'directory': str(target), 'files': len(payload),
        'archive_sha256': expected_archive_sha256, 'bundle_sha256': expected_bundle_sha256,
        'package_sha256': bundle['package_sha256'], 'full_readback': 'PASS',
        'production_changed': False, 'gate_b_created': False, 'preflight_executed': False,
        'next_action_requires_new_process': True,
        'preflight_argv': [sys.executable, '-I', '-B', str(target / 'preflight.py'),
                          '--output-id', 'preflight-' + staging_id.replace('_', '-'),
                          '--expected-bundle-sha256', expected_bundle_sha256],
        'preflight_expected_authority_result': 'BLOCKED_CANONICAL_CONTROL_BRIDGE_NOT_RUN',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True)
    parser.add_argument('--expected-archive-sha256', required=True)
    parser.add_argument('--expected-bundle-sha256', required=True)
    parser.add_argument('--staging-id', required=True)
    args = parser.parse_args()
    result = stage(args.archive, args.expected_archive_sha256,
                   args.expected_bundle_sha256, args.staging_id)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))


if __name__ == '__main__':
    main()
