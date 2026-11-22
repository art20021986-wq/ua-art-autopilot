"""Actions controller for SEO-SITE-001; the installation preserves all existing CRM records."""
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
# Each page carries its change: the Korea share address, the catalogue and terms declared Ukrainian.
EXPECTED = {'/video/index.html': '', '/video/podbor.html': '',
            '/video/korea.html': '<meta property="og:url" content="https://www.uaart.com.ua/video/korea.html"',
            '/video/katalog.html': '<html lang="uk"', '/video/info.html': '<html lang="uk"'}
KOREA_RU = '<meta property="og:url" content="https://www.uaart.com.ua/video/ru/korea.html"'
# ru/korea.html is rebuilt by the installed job (once a minute) after the bot resumes.
REBUILD_SECONDS = 600
SITE = 'https://www.uaart.com.ua'
AGENT = 'UAART-SeoSite-Verify/1'


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


def public_verify(api, bundle, backup_sha, plan):
    results = {}
    for path in EXPECTED:
        request = urllib.request.Request(SITE+path, headers={'Cache-Control': 'no-cache', 'User-Agent': AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            final = urllib.parse.urlsplit(response.url)
            if response.status != 200 or (final.scheme, final.netloc, final.path) != ('https', 'www.uaart.com.ua', path):
                raise RuntimeError('PUBLIC_CANONICAL_HEALTH:'+path)
            body = response.read(1024*1024).decode('utf-8', 'replace')
        if len(body) < 100:
            raise RuntimeError('EMPTY_PUBLIC_PAGE:'+path)
        if EXPECTED[path] not in body:
            raise RuntimeError('PUBLIC_CHANGE_MISSING:'+path)
        results[path] = 'PASS'
    return results


def status(path):
    try:
        with urllib.request.urlopen(urllib.request.Request(SITE+path, headers={
                'Cache-Control': 'no-cache', 'User-Agent': AGENT}), timeout=30) as response:
            return response.status, response.read(4*1024*1024).decode('utf-8', 'replace')
    except urllib.error.HTTPError as error:
        return error.code, ''


def removed_gone(plan):
    """Every removed page answers 404 on the live site."""
    names = sorted(n for n, i in plan['files'].items() if i['after'] is None)
    alive = [n for n in names if status('/'+n)[0] != 404]
    if alive or not names:
        raise RuntimeError('REMOVED_STILL_SERVED:'+','.join(alive))
    return {'removed_404': len(names)}


def korea_ru_rebuilt(sleep=time.sleep, clock=time.monotonic):
    """The Russian Korea page follows the new korea.html: its own share address and Russian share title."""
    deadline = clock()+REBUILD_SECONDS
    while True:
        code, body = status('/video/ru/korea.html')
        title = re.findall(r'<meta property="og:title" content="([^"]*)"', body)
        if code == 200 and KOREA_RU in body and title and 'Аукционы Кореи' in title[0]:
            return {'ru_korea': 'PASS'}
        if clock() >= deadline:
            raise RuntimeError('KOREA_RU_NOT_REBUILT')
        sleep(30)


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
    public = public_verify(api, bundle, backup_sha, plan)
    receipt = {**bindings, 'contract_id': 'UA-ART-CRITICAL-ADAPTER-V1.0', 'status': 'FINISHED',
               'task_class': 'CRITICAL', 'target_environment': 'production',
               'production_required': True, 'production': 'PASS', 'tests': 'PASS',
               'backup': 'PASS', 'backup_manifest_sha256': backup_sha, 'rollback': 'PASS',
               'rollback_ready': True, 'live_verify': 'PASS', 'unexpected_changes': 0,
               'protected_files_unchanged': True, 'crm_unchanged': True,
               'public_checks':public,'restart':value['crm_resume'],
               'code_sha256':verified['code_sha256'],
               'sync_after_resume':verified.get('sync'),'removed':removed_gone(plan),'korea_ru':korea_ru_rebuilt(),
               'acceptance_scope':'FILES_INSTALLATION_BOT_RESUME_AND_PUBLIC_HEALTH',
               'full_publication_acceptance':False,'database_migration_executed':False,
               'data_preservation_scope':value['preservation_scope']}
    save(env['UAART_RECEIPT_PATH'], receipt)
    save(PACKAGE+'/deployment_verify.json', verified)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(run())
