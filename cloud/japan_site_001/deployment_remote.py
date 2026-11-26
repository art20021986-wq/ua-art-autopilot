"""Bounded site release JAPAN-STOCK-001 step 2 (home titles, catalog «Выкуплены» and the country row, card texts with
Japan); preserve live data and pending requests. No CRM row changes; after the code, the existing publishers rebuild
the card pages and the catalog (as the CRM self-check and the publish button do)."""
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
import edit_home
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
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix='.japansite-')
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
    edit_home.build(read(ROOT/edit_home.NAME))  # the home titles are found exactly once
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
        'cars_ui.py','ua_delivery_status.py','ua_car_country.py',
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
    plan = {'schema_version':'JAPAN-SITE-INSTALL-1','files':files,
            'protected':protected,'crm_write':False,'site_write':True,
            'pending_requests_preserved':True}
    atomic(directory/'plan.json',canonical(plan))
    return plan


# Runs in a separate python3.10 (the bot's interpreter) on the candidate files, reading live data only: builds the
# catalog from the candidate golden page and the live published cars (as the publisher does), audits it, runs the
# candidate stage sync on the live and the built catalog, the counters on the built one, and compares cards and counts
# with the live catalog. The CRM database is opened read-only through a stand-in db module. Nothing is written.
SMOKE = r"""
import json, re, sqlite3, sys, types
after, root = sys.argv[1], sys.argv[2]
sys.path[:0] = [after, root]
fake = types.ModuleType('db')
fake.connect = lambda: sqlite3.connect('file:%s/crm.db?mode=ro' % root, uri=True, timeout=5)
sys.modules['db'] = fake
import catalog_design_guard as cdg, ua_stage_catalog_sync as scs, ua_site_counters as usc, ua_country_site as cs
con = sqlite3.connect('file:%s/crm.db?mode=ro' % root, uri=True, timeout=5)
con.row_factory = sqlite3.Row
rows = [dict(r) for r in con.execute('SELECT * FROM cars WHERE published=1 ORDER BY id')]
con.close()
golden = open(after + '/catalog_design_golden.html', encoding='utf-8').read()
live = open(root + '/video/katalog.html', encoding='utf-8').read()
photos = {}
for row in rows:
    code = str(row.get('auto_number') or '').upper()
    try:
        photos[code] = cdg.extract_main_photo(open('%s/video/%s.html' % (root, code), encoding='utf-8').read(), code)
    except OSError:
        pass
built = cdg.build_catalog(golden, rows, photos)
audit = cdg.audit_catalog(built, rows, golden)
by_code = {str(r['auto_number']).upper(): r for r in rows if r.get('auto_number')}
_, sync_live = scs.patch_catalog_stages(live, by_code)
_, sync_built = scs.patch_catalog_stages(built, by_code)
_, counts = usc.catalog_snapshot(built)
usc.patch_catalog(built, counts)
_, live_counts = usc.catalog_snapshot(live)
article = re.compile(r'<article\b[^>]*\bcatalog-card\b.*?</article\s*>', re.S)
strip = lambda block: re.sub(r' data-country="(?:korea|japan)"', '', block)
same = sum(1 for x, y in zip(sorted(map(strip, article.findall(built))), sorted(article.findall(live))) if x == y)
print(json.dumps({
    'audit': audit['status'], 'audit_errors': audit['errors'], 'counts': counts, 'live_counts': live_counts,
    'cards': len(article.findall(built)), 'cards_same_as_live': same,
    'countries': re.findall(r'<article\b[^>]*\bdata-country="(korea|japan)"', built).count('korea'),
    'row': built.count('class="ua-country-row"'),
    'korea_button': re.findall(r'data-f="korea"[^>]*>([^<]*)<', built),
    'sync_changes_live': sync_live, 'sync_changes_built': sync_built,
    'chip_korea': cs.country_chip({'id': -1}),
    'japan_texts': [cs.stage_chip({'id': None}, 'Выкуплена · стоянка в Корее'), cs.current_stage(1, 'Выкуплен · стоянка в Корее', 'japan')],
}, ensure_ascii=False))
"""


