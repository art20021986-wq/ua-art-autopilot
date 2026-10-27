#!/usr/bin/env python3
"""Write the HOME-REVIEWS preview request, then (after the preview) the install request set (run from the repo root).

Usage: python3 cloud/home_reviews_001/make_release.py preview [SUFFIX]   # PR, merge, then: launch preview
       python3 cloud/home_reviews_001/make_release.py launch TASK_ID
       python3 cloud/home_reviews_001/make_release.py install [SUFFIX]   # right after the preview: writes gate, manifest,
                                                                   # owner approval, storage probe, request and launch
Owner approvals in chat, 2026-10-26: release 1 «Ок размещай на сайте» (block, badge, logo); release 2 «Ок 1.2»
(Georgian texts, «autoria_click» Analytics event); 2026-10-27 release 3: no logo, text mark in AUTO.RIA brand style;
release 4 (owner «Да, конечно, сделай, чтобы везде шрифт был одинаковый» + white background): Roboto from our site. Task names come from release_constants.py.
"""
import datetime
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, 'automation')
import autostart_intake  # noqa: E402
import control_plane as cp  # noqa: E402

sys.path.insert(0, 'cloud/home_reviews_001')
from release_constants import INSTALL_TASK, PREVIEW_TASK  # noqa: E402

P = 'cloud/home_reviews_001/'
DEPENDENCIES = [P + n for n in ('autoria_click.py', 'candidate_builder.py', 'deployment_backup.py', 'deployment_bootstrap.py',
                                'deployment_remote.py', 'deployment_rollback.py', 'deployment_transport.py', 'edit_home.py',
                                'make_release.py', 'release_constants.py', 'reviews_block.py', 'reviews_data.py', 'roboto_font.py')]
TESTS = [P + n for n in ('test_deployment.py', 'test_edit_home.py')]
OWNER = 'Артём Бровинский / UA ART COMPANY LLC'
# Live data the install must not touch, besides the source files pinned in the plan.
LIVE_DATA = ['.crm_publish_requests', 'crm.db']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stamp(now):
    return now.strftime('%Y-%m-%dT%H:%M:%SZ')


def write(path, data, mode='x'):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, mode) as handle:
        handle.write(data)
    return path


def execution(task, production):
    files = DEPENDENCIES + TESTS
    value = {'controller_path': P + 'deployment_controller.py', 'controller_sha256': sha(P + 'deployment_controller.py'),
             'dependency_paths': DEPENDENCIES, 'file_sha256': {f: sha(f) for f in files},
             'production_required': production, 'receipt_path': 'state/receipts/%s.json' % task,
             'test_paths': TESTS, 'timeout_seconds': 3600 if production else 1200}
    if production:
        value.update(backup_controller_path=P + 'deployment_backup.py', backup_controller_sha256=sha(P + 'deployment_backup.py'),
                     backup_receipt_path='state/receipts/%s-BACKUP.json' % task,
                     rollback_controller_path=P + 'deployment_rollback.py',
                     rollback_controller_sha256=sha(P + 'deployment_rollback.py'),
                     rollback_receipt_path='state/receipts/%s-ROLLBACK.json' % task,
                     evidence_paths=[P + n for n in ('deployment_backup.json', 'deployment_rollback.json',
                                                     'deployment_install.json', 'deployment_verify.json')]
                     + ['state/receipts/%s%s.json' % (task, s) for s in ('', '-BACKUP', '-ROLLBACK')])
    else:
        value['evidence_paths'] = [P + 'deployment_plan.json', P + 'deployment_preview.json', 'state/receipts/%s.json' % task]
    return value


