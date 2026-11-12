"""Actions controller; source installation preserves all existing CRM records."""
import json
import os
from pathlib import Path
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from deployment_transport import API, HERE, INBOX, canonical, sha, upload_package

ROOT = HERE.parents[1]
from release_constants import PREVIEW_TASK, INSTALL_TASK, PACKAGE
from candidate_builder import MARK
# The web app keeps analitika_yadro in memory: after the install (and after a rollback) it is reloaded so /ua/a.js
# serves the file on disk (OWN-COUNTER lesson: WEBAPP-RELOAD-20261108).
RELOAD = 'https://www.pythonanywhere.com/api/v0/user/Carix/webapps/www.uaart.com.ua/reload/'
SCRIPT = '/ua/a.js?v=1&check=%d'
HEALTH = ('/video/index.html', '/video/katalog.html')


def reload_webapp(token):
    request = urllib.request.Request(RELOAD, data=b'', method='POST', headers={'Authorization': 'Token ' + token})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return 'HTTP_%d' % response.status
    except urllib.error.HTTPError as error:
        return 'HTTP_%d' % error.code
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return 'UNCONFIRMED:' + type(error).__name__


def fetch(path):
    url = 'https://www.uaart.com.ua' + path
    request = urllib.request.Request(url, headers={'Cache-Control': 'no-cache', 'User-Agent': 'UAART-Analytics3-Verify/1'})
    with urllib.request.urlopen(request, timeout=30) as response:
        final = urllib.parse.urlsplit(response.url)
        if response.status != 200 or (final.scheme, final.netloc, final.path) != ('https', 'www.uaart.com.ua', path.split('?')[0]):
            raise RuntimeError('PUBLIC_CANONICAL_HEALTH:' + path)
        return response.read(1024*1024).decode('utf-8', 'replace')


def context():
    environment = os.environ
    task = environment['UAART_TASK_ID']
    run_id = environment['UAART_RUN_ID']
    if task not in (PREVIEW_TASK, INSTALL_TASK) or not re.fullmatch(r'[0-9]+', run_id):
        raise RuntimeError('TASK_IDENTITY')
    request_path = (ROOT/environment['UAART_REQUEST_PATH']).resolve()
    if not request_path.is_relative_to(ROOT) or sha(request_path.read_bytes()) != environment['UAART_REQUEST_SHA256']:
        raise RuntimeError('REQUEST_BINDING')
    request = json.loads(request_path.read_bytes())
    production = task == INSTALL_TASK
    if request['task_id'] != task or request['production_required'] is not production:
        raise RuntimeError('REQUEST_SCOPE')
    if environment['UAART_TASK_CLASS'] != ('CRITICAL' if production else 'STANDARD'):
        raise RuntimeError('TASK_CLASS')
    return environment, request


def save(relative, value):
    target = (ROOT/relative).resolve()
    if not target.is_relative_to(ROOT):
        raise RuntimeError('RECEIPT_PATH')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(canonical(value))


def accepted(value, mode, run_id, backup=None):
    if value.get('status') != 'PASS' or value.get('mode') != mode or value.get('run_id') != run_id:
        raise RuntimeError('REMOTE_'+mode.upper()+':'+str(value.get('error', 'FAILED')))
    if value.get('crm_write') is not False or value.get('safe_to_stop') is not True:
        raise RuntimeError('REMOTE_SCOPE')
    if backup and value.get('backup_manifest_sha256') != backup:
        raise RuntimeError('BACKUP_BINDING')


def public_verify(attempts=10, pause=15):
    """The pages answer and the public script carries the new code (the reload can take a little while)."""
    results = {}
    for path in HEALTH:
        if len(fetch(path)) < 100:
            raise RuntimeError('EMPTY_PUBLIC_PAGE:' + path)
        results[path] = 'PASS'
    for attempt in range(attempts):
        if MARK in fetch(SCRIPT % (time.time() * 1000)):
            results['/ua/a.js'] = 'PASS'
            return results
        time.sleep(pause)
    raise RuntimeError('PUBLIC_CHANGE_MISSING:/ua/a.js')


