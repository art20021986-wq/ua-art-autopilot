'''Deterministic, idempotent merger for UA ART Shared Memory proposals.
Append-only writes to records.jsonl. Never touches production or CRM.
'''

import os
import json
import hashlib

import memory_guard as guard


def _proposal_hash(proposal):
    return hashlib.sha256(json.dumps(proposal, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def apply_proposal(proposal, base_dir):
    records_path = os.path.join(base_dir, 'records.jsonl')
    manifest_path = os.path.join(base_dir, 'manifest.json')
    manifest = guard.load_manifest(manifest_path)
    existing_records = guard.load_records(records_path)
    phash = _proposal_hash(proposal)
    applied = manifest.get('applied_proposals', [])
    if phash in applied:
        return {'result': 'ALREADY_APPLIED', 'memory_version': manifest['memory_version'], 'proposal_hash': phash, 'conflicts': []}
    validated_records, conflicts = guard.validate_proposal(proposal, manifest, existing_records)
    with open(records_path, 'a', encoding='utf-8') as handle:
        for record in validated_records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + '\n')
    new_hash = guard.sha256_file(records_path)
    manifest['previous_version'] = manifest['memory_version']
    manifest['memory_version'] = manifest['memory_version'] + 1
    manifest.setdefault('file_hashes', {})['records.jsonl'] = new_hash
    manifest['hashes_status'] = 'COMPUTED'
    applied.append(phash)
    manifest['applied_proposals'] = applied
    manifest['status'] = 'OK'
    guard.save_manifest(manifest_path, manifest)
    result = 'APPLIED_WITH_CONFLICTS' if conflicts else 'APPLIED'
    return {'result': result, 'memory_version': manifest['memory_version'], 'proposal_hash': phash, 'conflicts': conflicts}


if __name__ == '__main__':
    import sys
    base = os.path.dirname(os.path.abspath(__file__))
    with open(sys.argv[1], 'r', encoding='utf-8') as fh:
        proposal_obj = json.load(fh)
    outcome = apply_proposal(proposal_obj, base)
    print(json.dumps(outcome, indent=2))
