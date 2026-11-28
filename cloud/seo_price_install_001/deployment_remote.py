"""Bounded site release SEO-PRICE-001 (the card price back in the title, description and JSON-LD); preserve live data and
pending requests. No CRM row changes; after the code, the existing card publisher (stranica, as the CRM self-check)
rebuilds the card pages. Before/after: on the card pages only the title, description, og texts and the JSON-LD may
change."""
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
import page_compare
from release_constants import NEW_MODULES

ROOT = Path('/home/Carix')
QUOTA_BYTES = 35 * 10**9
HERE = Path(__file__).resolve().parent
PAGES = ('video/katalog.html', 'site/katalog.html', 'video/index.html', 'site/index.html')
PROTECTED = ('start_safe.py', 'run_all.py', 'ua_site_counters.py',
             'publication_fence.py', 'catalog_design_golden.html')


class DeploymentError(RuntimeError):
    pass


def read(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 64*1024*1024:
        raise DeploymentError('UNSAFE_FILE:'+path.name)
    if path.resolve() != path:
        raise DeploymentError('NONCANONICAL_PATH')
    return path.read_bytes()


def atomic(path, value, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix='.seoprice-')
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
    for name in candidate:
        if name.endswith('.py'):
            compile(candidate[name], name, 'exec')
    for name in NEW_MODULES:
        if (ROOT/name).exists() or (ROOT/name).is_symlink():
            raise DeploymentError('NEW_FILE_ALREADY_EXISTS:'+name)
    protected_names = set(DEPENDENCY_SHA256) | {
        'start_safe.py','run_all.py','team_bot.py','lead_bot.py','db.py',
        'publication_fence.py','ua_public_freshness.py',
        'ua_site_counters.py','catalog_design_guard.py','cars_schema.py',
        'stranica.py','konteyner.py','master_card.py',
        'ua_crm_catalog_folders.py','ua_crm_public_sync.py','ua_card_delete.py',
        'publikaciya.py','publish_transaction_guard.py',
        'cars_ui.py','ua_delivery_status.py','ua_car_country.py','site_ge_inject.py','ua_price_html_v2.py',
        'ua_card_lang.py','ua_card_lang_job.py','yadro.py',
    }
    protected_names -= set(candidate)  # the files this release changes are pinned in files, not as protected
    protected = {name:sha(read(ROOT/name)) for name in sorted(protected_names)}
    files = {}
    for name,value in sorted(candidate.items()):
        before = source.get(name)
        mode = stat.S_IMODE((ROOT/name).stat().st_mode) if before is not None else 0o644
        files[name] = {'before':sha(before) if before is not None else None,
                       'after':sha(value), 'mode':mode}
        if before is not None: atomic(directory/'before'/name,before,mode)
        atomic(directory/'after'/name,value,mode)
    # A source-only plan stays valid across legitimate operator edits. Actual
    # CRM/page snapshots are captured again under locks at the write boundary.
    plan = {'schema_version':'SEO-PRICE-INSTALL-1','files':files,
            'protected':protected,'crm_write':False,'site_write':True,
            'site_scope':'new ua_seo_price.py and a tail on ua_seo_metadata.card_facts: the card price in <title>, the description, og and the Product JSON-LD even when normalize runs before the price block is put in; then the card pages rebuilt by stranica; no other page, catalog or CRM change',
            'pending_requests_preserved':True}
    atomic(directory/'plan.json',canonical(plan))
    return plan


# Runs in a separate python3.10 (the bot's interpreter) with the candidate modules first on the path and the live server
# root: for every published card, the candidate ua_seo_metadata.normalize on the page as the writer has it before the
# price block (the block taken out), and on the live page, must give the price from the live price block; the live
# installed normalize is run the same way for comparison. Nothing is written (RLIMIT_FSIZE 0).
SMOKE = r"""
import json, re, resource, sqlite3, sys
resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
after, root = sys.argv[1], sys.argv[2]
sys.path[:0] = [after, root]
import ua_seo_metadata
from ua_price_html_v2 import BLOCK, LEGACY
con = sqlite3.connect('file:%s/crm.db?mode=ro' % root, uri=True, timeout=5)
codes = [c for (c,) in con.execute("SELECT auto_number FROM cars WHERE published=1 ORDER BY auto_number") if c]
con.close()
price = re.compile(r'data-ua-market=["\']ukraine["\'][^>]*?data-ua-value=["\']([0-9]+)')
title = re.compile(r'<title[^>]*>(.*?)</title>', re.S)
cards = {}
for code in codes:
    try:
        page = open('%s/video/%s.html' % (root, code), encoding='utf-8').read()
    except OSError:
        continue
    found = price.search(page)
    if not found:
        cards[code] = {'price': None}
        continue
    raw = BLOCK.sub('<div class="cena">' + found.group(1) + '</div>', page, count=1)
    path = '%s/video/%s.html' % (root, code)
    before_block = ua_seo_metadata.normalize(raw, path)
    live = ua_seo_metadata.normalize(page, path)
    amount = '{:,}'.format(int(found.group(1))).replace(',', '\u00a0') + ' $'
    cards[code] = {'price': int(found.group(1)),
                   'title_before_block': amount in title.search(before_block).group(1),
                   'title_live': amount in title.search(live).group(1),
                   'ld_before_block': '"price"' in before_block, 'same_canonical': re.findall(
                       r'<link rel="canonical" href="([^"]+)"', live) == re.findall(r'<link rel="canonical" href="([^"]+)"', page)}
print(json.dumps({'cards': cards}, ensure_ascii=False))
"""


def smoke(directory):
    result = subprocess.run(['python3.10', '-B', '-c', SMOKE, str(directory/'after'), str(ROOT)],
                            capture_output=True, text=True, timeout=240, check=False, cwd=str(directory))
    if result.returncode != 0:
        raise DeploymentError('SMOKE:'+result.stderr.strip()[-300:])
    value = json.loads(result.stdout.strip().splitlines()[-1])
    cards = value['cards']
    priced = {c: v for c, v in cards.items() if v['price']}
    value['summary'] = {'cards': len(cards), 'priced': len(priced),
                        'title_before_block': sum(v['title_before_block'] for v in priced.values()),
                        'title_live': sum(v['title_live'] for v in priced.values()),
                        'ld_before_block': sum(v['ld_before_block'] for v in priced.values()),
                        'same_canonical': sum(v['same_canonical'] for v in priced.values())}
    if not priced or any(value['summary'][k] != len(priced) for k in
                         ('title_before_block', 'title_live', 'ld_before_block', 'same_canonical')):
        raise DeploymentError('SMOKE_RESULT:'+json.dumps(value['summary']))
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
                before=protected_data()
                if mode=='rollback' or applied:
                    restore(directory,plan)
                    result={'status':'PASS' if mode=='rollback' else 'FAIL',
                            'restored':True,'interrupted_install':applied}
                else:
                    verify_files(plan,False)
                    state.update(stage='APPLYING',data_before=before)
                    atomic(journal,canonical(state));applied=True
                    try:
                        ordered=sorted(plan['files'],key=lambda n:plan['files'][n]['before'] is not None)  # new modules first
                        for relative in ordered:
                            atomic(ROOT/relative,read(directory/'after'/relative),plan['files'][relative]['mode'])
                        verify_files(plan,True)
                        if protected_data()!=before: raise DeploymentError('PROTECTED_DATA_CHANGED_DURING_INSTALL')
                        result={'status':'PASS','installed':True}
                    except BaseException:
                        restore(directory,plan);applied=False
                        raise
                if protected_data()!=before:
                    raise DeploymentError('PROTECTED_DATA_CHANGED_DURING_OPERATION')
                result.update(crm_unchanged=True,protected_files_unchanged=True,
                              preservation_scope='WHILE_BOT_PAUSED_UNDER_WRITER_LOCKS',
                              protected_data_sha256=sha(canonical(before)))
        except Exception as error:
            result={'status':'FAIL','error':type(error).__name__+':'+str(error)[:180]}
            if applied:
                try:
                    with writer_exclusion(): restore(directory,plan)
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



def protected_data():
    # Only read while the existing publication and database locks are held.
    pages={}
    for folder in ('video','site'):
        for path in sorted((ROOT/folder).glob('*.html')):
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


CARD_FILES = ('video/%s.html', 'site/%s.html')


def published_codes():
    with closing(sqlite3.connect((ROOT/'crm.db').as_uri()+'?mode=ro',uri=True,timeout=5)) as con:
        return [c for (c,) in con.execute("SELECT auto_number FROM cars WHERE published=1 ORDER BY auto_number") if c]


def card_pages():
    """The base card pages of the published cars as they are now (both site folders)."""
    pages={}
    for code in published_codes():
        for pattern in CARD_FILES:
            path=ROOT/(pattern % code)
            if path.is_file(): pages[pattern % code]=read(path).decode('utf-8')
    return pages


def republish():
    """The existing card publisher with the new code: every card page (stranica, as the CRM self-check). It takes the
    publication locks itself; the language versions follow from the card version job (ua_card_lang_job)."""
    started=time.monotonic()
    result=subprocess.run(['python3.10','-c',"import sys; sys.path.insert(0, '/home/Carix'); import stranica; stranica.main()"],
                          cwd=str(ROOT),capture_output=True,text=True,timeout=330,check=False)
    last=(result.stderr.strip().splitlines() or [''])[-1]
    steps={'cards':{'returncode':result.returncode,'error':re.sub(r'\d{6,}','[N]',last)[:160] if result.returncode else ''}}
    if result.returncode: return {'status':'FAIL','steps':steps}
    return {'status':'PASS','steps':steps,'seconds':round(time.monotonic()-started)}


def pages_check(before=None):
    """After the rebuild: every published card with a price block names that price in its title and JSON-LD; with the
    pages read before the install, any change outside the search fields is listed."""
    after=card_pages()
    cards={name:page_compare.card((before or {}).get(name),page) for name,page in after.items()}
    priced={n:v for n,v in cards.items() if v['price']}
    value={'pages':len(cards),'priced':len(priced),
           'title_with_price':sum(v['title_has_price'] for v in priced.values()),
           'ld_price':sum(v['ld_price'] for v in priced.values()),
           'other_changes':sorted(n for n,v in cards.items() if v['other_changes']),
           'missing_after':sorted(set(before or {})-set(after))}
    if not priced or value['title_with_price']!=len(priced) or value['ld_price']!=len(priced):
        raise DeploymentError('PAGES_CHECK:'+json.dumps({k:value[k] for k in ('pages','priced','title_with_price','ld_price')}))
    return value


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


def main():
    cpu_start = time.process_time()
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', required=True, choices=('preview', 'backup', 'install', 'verify', 'rollback'))
    parser.add_argument('--run', required=True)
    parser.add_argument('--plan', default='')
    parser.add_argument('--backup', default='')
    args = parser.parse_args()
    limit = {'preview': 60, 'install': 600, 'rollback': 600}.get(args.mode, 20)  # install/rollback rebuild the pages
    resource.setrlimit(resource.RLIMIT_CPU, (limit, limit + 5))
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
                value.update(plan=plan, plan_sha256=sha(canonical(plan)), storage_probe=storage_probe(),
                             smoke=smoke(work/'preview'), status='PASS')
            elif args.mode == 'backup':
                value.update(backup(args.run, args.plan), status='PASS')
            elif args.mode in ('install', 'rollback'):
                before = card_pages() if args.mode == 'install' else None
                value.update(lifecycle(args.mode, args.run, args.plan, args.backup))
                if value.get('status') == 'PASS':
                    value['republish'] = republish()
                    if value['republish']['status'] != 'PASS':
                        value.update(status='FAIL', error='REPUBLISH_FAILED')
                    elif before is not None:
                        try:
                            value['pages'] = pages_check(before)
                        except DeploymentError as error:
                            value.update(status='FAIL', error=str(error)[:180])
            else:
                manifest, result = installed(args.run, args.plan, args.backup)
                value.update(status='PASS',backup_manifest_sha256=args.backup,
                             plan_sha256=args.plan,crm_unchanged=True,protected_files_unchanged=True,
                             preservation_scope=result['preservation_scope'],
                             code_sha256={name: item['after'] for name, item in manifest['plan']['files'].items()},
                             pages=pages_check())
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