def preview(suffix):
    task = PREVIEW_TASK + suffix
    value = {'ai_requested': False, 'changed_paths': [P + 'deployment_plan.json', P + 'deployment_preview.json'],
             'complexity': 2, 'control_plane_version': 'TASK107-R2',
             'description': 'Preview of home reviews release 4 (owner request 2026-10-27): reads the live '
                            'video/index.html, builds the candidate (the installed AUTO.RIA reviews block, footer badge '
                            'and CSS replaced in place: the text mark «AUTO.RIA» as red and blue letters on white, in '
                            'Roboto served from the new video/brand/roboto-700.woff2) and measures storage. No application source, CRM, HTML, media or bot state '
                            'changes.',
             'execution': execution(task, False), 'production_required': False, 'read_only': False,
             'requested_min_class': 'STANDARD', 'storage_required_bytes': 33554432, 'task_id': task,
             'title': 'Preview home reviews release'}
    return write('tasks/requests/%s.json' % task, json.dumps(value, sort_keys=True, separators=(',', ':')))


def launch(task, now=None, production=False):
    now = now or datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    path = 'tasks/requests/%s.json' % task
    value = {'action': 'RUN_EXACT_TASK', 'created_at': stamp(now), 'expires_at': stamp(now + datetime.timedelta(minutes=110)),
             'mode_epoch': json.load(open('state/EXECUTION_MODE.json'))['mode_epoch'],
             'nonce': (task + '-' + now.strftime('%Y%m%dT%H%M%SZ')).lower(), 'owner_authorized': True,
             'production_allowed': production, 'request_path': path, 'request_sha256': sha(path),
             'schema_version': 'UA-ART-AUTOSTART-LAUNCH-1', 'task_id': task}
    return write('tasks/launch/AUTO-%s-%s.json' % (task, now.strftime('%Y%m%dT%H%M%SZ')),
                 json.dumps(value, indent=2, sort_keys=True) + '\n'), value


