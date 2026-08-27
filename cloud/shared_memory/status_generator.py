'''Generated status view for UA ART Shared Memory. Derived only from canonical records.'''

import os
import json
import datetime

import memory_guard as guard


def generate_status(base_dir):
    manifest_path = os.path.join(base_dir, 'manifest.json')
    records_path = os.path.join(base_dir, 'records.jsonl')
    manifest = guard.load_manifest(manifest_path)
    records = guard.load_records(records_path)
    view = guard.compute_active_view(records)
    counts = {}
    for record in records:
        status = view[record['record_id']]
        by_class = counts.setdefault(record['record_class'], {})
        by_class[status] = by_class.get(status, 0) + 1
    ua0009_records = [r for r in records if r['subject'] == 'UA-0009' and view[r['record_id']] in ('ACTIVE', 'CONFLICT')]
    ua0009_approvals = [r for r in ua0009_records if r['record_class'] == 'APPROVAL' and r.get('evidence')]
    task015_acceptance = [
        r for r in records
        if r['subject'] == 'TASK_015_ACCEPTANCE'
        and r['record_class'] == 'RESULT'
        and r.get('evidence')
        and view[r['record_id']] == 'ACTIVE'
    ]
    memory_accepted = bool(task015_acceptance)
    conflicts_present = any(status == 'CONFLICT' for status in view.values())
    return {
        'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z'),
        'memory_version': manifest['memory_version'],
        'canonical_branch': manifest.get('canonical_branch'),
        'record_counts': counts,
        'conflicts_present': conflicts_present,
        'ua0009_safe_to_publish': 'YES' if ua0009_approvals else 'NO',
        'production_write': 'NO',
        'crm_write': 'NO',
        'task_015_status': 'CONTROLLER_VERIFIED_ACCEPTED' if memory_accepted else 'COMPLETED_PENDING_CONTROLLER_VERIFICATION',
        'task_014_017_dependency': 'UNBLOCKED_AFTER_MEMORY_ACCEPTANCE' if memory_accepted else 'BLOCKED_UNTIL_MEMORY_ACCEPTANCE',
    }


def write_status(base_dir):
    status = generate_status(base_dir)
    out_path = os.path.join(base_dir, 'state', 'current_status.json')
    with open(out_path, 'w', encoding='utf-8') as handle:
        json.dump(status, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write('\n')
    return status


if __name__ == '__main__':
    base = os.path.dirname(os.path.abspath(__file__))
    print(json.dumps(write_status(base), indent=2, sort_keys=True))
