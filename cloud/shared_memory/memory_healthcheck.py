'''Healthcheck for UA ART Shared Memory canonical state. Read-only.'''

import os
import json

import memory_guard as guard


def run_healthcheck(base_dir):
    manifest_path = os.path.join(base_dir, 'manifest.json')
    records_path = os.path.join(base_dir, 'records.jsonl')
    issues = []
    manifest = guard.load_manifest(manifest_path)
    records = guard.load_records(records_path)
    ids = [r.get('record_id') for r in records]
    if len(ids) != len(set(ids)):
        issues.append('DUPLICATE_RECORD_ID')
    for record in records:
        try:
            guard.validate_record_schema(record)
        except guard.MemoryGuardError:
            issues.append('INVALID_RECORD_SCHEMA:' + str(record.get('record_id', 'UNKNOWN')))
            continue
        if record['record_class'] == 'OWNER_DIRECTIVE' and not record.get('immutable'):
            issues.append('OWNER_DIRECTIVE_NOT_IMMUTABLE:' + record['record_id'])
        if guard.scan_for_secrets(json.dumps(record)):
            issues.append('SECRET_LIKE_CONTENT:' + record['record_id'])
    managed_files = manifest.get('managed_files')
    file_hashes = manifest.get('file_hashes')
    if manifest.get('hashes_status') != 'COMPUTED':
        issues.append('HASHES_NOT_COMPUTED')
    if not isinstance(managed_files, list) or not managed_files:
        issues.append('MANAGED_FILES_INVALID')
        managed_files = []
    if not isinstance(file_hashes, dict):
        issues.append('FILE_HASHES_INVALID')
        file_hashes = {}
    if set(file_hashes) != set(managed_files):
        issues.append('MANAGED_FILE_HASH_SET_MISMATCH')
    root = os.path.realpath(base_dir)
    for relative_path in managed_files:
        recorded_hash = file_hashes.get(relative_path)
        if not isinstance(recorded_hash, str) or len(recorded_hash) != 64:
            issues.append('MANAGED_FILE_HASH_MISSING:' + str(relative_path))
            continue
        if (not isinstance(relative_path, str) or os.path.isabs(relative_path)
                or relative_path.startswith('~') or '\\' in relative_path):
            issues.append('MANAGED_FILE_PATH_UNSAFE:' + str(relative_path))
            continue
        normalized = os.path.normpath(relative_path)
        full = os.path.realpath(os.path.join(root, normalized))
        if normalized == '..' or normalized.startswith('../') or os.path.commonpath((root, full)) != root:
            issues.append('MANAGED_FILE_PATH_UNSAFE:' + str(relative_path))
            continue
        lexical_path = os.path.join(root, normalized)
        if os.path.islink(lexical_path) or not os.path.isfile(full):
            issues.append('MANAGED_FILE_MISSING_OR_SYMLINK:' + str(relative_path))
            continue
        if guard.sha256_file(full) != recorded_hash:
            issues.append('MANAGED_FILE_HASH_MISMATCH:' + str(relative_path))
    view = guard.compute_active_view(records)
    conflicts = sorted([rid for rid, status in view.items() if status == 'CONFLICT'])
    health = 'PASS' if not issues else 'FAIL'
    return {
        'MEMORY_HEALTH': health,
        'issues': issues,
        'conflicts': conflicts,
        'memory_version': manifest['memory_version'],
    }


if __name__ == '__main__':
    base = os.path.dirname(os.path.abspath(__file__))
    print(json.dumps(run_healthcheck(base), indent=2, sort_keys=True))