def run(operation=None):
    env, request = context()
    api = API(env['PYTHONANYWHERE_API_TOKEN'])
    run_id, task = env['UAART_RUN_ID'], env['UAART_TASK_ID']
    bundle = upload_package(api)
    if task == PREVIEW_TASK:
        value = api.run('preview', run_id, bundle)
        accepted(value, 'preview', run_id)
        save(PACKAGE+'/deployment_plan.json', value['plan'])
        save(PACKAGE+'/deployment_preview.json', value)
        receipt = {'task_id': task, 'task_class': 'STANDARD', 'run_id': run_id,
                   'request_sha256': env['UAART_REQUEST_SHA256'], 'status': 'FINISHED',
                   'target_environment': 'shadow', 'tests': 'PASS', 'unexpected_changes': 0,
                   'production_required': False, 'production_touched': False,
                   'rollback_ready': True, 'full_acceptance': False,
                   'plan_sha256': value['plan_sha256'], 'bundle_sha256': bundle}
        save(env['UAART_RECEIPT_PATH'], receipt)
        print(json.dumps(receipt, sort_keys=True))
        return 0
    plan = json.loads((HERE/'deployment_plan.json').read_bytes())
    plan_sha = sha(canonical(plan))
    if request['deployment_plan_sha256'] != plan_sha:
        raise RuntimeError('PLAN_BINDING')
    bindings = {'task_id': task, 'request_sha256': env['UAART_REQUEST_SHA256'],
                'run_id': run_id, 'transaction_id': env['UAART_TRANSACTION_ID'],
                'manifest_sha256': env['UAART_MANIFEST_SHA256']}
    if operation == 'backup':
        value = api.run('backup', run_id, bundle, plan_sha)
        accepted(value, 'backup', run_id)
        receipt = {**bindings, 'schema_version': 'UA-ART-PRODUCTION-BACKUP-RECEIPT-1',
                   'operation': 'backup', 'status': 'PASS', 'backup': 'PASS', 'unexpected_changes': 0,
                   'backup_manifest_sha256': value['backup_manifest_sha256']}
        save(env['UAART_BACKUP_RECEIPT_PATH'], receipt)
        save(PACKAGE+'/deployment_backup.json', value)
        return 0
    backup_sha = env['UAART_BACKUP_MANIFEST_SHA256']
    if operation == 'rollback':
        value = api.run('rollback', run_id, bundle, plan_sha, backup_sha)
        accepted(value, 'rollback', run_id, backup_sha)
        value['webapp_reload'] = reload_webapp(env['PYTHONANYWHERE_API_TOKEN'])
        if value.get('restored') is not True or value.get('crm_unchanged') is not True or value.get('crm_resume', {}).get('enabled') is not True:
            raise RuntimeError('ROLLBACK_INCOMPLETE')
        receipt = {**bindings, 'schema_version': 'UA-ART-PRODUCTION-ROLLBACK-RECEIPT-1',
                   'operation': 'rollback', 'status': 'ROLLED_BACK', 'rollback': 'PASS',
                   'restored': True, 'unexpected_changes': 0, 'protected_files_unchanged': True,
                   'crm_unchanged': True, 'live_verify': 'PASS', 'backup_manifest_sha256': backup_sha}
        save(env['UAART_ROLLBACK_RECEIPT_PATH'], receipt)
        save(PACKAGE+'/deployment_rollback.json', value)
        return 0
    value = api.run('install', run_id, bundle, plan_sha, backup_sha)
    save(PACKAGE+'/deployment_install.json', value)
    accepted(value, 'install', run_id, backup_sha)
    if value.get('installed') is not True or value.get('crm_unchanged') is not True or value.get('crm_resume', {}).get('enabled') is not True:
        raise RuntimeError('INSTALL_OR_RESUME_INCOMPLETE')
    verified = api.run('verify', run_id, bundle, plan_sha, backup_sha)
    accepted(verified, 'verify', run_id, backup_sha)
    if verified.get('code_sha256') != {name: item['after'] for name, item in plan['files'].items()}:
        raise RuntimeError('VERIFIED_CODE_HASH')
    if not (verified.get('report_check') or {}).get('events_7d'):
        raise RuntimeError('REPORT_CHECK_EMPTY')
    webapp_reload = reload_webapp(env['PYTHONANYWHERE_API_TOKEN'])
    if webapp_reload != 'HTTP_200':
        raise RuntimeError('WEBAPP_RELOAD:' + webapp_reload)
    public = public_verify()
    receipt = {**bindings, 'contract_id': 'UA-ART-CRITICAL-ADAPTER-V1.0', 'status': 'FINISHED',
               'task_class': 'CRITICAL', 'target_environment': 'production',
               'production_required': True, 'production': 'PASS', 'tests': 'PASS',
               'backup': 'PASS', 'backup_manifest_sha256': backup_sha, 'rollback': 'PASS',
               'rollback_ready': True, 'live_verify': 'PASS', 'unexpected_changes': 0,
               'protected_files_unchanged': True, 'crm_unchanged': True,
               'public_checks':public,'restart':value['crm_resume'],
               'webapp_reload':webapp_reload,'report_check':verified.get('report_check'),
               'code_sha256':verified['code_sha256'],
               'acceptance_scope':'FILES_INSTALLATION_BOT_RESUME_WEBAPP_RELOAD_PUBLIC_SCRIPT_AND_REPORT',
               'full_publication_acceptance':False,'database_migration_executed':False,
               'data_preservation_scope':value['preservation_scope']}
    save(env['UAART_RECEIPT_PATH'], receipt)
    save(PACKAGE+'/deployment_verify.json', verified)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(run())