def smoke(directory):
    result = subprocess.run(['python3.10', '-B', '-c', SMOKE, str(directory/'after'), str(ROOT)],
                            capture_output=True, text=True, timeout=240, check=False)
    if result.returncode != 0:
        raise DeploymentError('SMOKE:'+result.stderr.strip()[-300:])
    value = json.loads(result.stdout.strip().splitlines()[-1])
    if (value['audit'] != 'PASS' or value['counts'] != value['live_counts'] or value['countries'] != value['cards']
            or value['cards'] != value['counts']['all'] or value['row'] != 1
            or value['korea_button'] != ['Выкуплены · %d' % value['counts']['korea']]
            or value['sync_changes_live'] or value['sync_changes_built']):
        raise DeploymentError('SMOKE_RESULT')
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
    home(False)


def home(new):
    """Home page titles: the new ones (install) or the old ones back (rollback), only where the other ones stand."""
    path=ROOT/edit_home.NAME
    text=read(path).decode('utf-8')
    pairs=edit_home.PAIRS if new else tuple((b,a) for a,b in edit_home.PAIRS)
    done=sum(text.count(b) for _,b in pairs)
    if done==len(pairs): return
    if done or any(text.count(a)!=1 for a,_ in pairs): raise DeploymentError('HOME_TITLES_SHAPE')
    for a,b in pairs: text=text.replace(a,b)
    atomic(path,text.encode('utf-8'),stat.S_IMODE(path.stat().st_mode))


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
                        home(True)
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
            if str(path.relative_to(ROOT))==edit_home.NAME: continue  # changed by this release (home titles)
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


def republish():
    """The existing publishers with the new code: every card page (stranica, as the CRM self-check), then both catalogs
    (publikaciya.obnovit_katalog, as the publish button). They take the publication locks themselves."""
    started=time.monotonic(); steps={}
    for name,code in (('cards','import stranica; stranica.main()'),
                      ('catalog','import publikaciya; publikaciya.obnovit_katalog()')):
        result=subprocess.run(['python3.10','-c',"import sys; sys.path.insert(0, '/home/Carix'); "+code],
                              cwd=str(ROOT),capture_output=True,text=True,timeout=330,check=False)
        last=(result.stderr.strip().splitlines() or [''])[-1]
        steps[name]={'returncode':result.returncode,'error':re.sub(r'\d{6,}','[N]',last)[:160] if result.returncode else ''}
        if result.returncode: return {'status':'FAIL','steps':steps}
    return {'status':'PASS','steps':steps,'seconds':round(time.monotonic()-started)}


def pages_check():
    """After the rebuild: one country chip on every published card, the country on every catalog card, the row and
    the «Выкуплены» filter once in both catalogs, the new home titles."""
    with closing(sqlite3.connect((ROOT/'crm.db').as_uri()+'?mode=ro',uri=True,timeout=5)) as con:
        codes=[c for (c,) in con.execute("SELECT auto_number FROM cars WHERE published=1 AND status IN "
                                         "('kr_bought','sea_loaded','ge_waiting','ua_arrived') ORDER BY auto_number")]
    errors=[]
    for code in codes:
        page=read(ROOT/'video'/(code+'.html')).decode('utf-8')
        if page.count('>🇰🇷 Автомобиль из Кореи<')+page.count('>🇯🇵 Автомобиль из Японии<')!=1:
            errors.append('CARD_CHIP:'+code)
    for folder in ('video','site'):
        page=read(ROOT/folder/'katalog.html').decode('utf-8')
        cards=len(re.findall(r'<article\b[^>]*\bcatalog-card\b',page))
        if (page.count('class="ua-country-row"')!=1 or len(re.findall(r'data-f="korea"[^>]*(?:>Выкуплены|>Викуплені) · \d+<',page))!=1
                or len(re.findall(r'<article\b[^>]*\bdata-country="(?:korea|japan)"',page))!=cards or cards!=len(codes)):
            errors.append('CATALOG:'+folder)
    home_page=read(ROOT/edit_home.NAME).decode('utf-8')
    if any(home_page.count(new)!=1 for _,new in edit_home.PAIRS): errors.append('HOME_TITLES')
    if errors: raise DeploymentError('PAGES_CHECK:'+','.join(errors[:8]))
    return {'cards':len(codes),'catalogs':2,'home_titles':2}


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
                value.update(lifecycle(args.mode, args.run, args.plan, args.backup))
                if value.get('status') == 'PASS':
                    value['republish'] = republish()
                    if value['republish']['status'] != 'PASS':
                        value.update(status='FAIL', error='REPUBLISH_FAILED')
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