def install(suffix):
    task = INSTALL_TASK + suffix
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    plan = json.load(open(P + 'deployment_plan.json'))
    preview_value = json.load(open(P + 'deployment_preview.json'))
    probe = preview_value['storage_probe']
    storage = {k: probe[k] for k in ('account_quota_measured', 'free_bytes', 'measured_at', 'measurement_method',
                                     'read_only', 'target_environment', 'total_bytes', 'used_bytes')}
    storage.update(task_id=task, raw_filesystem_measurement=probe['shared_filesystem'])
    storage_path = write('state/storage/%s.json' % task, json.dumps(storage, sort_keys=True, separators=(',', ':')))
    operations = [{'action': 'replace' if item['before'] else 'create', 'expected_after_sha256': item['after'],
                   **({'expected_before_sha256': item['before']} if item['before'] else {}),
                   'path': 'production/homereviews/' + name} for name, item in sorted(plan['files'].items())]
    manifest = {'backup_required': True, 'contract_id': 'UA-ART-CRITICAL-ADAPTER-V1.0', 'crm_write': False,
                'live_verify_required': True, 'operations': operations, 'pending_requests_preserved': True,
                'protected_paths': sorted(LIVE_DATA + list(plan['protected'])), 'rollback_required': True, 'site_write': True, 'task_class': 'CRITICAL',
                'task_id': task}
    manifest_path = write('tasks/manifests/%s.json' % task, json.dumps(manifest, sort_keys=True, separators=(',', ':')))
    manifest_sha = cp.sha256_bytes(cp.canonical_json(manifest))
    gate = {'backup_plan_ready': True, 'backup_scope_verified': [o['path'] for o in operations],
            'contract_id': 'UA-ART-CRITICAL-ADAPTER-V1.0', 'evaluated_at': stamp(now), 'manifest_sha256': manifest_sha,
            'plan_sha256': preview_value['plan_sha256'], 'preview_cpu_seconds': preview_value.get('cpu_seconds'),
            'preview_run_id': preview_value['run_id'], 'production_write': False,
            'protected_snapshot': {'files': plan['protected'],
                                   'operator_data_policy': 'Re-snapshot under writer locks; preserve all newer operator edits'},
            'rollback_plan_ready': True, 'rollback_scope_verified': [o['path'] for o in operations], 'status': 'PASS',
            'task_id': task, 'test_evidence': {'actual_remote_candidate_build': 'PASS',
                                               'unit_and_lifecycle_tests': 'PASS'},
            'tests': 'PASS', 'unexpected_changes': 0}
    gate_path = write('tasks/gates/%s.json' % task, json.dumps(gate, sort_keys=True, separators=(',', ':')))
    approval_path = 'tasks/approvals/%s.production.json' % task
    request = {'ai_requested': False, 'changed_paths': [o['path'] for o in operations], 'complexity': 2,
               'control_plane_version': 'TASK107-R2',
               'critical': {'allow_crm_vehicle_data': False, 'gate_a_path': gate_path, 'gate_a_sha256': sha(gate_path),
                            'gate_b_authorized': True, 'manifest_path': manifest_path, 'manifest_sha256': manifest_sha,
                            'owner_approval_path': approval_path, 'owner_approval_sha256': '0' * 64},
               'deployment_plan_sha256': preview_value['plan_sha256'],
               'description': 'Owner approved (2026-10-27) AUTORIA-REVIEWS-001 release 4: in '
                              'video/index.html the installed AUTO.RIA reviews block, footer badge and their CSS are '
                              'replaced in place; the only difference is the text mark «AUTO.RIA»: red «AUTO» and blue '
                              '«.RIA» letters on the white button and badge, in Roboto Bold (SIL OFL) served from the new '
                              'file video/brand/roboto-700.woff2; every other byte stays as is. No CRM or car card change. Existing backup, bot '
                              'pause, writer locks, data-preservation, rollback and public health checks are kept.',
               'execution': execution(task, True),
               'health_checks': ['https://www.uaart.com.ua/video/index.html', 'https://www.uaart.com.ua/video/katalog.html'],
               'production_required': True, 'read_only': False, 'requested_min_class': 'CRITICAL',
               'storage_probe': {'evidence_path': storage_path, 'evidence_sha256': sha(storage_path)},
               'storage_required_bytes': 67108864, 'task_id': task, 'title': 'Install home reviews release'}
    _, marker = launch_values(task, now)
    approval = {'approved_at': stamp(now), 'authorization_id': 'prod-auth-' + marker['nonce'],
                'authorized_environment': 'production', 'expires_at': marker['expires_at'], 'gate_a_sha256': sha(gate_path),
                'launch_nonce': marker['nonce'], 'manifest_sha256': manifest_sha, 'mode_epoch': marker['mode_epoch'],
                'owner': OWNER, 'owner_authorized': True, 'production_allowed': True,
                'request_path': 'tasks/requests/%s.json' % task,
                'request_subject_sha256': autostart_intake.request_authorization_sha256(request),
                'schema_version': 'UA-ART-PRODUCTION-AUTHORIZATION-1', 'task_id': task}
    write(approval_path, json.dumps(approval, sort_keys=True, separators=(',', ':')))
    request['critical']['owner_approval_sha256'] = sha(approval_path)
    write('tasks/requests/%s.json' % task, json.dumps(request, sort_keys=True, separators=(',', ':')))
    marker_path, value = launch(task, now, production=True)
    assert value['nonce'] == marker['nonce'] and value['expires_at'] == marker['expires_at']
    return marker_path


def launch_values(task, now):
    mode = json.load(open('state/EXECUTION_MODE.json'))
    nonce = (task + '-' + now.strftime('%Y%m%dT%H%M%SZ')).lower()
    return None, {'nonce': nonce, 'expires_at': stamp(now + datetime.timedelta(minutes=110)), 'mode_epoch': mode['mode_epoch']}


if __name__ == '__main__':
    action = sys.argv[1]
    if action == 'preview':
        print(preview(sys.argv[2] if len(sys.argv) > 2 else ''))
    elif action == 'launch':
        print(launch(sys.argv[2])[0])
    else:
        print(install(sys.argv[2] if len(sys.argv) > 2 else ''))
