"""Bounded CARD-LANG-001 release (card language versions: two modules, four small edits); preserve live data and pending requests."""
import argparse
import datetime
from contextlib import closing, contextmanager
import fcntl
import gzip
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time

from deployment_transport import API, canonical, sha
from candidate_builder import SOURCE_FILES, DEPENDENCY_SHA256, build

ROOT = Path('/home/Carix')
HERE = Path(__file__).resolve().parent
# The account's PythonAnywhere disk quota (owner's Files page, 2026-10-20:
# "8.2 GB of your 35.0 GB quota"); decimal GB is the conservative reading.
QUOTA_BYTES = 35 * 10**9
PAGES = ('video/katalog.html', 'site/katalog.html', 'video/index.html', 'site/index.html')
PROTECTED = ('start_safe.py', 'run_all.py', 'ua_site_counters.py',
             'publication_fence.py', 'catalog_design_golden.html')


class DeploymentError(RuntimeError):
    pass


def read(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 16*1024*1024:
        raise DeploymentError('UNSAFE_FILE:'+path.name)
    if path.resolve() != path:
        raise DeploymentError('NONCANONICAL_PATH')
    return path.read_bytes()


def atomic(path, value, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix='.cardlang-')
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def rows(connection):
    cursor = connection.execute('SELECT * FROM cars ORDER BY id')
    columns = tuple(item[0] for item in cursor.description)
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def crm_rows():
    with closing(sqlite3.connect((ROOT/'crm.db').as_uri()+'?mode=ro', uri=True, timeout=5)) as connection:
        return rows(connection)


def row_digest(value):
    return sha(canonical(value))


def prepare(directory):
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    source = {name: read(ROOT/name) for name in SOURCE_FILES}
    dependencies = {name: read(ROOT/name) for name in DEPENDENCY_SHA256}
    candidate = build(source, dependencies)
    for name, value in candidate.items():
        if name.endswith('.py'):
            compile(value, name, 'exec')
    protected_names = set(DEPENDENCY_SHA256) | {
        'start_safe.py','run_all.py','team_bot.py','lead_bot.py','db.py',
        'publication_fence.py','ua_public_freshness.py',
        'ua_site_counters.py','catalog_design_guard.py','cars_schema.py',
        'stranica.py','master_card.py','publish_transaction_guard.py',
        'ua_seo_catalog.py',
    }
    protected = {name:sha(read(ROOT/name)) for name in sorted(protected_names)}
    files = {}
    for name,value in sorted(candidate.items()):
        before = source.get(name)
        mode = stat.S_IMODE((ROOT/name).stat().st_mode) if before is not None else 0o644
        files[name] = {'before':sha(before) if before is not None else None,
                       'after':sha(value), 'mode':mode}
        if before is None and ((ROOT/name).exists() or (ROOT/name).is_symlink()):
            raise DeploymentError('NEW_FILE_EXISTS:'+name)
        if before is not None: atomic(directory/'before'/name,before,mode)
        atomic(directory/'after'/name,value,mode)
    # A source-only plan stays valid across legitimate operator edits. Actual
    # CRM/page snapshots are captured again under locks at the write boundary.
    plan = {'schema_version':'CARD-LANG-INSTALL-1','files':files,
            'protected':protected,'crm_write':False,'site_write':True,
            'site_scope':'card language versions: video/ua/ and video/ru/ derived from every published card (ua_card_lang, CRM bot job), card canonical (ua_seo_metadata), sitemap (ua_seo_sitemap), site language script',
            'pending_requests_preserved':True}
    atomic(directory/'plan.json',canonical(plan))
    return plan


# Runs in a separate python3.10 (the bots' interpreter) on the candidate files and the live cards: every
# published card is turned into its language versions and normalized with the candidate modules, in memory.
# Nothing is written.
SMOKE = r'''
import json, sys
after, root = sys.argv[1], sys.argv[2]
sys.path[:0] = [after, root]
import ua_card_lang, ua_seo_metadata, ua_seo_sitemap
video = root + '/video'
script = open(after + '/video/ua-site-languages.js', encoding='utf-8').read()
words = ua_card_lang.dictionary(script)
names = sorted(ua_seo_sitemap.CatalogLinks(open(video + '/katalog.html', encoding='utf-8').read()).names)
incomplete, review, bytes_out = {}, {}, 0
for name in names:
    source = open(video + '/' + name, encoding='utf-8').read()
    pages, missing = ua_card_lang.versions(source, name, words, ua_card_lang.revision(source, script))
    if pages is None:
        incomplete[name] = missing
    else:
        bytes_out += sum(len(p) for p in pages.values())
        found = ua_card_lang.suspects(source, ua_card_lang.ukrainian(ua_card_lang.absolute(source), words)[0], words)
        if found:
            review[name] = found
    normalized = ua_seo_metadata.normalize(source, video + '/' + name)
    assert ua_seo_metadata.normalize(normalized, video + '/' + name) == normalized, name
print(json.dumps({'cards': len(names), 'complete': len(names) - len(incomplete), 'incomplete': incomplete,
                  'review': review, 'versions_bytes': bytes_out}, ensure_ascii=False))
'''


def smoke(directory):
    result = subprocess.run(['python3.10', '-B', '-c', SMOKE, str(directory/'after'), str(ROOT)],
                            capture_output=True, text=True, timeout=120, check=False, cwd=str(directory))
    if result.returncode != 0:
        raise DeploymentError('SMOKE:'+result.stderr.strip()[-300:])
    value = json.loads(result.stdout.strip().splitlines()[-1])
    if not value['cards']:
        raise DeploymentError('SMOKE_RESULT:no published cards')
    return value


def verify_files(plan, after):
    for relative,item in plan['files'].items():
        expected = item['after' if after else 'before']
        path = ROOT/relative
        if expected is None:
            if path.exists() or path.is_symlink():
                raise DeploymentError('UNEXPECTED_FILE:'+relative)
        elif sha(read(path)) != expected:
            raise DeploymentError('FILE_CHANGED:'+relative)
    for relative,digest in plan['protected'].items():
        if sha(read(ROOT/relative)) != digest:
            raise DeploymentError('PROTECTED_CHANGED:'+relative)


def load_backup(digest):
    directory = HERE/'backups'/digest
    manifest = json.loads(read(directory/'manifest.json'))
    if sha(canonical(manifest)) != digest:
        raise DeploymentError('BACKUP_HASH')
    if sha(read(directory/'crm.db')) != manifest['database_backup_sha256']:
        raise DeploymentError('DATABASE_BACKUP_CHANGED')
    plan = manifest['plan']
    if sha(canonical(plan)) != manifest['plan_sha256']:
        raise DeploymentError('BACKUP_PLAN_HASH')
    for relative, item in plan['files'].items():
        for prefix, key in (('before', 'before'), ('after', 'after')):
            if item[key] is not None and sha(read(directory/prefix/relative)) != item[key]:
                raise DeploymentError('BACKUP_FILE_CHANGED')
    return directory, manifest


def backup(run_id, expected_plan):
    workspace = HERE/'runs'/run_id/'backup-prepared'
    plan = prepare(workspace)
    if sha(canonical(plan)) != expected_plan:
        raise DeploymentError('LIVE_PLAN_DRIFT')
    database = workspace/'crm.db'
    with database.open('xb'): os.chmod(database,0o600)
    with closing(sqlite3.connect((ROOT/'crm.db').as_uri()+'?mode=ro',uri=True,timeout=5)) as source:
        with closing(sqlite3.connect(database)) as target:
            deadline = time.monotonic()+60
            def progress(status,remaining,total):
                if time.monotonic() >= deadline: raise DeploymentError('BACKUP_TIMEOUT')
            source.backup(target,pages=256,progress=progress)
            if target.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                raise DeploymentError('BACKUP_DATABASE_VERIFY')
            crm_snapshot = row_digest(rows(target))
    verify_files(plan,False)
    manifest = {'plan':plan,'plan_sha256':expected_plan,'run_id':run_id,
                'crm_rows_sha256':crm_snapshot,'database_backup_sha256':sha(read(database))}
    digest = sha(canonical(manifest))
    atomic(workspace/'manifest.json',canonical(manifest))
    target = HERE/'backups'/digest
    target.parent.mkdir(mode=0o700,exist_ok=True)
    os.rename(workspace,target)
    load_backup(digest)
    return {'backup_manifest_sha256':digest,'backup':str(target),'plan_sha256':expected_plan}


@contextmanager
def writer_exclusion():
    lock = open(ROOT/'.crm_public_sync_worker.lock', 'a+')
    deadline = time.monotonic()+30
    try:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise DeploymentError('WORKER_BUSY')
                time.sleep(.1)
        fence = load(ROOT/'publication_fence.py', 'delivery_publication_fence')
        with fence.publication_fence(timeout=30):
            with closing(sqlite3.connect((ROOT/'crm.db').as_uri()+'?mode=rw', uri=True, timeout=5)) as connection:
                connection.execute('BEGIN IMMEDIATE')
                try:
                    yield
                finally:
                    connection.rollback()
    finally:
        lock.close()


def no_bot_processes():
    names = {'start_safe.py', 'run_all.py', 'team_bot.py', 'lead_bot.py'}
    deadline = time.monotonic()+30
    while True:
        found = []
        for item in Path('/proc').glob('[0-9]*'):
            try:
                if item.stat().st_uid != os.getuid() or int(item.name) == os.getpid():
                    continue
                args = (item/'cmdline').read_bytes().decode(errors='replace').split('\0')
                if any(Path(arg).name in names for arg in args):
                    found.append(item.name)
            except (OSError, ValueError):
                continue
        if not found:
            return
        if time.monotonic() >= deadline:
            raise DeploymentError('OLD_BOT_PROCESSES_REMAIN')
        time.sleep(1)


def restore(directory, plan):
    for relative,digest in plan['protected'].items():
        if sha(read(ROOT/relative)) != digest:
            raise DeploymentError('PROTECTED_CHANGED:'+relative)
    for relative,item in plan['files'].items():
        path=ROOT/relative
        current=sha(read(path)) if path.exists() else None
        if path.is_symlink() or current not in (item['before'],item['after']):
            raise DeploymentError('ROLLBACK_CONCURRENT_CHANGE:'+relative)
    for relative,item in reversed(list(plan['files'].items())):
        path=ROOT/relative
        if item['before'] is None: path.unlink(missing_ok=True)
        else: atomic(path,read(directory/'before'/relative),item['mode'])
    verify_files(plan,False)


def lifecycle(mode, run_id, expected_plan, backup_sha):
    directory,manifest = load_backup(backup_sha)
    if manifest['plan_sha256'] != expected_plan or manifest['run_id'] != run_id:
        raise DeploymentError('INSTALL_PLAN_IDENTITY')
    plan=manifest['plan']; api=API(os.environ.get('API_TOKEN'))
    journal=directory/('journal-'+mode+'.json')
    previous=json.loads(read(journal)) if journal.exists() else None
    observed=api.bot()
    install_journal=directory/'journal-install.json'
    owner=json.loads(read(install_journal)) if install_journal.exists() else {}
    owned_pause=(mode=='rollback' and owner.get('backup_sha256')==backup_sha
                 and owner.get('stage') in ('PAUSE_INTENT','APPLYING','RESUME','FINISHED'))
    if not previous and not owned_pause and (observed.get('enabled') is not True
            or str(observed.get('state')).lower()!='running'):
        raise DeploymentError('BOT_NOT_RUNNING_BEFORE_PAUSE')
    state=previous or {'stage':'PAUSE_INTENT','mode':mode,'backup_sha256':backup_sha}
    atomic(journal,canonical(state));result=state.get('result')
    if state['stage'] not in ('RESUME','FINISHED'):
        applied=bool(previous and previous.get('stage')=='APPLYING')
        try:
            api.set_bot(False); no_bot_processes()
            with writer_exclusion():
                before=protected_data(plan)
                if mode=='rollback' or applied:
                    restore_all(directory,plan)
                    result={'status':'PASS' if mode=='rollback' else 'FAIL',
                            'restored':True,'interrupted_install':applied}
                else:
                    verify_files(plan,False)
                    state.update(stage='APPLYING',data_before=before)
                    atomic(journal,canonical(state));applied=True
                    try:
                        for relative in plan['files']:
                            atomic(ROOT/relative,read(directory/'after'/relative),plan['files'][relative]['mode'])
                        verify_files(plan,True)
                        refreshed=card_versions()
                        if protected_data(plan)!=before: raise DeploymentError('PROTECTED_DATA_CHANGED_DURING_INSTALL')
                        result={'status':'PASS','installed':True,'card_versions':refreshed}
                    except BaseException:
                        restore_all(directory,plan);applied=False
                        raise
                if protected_data(plan)!=before:
                    raise DeploymentError('PROTECTED_DATA_CHANGED_DURING_OPERATION')
                result.update(crm_unchanged=True,protected_files_unchanged=True,
                              preservation_scope='WHILE_BOT_PAUSED_UNDER_WRITER_LOCKS',
                              protected_data_sha256=sha(canonical(before)))
        except Exception as error:
            result={'status':'FAIL','error':type(error).__name__+':'+str(error)[:180]}
            if applied:
                try:
                    with writer_exclusion(): restore_all(directory,plan)
                    result['restored']=True
                except Exception as restore_error:
                    result['rollback_error']=type(restore_error).__name__+':'+str(restore_error)[:160]
        state.update(stage='RESUME',result=result);atomic(journal,canonical(state))
    if result.get('rollback_error'):
        result['crm_resume']={'enabled':False,'state':'rollback_requires_reconciliation'}
    else:
        result['crm_resume']=api.set_bot(True)
    state.update(stage='FINISHED',result=result);atomic(journal,canonical(state))
    return {**result,'backup_manifest_sha256':backup_sha,'plan_sha256':expected_plan}



def installed_modules():
    """Fresh imports of the installed SEO modules (and this release's), from the server root."""
    for name in [n for n in sys.modules if n.startswith(('ua_seo_', 'ua_card_lang')) or n in ('ua_indexnow', 'ua_google_sitemap')]:
        del sys.modules[name]
    sys.path.insert(0, str(ROOT))
    try:
        return importlib.import_module('ua_seo_index'), importlib.import_module('ua_seo_sitemap')
    finally:
        sys.path.remove(str(ROOT))


def card_versions():
    """Language versions of every published card with the installed modules, then sitemap and IndexNow."""
    index, sitemap = installed_modules()
    sys.path.insert(0, str(ROOT))
    try:
        lang = importlib.import_module('ua_card_lang')
    finally:
        sys.path.remove(str(ROOT))
    video = ROOT/'video'
    published = sitemap.CatalogLinks((video/'katalog.html').read_text(encoding='utf-8')).names
    value = lang.reconcile(video, published)
    if value['failed'] or not value['written']:
        raise DeploymentError('CARD_VERSIONS:'+json.dumps({k: value[k] for k in ('failed', 'written')})[:160])
    value['seo_index'] = index.refresh(video)
    if value['seo_index'].get('status') != 'PASS':
        raise DeploymentError('SEO_REFRESH')
    return value


def restore_all(directory, plan):
    """The release's files back as they were, its derived language versions removed, the sitemap renewed."""
    restore(directory, plan)
    for folder in ('ua', 'ru'):
        for path in sorted((ROOT/'video'/folder).glob('UA-*.html')):
            path.unlink()
    try:
        installed_modules()[0].refresh(ROOT/'video')
    except Exception:
        pass  # the next publication renews the sitemap; the restored files are what matters


def protected_data(plan):
    # Only read while the existing publication and database locks are held.
    pages={}
    for folder in ('video','site'):
        for path in sorted((ROOT/folder).glob('*.html')):
            if str(path.relative_to(ROOT)) not in plan['files']:
                pages[str(path.relative_to(ROOT))]=sha(read(path))
    ledger=ROOT/'.crm_publish_requests/requests.sqlite3'
    if ledger.exists() or ledger.is_symlink():
        pages['.crm_publish_requests/requests.sqlite3']=sha(read(ledger))
        for suffix in ('-wal','-shm'):
            part=Path(str(ledger)+suffix)
            if part.exists(): pages[str(part.relative_to(ROOT))]=sha(read(part))
    with closing(sqlite3.connect((ROOT/'crm.db').as_uri()+'?mode=ro',uri=True,timeout=5)) as con:
        database=sha(('\n'.join(con.iterdump())+'\n').encode())
    return {'database_logical_sha256':database,'pages_and_pending_ledger':pages}

def account_used_bytes():
    """Bytes counted against the quota: home and /tmp, measured as PythonAnywhere's help does."""
    result = subprocess.run(['du', '-s', '-B1', str(ROOT), '/tmp'], capture_output=True, text=True,
                            timeout=600, check=False)
    sizes = [int(line.split('\t')[0]) for line in result.stdout.splitlines() if line.strip()]
    if result.returncode != 0 or len(sizes) != 2:
        raise DeploymentError('ACCOUNT_USAGE:'+result.stderr[-160:])
    return sum(sizes)


def storage_probe():
    """Space against the account quota; the shared filesystem figure is kept for reference only."""
    measured_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    used = account_used_bytes()
    if used > QUOTA_BYTES:
        raise DeploymentError('ACCOUNT_OVER_QUOTA')
    shared = shutil.disk_usage(ROOT)
    return {'target_environment': 'production', 'read_only': True, 'measured_at': measured_at,
            'total_bytes': QUOTA_BYTES, 'used_bytes': used, 'free_bytes': QUOTA_BYTES-used,
            'account_quota_measured': True,
            'measurement_method': 'account quota: du -s -B1 /home/Carix /tmp against the 35.0 GB plan quota',
            'shared_filesystem': {'total_bytes': shared.total, 'used_bytes': shared.used, 'free_bytes': shared.free,
                                  'measurement_method': 'shutil.disk_usage(/home/Carix)'}}


def installed(run_id, expected_plan, backup_sha):
    """Return the backup manifest and install result only for a finished install."""
    _, manifest = load_backup(backup_sha)
    verify_files(manifest['plan'], True)
    if manifest['run_id'] != run_id or manifest['plan_sha256'] != expected_plan:
        raise DeploymentError('VERIFY_BINDING')
    journal=json.loads(read(HERE/'backups'/backup_sha/'journal-install.json'))
    result=journal.get('result',{})
    if journal.get('stage')!='FINISHED' or result.get('status')!='PASS' or result.get('installed') is not True:
        raise DeploymentError('INSTALL_JOURNAL_NOT_FINISHED')
    if result.get('crm_unchanged') is not True or result.get('protected_files_unchanged') is not True:
        raise DeploymentError('INSTALL_DATA_PRESERVATION')
    return manifest, result


def main():
    cpu_start = time.process_time()
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', required=True, choices=('preview', 'backup', 'install', 'verify', 'rollback'))
    parser.add_argument('--run', required=True)
    parser.add_argument('--plan', default='')
    parser.add_argument('--backup', default='')
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CPU, (20, 25))
    if not re.fullmatch(r'[0-9]+', args.run):
        raise DeploymentError('RUN_ID')
    work = HERE/'runs'/args.run
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = work/('receipt-'+args.mode+'.json')
    if receipt.exists():
        return 0 if json.loads(read(receipt))['status'] == 'PASS' else 1
    value = {'run_id': args.run, 'mode': args.mode, 'status': 'FAIL', 'crm_write': False}
    with (HERE/'deployment.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if receipt.exists():
            return 0 if json.loads(read(receipt))['status'] == 'PASS' else 1
        try:
            if args.mode == 'preview':
                plan = prepare(work/'preview')
                value.update(status='PASS', plan=plan, plan_sha256=sha(canonical(plan)), smoke=smoke(work/'preview'))
                value['storage_probe'] = storage_probe()
            elif args.mode == 'backup':
                value.update(backup(args.run, args.plan), status='PASS')
            elif args.mode in ('install', 'rollback'):
                value.update(lifecycle(args.mode, args.run, args.plan, args.backup))
            else:
                manifest, result = installed(args.run, args.plan, args.backup)
                value.update(status='PASS',backup_manifest_sha256=args.backup,
                             plan_sha256=args.plan,crm_unchanged=True,protected_files_unchanged=True,
                             preservation_scope=result['preservation_scope'],
                             code_sha256={name: item['after'] for name, item in manifest['plan']['files'].items()})
            value['safe_to_stop'] = True
        except Exception as error:
            value['error'] = type(error).__name__+':'+str(error)[:180]
            if args.mode in ('preview', 'backup', 'verify'):
                value['safe_to_stop'] = True
            else:
                # A lifecycle journal must finish its own resume or recovery.
                journal = HERE/'backups'/args.backup/('journal-'+args.mode+'.json')
                if journal.exists():
                    return 1
                value['safe_to_stop'] = True
        value['cpu_seconds'] = round(time.process_time()-cpu_start, 3)
        atomic(receipt, canonical(value))
    print(json.dumps(value, sort_keys=True))
    return 0 if value['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
