'''Deterministic context bundle builder for UA ART Shared Memory. Read-only.'''

import os
import json
import hashlib

import memory_guard as guard


def build_context(base_dir, subject=None):
    manifest_path = os.path.join(base_dir, 'manifest.json')
    records_path = os.path.join(base_dir, 'records.jsonl')
    manifest = guard.load_manifest(manifest_path)
    records = guard.load_records(records_path)
    view = guard.compute_active_view(records)
    selected = [r for r in records if view.get(r['record_id']) in ('ACTIVE', 'CONFLICT')]
    if subject:
        selected = [r for r in selected if r['subject'] == subject]

    def rank(record):
        try:
            return guard.AUTHORITY_LEVELS.index(record['authority'])
        except ValueError:
            return len(guard.AUTHORITY_LEVELS)

    selected_sorted = sorted(selected, key=lambda r: (rank(r), r['record_id']))
    enriched = [dict(r, computed_status=view[r['record_id']]) for r in selected_sorted]
    body = {
        'memory_version_read': manifest['memory_version'],
        'canonical_branch': manifest.get('canonical_branch'),
        'subject_filter': subject,
        'records': enriched,
    }
    serialized = json.dumps(body, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(serialized.encode('utf-8')).hexdigest()
    return {
        'MEMORY_VERSION_READ': manifest['memory_version'],
        'CONTEXT_BUNDLE_SHA256': digest,
        'bundle': body,
    }


if __name__ == '__main__':
    import sys
    base = os.path.dirname(os.path.abspath(__file__))
    subj = sys.argv[1] if len(sys.argv) > 1 else None
    print(json.dumps(build_context(base, subj), indent=2, sort_keys=True))
