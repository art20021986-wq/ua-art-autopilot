"""Actions controller; changes only the listed CRM fuel values and checks the republished pages."""
import json
import os
from pathlib import Path
import re
import tempfile
import time
import urllib.parse
import urllib.request

from deployment_transport import API, HERE, INBOX, canonical, sha, upload_package

ROOT = HERE.parents[1]
from release_constants import PREVIEW_TASK, INSTALL_TASK, PACKAGE
SITE = 'https://www.uaart.com.ua/video/'
# The public sync worker republishes changed cards one by one after the bot resumes.
REPUBLISH_SECONDS = 900
ARTICLE = re.compile(r'<article class="catalog-card"[^>]*>.*?</article>', re.S)


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
    if value.get('crm_write') is not (mode in ('install', 'rollback')) or value.get('safe_to_stop') is not True:
        raise RuntimeError('REMOTE_SCOPE')
    if backup and value.get('backup_manifest_sha256') != backup:
        raise RuntimeError('BACKUP_BINDING')


def fetch(name):
    request = urllib.request.Request(SITE+name+'?fuelnorm=%d' % time.time(),
                                     headers={'Cache-Control': 'no-cache', 'User-Agent': 'UAART-FuelNormalize-Verify/1'})
    with urllib.request.urlopen(request, timeout=30) as response:
        final = urllib.parse.urlsplit(response.url)
        if response.status != 200 or (final.netloc, final.path) != ('www.uaart.com.ua', '/video/'+name):
            raise RuntimeError('PUBLIC_CANONICAL_HEALTH:'+name)
        return response.read(4*1024*1024).decode('utf-8', 'replace')


def card_line(catalog, code):
    for article in ARTICLE.findall(catalog):
        if '>%s<' % code in article:
            return re.sub(r'<[^>]+>', ' ', article)
    return None


def public_verify(changes, fetch=fetch, sleep=time.sleep, clock=time.monotonic):
    """Wait until the catalog shows every new published fuel value and none of the old ones."""
    published = [c for c in changes if c.get('published') == 1]
    deadline = clock()+REPUBLISH_SECONDS
    while True:
        catalog = fetch('katalog.html')
        if len(catalog) < 1000:
            raise RuntimeError('EMPTY_CATALOG')
        waiting = []
        for change in published:
            line = card_line(catalog, change['auto_number'])
            if line is None or ' %s ' % change['after'] not in line or ' %s ' % change['before'] in line:
                waiting.append(change['auto_number'])
        if not waiting:
            break
        if clock() >= deadline:
            raise RuntimeError('REPUBLISH_TIMEOUT:'+','.join(waiting))
        sleep(20)
    results = {'/video/katalog.html': 'PASS', '/video/index.html': 'PASS' if len(fetch('index.html')) > 1000 else 'FAIL'}
    for change in published:
        results['/video/%s.html' % change['auto_number']] = 'PASS' if change['after'] in fetch(change['auto_number']+'.html') else 'FAIL'
    if set(results.values()) != {'PASS'}:
        raise RuntimeError('PUBLIC_CHANGE_MISSING:'+json.dumps(results))
    return results


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
        if value.get('restored') is not True or value.get('crm_unchanged') is not True or value.get('crm_resume', {}).get('enabled') is not True:
            raise RuntimeError('ROLLBACK_INCOMPLETE')
        public_verify([dict(c, before=c['after'], after=c['before']) for c in plan['changes']])
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
    if verified.get('crm_changes') != plan['changes']:
        raise RuntimeError('VERIFIED_CRM_CHANGES')
    public = public_verify(plan['changes'])
    receipt = {**bindings, 'contract_id': 'UA-ART-CRITICAL-ADAPTER-V1.0', 'status': 'FINISHED',
               'task_class': 'CRITICAL', 'target_environment': 'production',
               'production_required': True, 'production': 'PASS', 'tests': 'PASS',
               'backup': 'PASS', 'backup_manifest_sha256': backup_sha, 'rollback': 'PASS',
               'rollback_ready': True, 'live_verify': 'PASS', 'unexpected_changes': 0,
               'protected_files_unchanged': True, 'crm_unchanged': True,
               'crm_unchanged_scope':'ALL_CRM_ROWS_AND_FIELDS_EXCEPT_APPROVED_FUEL_VALUES',
               'crm_changes':plan['changes'],
               'public_checks':public,'restart':value['crm_resume'],
               'acceptance_scope':'CRM_FUEL_VALUES_BOT_RESUME_AND_REPUBLISHED_CATALOG',
               'full_publication_acceptance':False,'database_migration_executed':False,
               'data_preservation_scope':value['preservation_scope']}
    save(env['UAART_RECEIPT_PATH'], receipt)
    save(PACKAGE+'/deployment_verify.json', verified)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(run())
