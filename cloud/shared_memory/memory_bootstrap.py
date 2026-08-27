'''Idempotent bootstrap for UA ART Shared Memory.
Computes and persists managed-file hashes. No network access.
'''

import os
import json

import memory_guard as guard


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
    file_hashes = manifest.setdefault('file_hashes', {})
    file_hashes['records.jsonl'] = guard.sha256_file(records_path)
    for extra in ('schemas/record.schema.json', 'schemas/proposal.schema.json'):
        full = os.path.join(base_dir, extra)
        if os.path.exists(full):
            file_hashes[extra] = guard.sha256_file(full)
    manifest['hashes_status'] = 'COMPUTED'
    if manifest.get('status') == 'SEEDED':
        manifest['status'] = 'BOOTSTRAPPED'
    guard.save_manifest(manifest_path, manifest)
    return manifest


if __name__ == '__main__':
    base = os.path.dirname(os.path.abspath(__file__))
    result = bootstrap(base)
    print(json.dumps(result, indent=2, sort_keys=True))
