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
    ids = [r['record_id'] for r in records]
    if len(ids) != len(set(ids)):
        issues.append('DUPLICATE_RECORD_ID')
    for record in records:
        if record['record_class'] == 'OWNER_DIRECTIVE' and not record.get('immutable'):
            issues.append('OWNER_DIRECTIVE_NOT_IMMUTABLE:' + record['record_id'])
        if guard.scan_for_secrets(json.dumps(record)):
            issues.append('SECRET_LIKE_CONTENT:' + record['record_id'])
    recorded_hash = manifest.get('file_hashes', {}).get('records.jsonl')
    if recorded_hash:
        actual_hash = guard.sha256_file(records_path)
        if actual_hash != recorded_hash:
            issues.append('RECORDS_HASH_MISMATCH')
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
