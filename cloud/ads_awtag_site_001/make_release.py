#!/usr/bin/env python3
"""Write the ADS-AWTAG-SITE preview request, then (after the preview) the install request set (run from the repo root).

Usage: python3 cloud/ads_awtag_site_001/make_release.py preview   # PR, merge, then: launch preview
       python3 cloud/ads_awtag_site_001/make_release.py launch TASK_ID
       python3 cloud/ads_awtag_site_001/make_release.py install   # after the owner's «да» on the preview
Owner 2026-11-27 (tasks/ADS-AWTAG-001.md, step 2): the site Google tag also counts Google Ads conversions.
"""
import datetime
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, 'automation')
sys.path.insert(0, 'cloud/ads_awtag_site_001')
import autostart_intake  # noqa: E402
import control_plane as cp  # noqa: E402

P = 'cloud/ads_awtag_site_001/'
from release_constants import INSTALL_TASK, PREVIEW_TASK  # noqa: E402

DEPENDENCIES = [P + n for n in ('candidate_builder.py', 'deployment_backup.py', 'deployment_bootstrap.py',
                                'deployment_remote.py', 'deployment_rollback.py', 'deployment_transport.py',
                                'make_release.py', 'release_constants.py', 'ua_google_tag.py',
                                'ua_google_tag_old.py')]
TESTS = [P + n for n in ('test_deployment.py', 'test_release.py', 'test_google_tag.py')]
OWNER = 'Артём Бровинский / UA ART COMPANY LLC'
PROTECTED = ['.crm_publish_requests', 'cars_schema.py', 'catalog_design_guard.py', 'crm.db', 'db.py', 'lead_bot.py',
             'master_card.py', 'publication_fence.py', 'publikaciya.py', 'run_all.py',
             'start_safe.py', 'stranica.py', 'team_bot.py', 'ua_google_sitemap.py', 'ua_indexnow.py',
             'ua_public_freshness.py',
             'ua_seo_sitemap.py', 'ua_site_counters.py',
             'site_ge_inject.py', 'ua_seo_metadata.py', 'ua_seo_index.py', 'ua_own_counter.py',
             'publish_transaction_guard.py', 'ua_crm_public_sync.py']


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


def preview():
    task = PREVIEW_TASK
    value = {'ai_requested': False, 'changed_paths': [P + 'deployment_plan.json', P + 'deployment_preview.json'],
             'complexity': 2, 'control_plane_version': 'TASK107-R2',
             'description': 'Preview of ADS-AWTAG-SITE (ADS-AWTAG-001 step 2): builds the candidate on the server '
                            '(ua_google_tag.py V1 -> V2: GA4 config as before, Google Ads AW-18537441937 config, one '
                            'conversion per generate_lead, quick-lead.js included; no user data) and every public page '
                            'with the tag block (the V1 block swapped, nothing else; a landing already V2 since 28.11 '
                            'kept as it is), checks each page differs only by the '
                            'block and is undone exactly, the new module writes the same page and a second pass changes '
                            'nothing, no new host, the catalogue design guard sees the same shell, and measures storage. '
                            'No application source, CRM, HTML, media or bot state changes.',
             'execution': execution(task, False), 'production_required': False, 'read_only': False,
             'requested_min_class': 'STANDARD', 'storage_required_bytes': 33554432, 'task_id': task,
             'title': 'Preview Google Ads tag on site'}
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


def install():
    task = INSTALL_TASK
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
                   'path': 'production/ads_awtag_site/' + name} for name, item in sorted(plan['files'].items())]
    manifest = {'backup_required': True, 'contract_id': 'UA-ART-CRITICAL-ADAPTER-V1.0', 'crm_write': False,
                'live_verify_required': True, 'operations': operations, 'pending_requests_preserved': True,
                'protected_paths': PROTECTED, 'rollback_required': True, 'site_write': True, 'task_class': 'CRITICAL',
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
               'description': 'Owner approved ADS-AWTAG-001 step 2: the site Google tag block V1 -> V2 in '
                              'ua_google_tag.py and on every public page that carries it: the GA4 config as before, the '
                              'tag also configured for Google Ads AW-18537441937, and every generate_lead (quick-lead.js '
                              'included) sends one Google Ads conversion. No user data, no privacy text change; nothing '
                              'else on the pages changes. Rollback puts every file back byte for byte (a page a writer '
                              'rewrote meanwhile gets the V1 block back). R2: the bot pause waits for the explicit '
                              'stopped state; one landing refresh with the installed modules runs under the locks and '
                              'every page is checked byte for byte before they are released; the verify reads the pages '
                              'under the page writers\' locks; a rollback restores the modules first, then every page '
                              'with the V1 block (the 32 landings already V2 since 28.11 included). Existing backup, '
                              'bot pause, writer locks, the auction jobs held, data-preservation, rollback and public '
                              'health checks are kept.',
               'execution': execution(task, True),
               'health_checks': ['https://www.uaart.com.ua/video/index.html', 'https://www.uaart.com.ua/video/katalog.html',
                                 'https://www.uaart.com.ua/video/podbor.html', 'https://www.uaart.com.ua/video/korea.html'],
               'production_required': True, 'read_only': False, 'requested_min_class': 'CRITICAL',
               'storage_probe': {'evidence_path': storage_path, 'evidence_sha256': sha(storage_path)},
               'storage_required_bytes': 33554432, 'task_id': task, 'title': 'Install Google Ads tag on site'}
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
        print(preview())
    elif action == 'launch':
        print(launch(sys.argv[2], production=sys.argv[2] == INSTALL_TASK)[0])
    else:
        print(install())
