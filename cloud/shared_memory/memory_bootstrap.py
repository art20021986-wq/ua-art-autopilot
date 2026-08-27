'''Idempotent bootstrap for UA ART Shared Memory.
Computes and persists managed-file hashes. No network access.
'''

import os
import json

import memory_guard as guard


def _resolve_managed_file(base_dir, relative_path):
    if not isinstance(relative_path, str) or not relative_path:
        raise ValueError('Managed file path must be a non-empty string')
    if os.path.isabs(relative_path) or relative_path.startswith('~') or '\\' in relative_path:
        raise ValueError('Unsafe managed file path: ' + relative_path)
    normalized = os.path.normpath(relative_path)
    if normalized == '..' or normalized.startswith('../'):
        raise ValueError('Unsafe managed file path: ' + relative_path)
    root = os.path.realpath(base_dir)
    full = os.path.realpath(os.path.join(root, normalized))
    if os.path.commonpath((root, full)) != root:
        raise ValueError('Managed file escapes memory root: ' + relative_path)
    if os.path.islink(os.path.join(root, normalized)):
        raise ValueError('Managed file cannot be a symlink: ' + relative_path)
    if not os.path.isfile(full):
        raise FileNotFoundError('Managed file missing: ' + relative_path)
    return full


def bootstrap(base_dir):
    manifest_path = os.path.join(base_dir, 'manifest.json')
    records_path = os.path.join(base_dir, 'records.jsonl')
    if not os.path.exists(manifest_path):
        raise FileNotFoundError('manifest.json missing, cannot bootstrap: ' + manifest_path)
    if not os.path.exists(records_path):
        raise FileNotFoundError('records.jsonl missing, cannot bootstrap: ' + records_path)
    manifest = guard.load_manifest(manifest_path)
    records = guard.load_records(records_path)
    ids = [r['record_id'] for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate record_id found in records.jsonl')
    for record in records:
        guard.validate_record_schema(record)
    managed_files = manifest.get('managed_files')
    if not isinstance(managed_files, list) or not managed_files:
        raise ValueError('manifest managed_files must be a non-empty list')
    file_hashes = {}
    for relative_path in managed_files:
        full = _resolve_managed_file(base_dir, relative_path)
        file_hashes[relative_path] = guard.sha256_file(full)
    manifest['file_hashes'] = file_hashes
    manifest['hashes_status'] = 'COMPUTED'
    if manifest.get('status') == 'SEEDED':
        manifest['status'] = 'BOOTSTRAPPED'
    guard.save_manifest(manifest_path, manifest)
    return manifest


if __name__ == '__main__':
    base = os.path.dirname(os.path.abspath(__file__))
    result = bootstrap(base)
    print(json.dumps(result, indent=2, sort_keys=True))
