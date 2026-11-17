"""Bounded AUTOSEARCH-002 release (manager search requests on the site, WhatsApp group messages in one tap, CRM statistics); preserve live data and pending requests."""
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
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix='.autosearch2-')
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
        if name.endswith('.py') and value is not None:
            compile(value, name, 'exec')
    protected_names = set(DEPENDENCY_SHA256) | {
        'start_safe.py','run_all.py','team_bot.py','client_ui.py','stranica.py','master_card.py','cars_ui.py',
        'publication_fence.py','ua_public_freshness.py',
        'ua_site_counters.py','catalog_design_guard.py','cars_schema.py',
        'publish_transaction_guard.py','ua_spec_permanent.py',
        'ua_seo_sitemap.py','ua_seo_catalog.py',
        'ua_order/preference_summary.py','ua_order/storage.py',
        'ua_crm_public_sync.py','ua_google_tag.py','ua_finance_crm.py','ua_finance_partners.py','ua_card_lang_job.py',
    }
    protected = {name:sha(read(ROOT/name)) for name in sorted(protected_names)}
    files = {}
    for name,value in sorted(candidate.items()):
        before = source.get(name)
        mode = stat.S_IMODE((ROOT/name).stat().st_mode) if before is not None else 0o644
        files[name] = {'before':sha(before) if before is not None else None,
                       'after':sha(value) if value is not None else None, 'mode':mode}
        if before is None and ((ROOT/name).exists() or (ROOT/name).is_symlink()):
            raise DeploymentError('NEW_FILE_EXISTS:'+name)
        if before is not None: atomic(directory/'before'/name,before,mode)
        if value is not None: atomic(directory/'after'/name,value,mode)
    # A source-only plan stays valid across legitimate operator edits. Actual
    # CRM/page snapshots are captured again under locks at the write boundary.
    plan = {'schema_version':'AUTOSEARCH2-INSTALL-1','files':files,
            'protected':protected,'crm_write':False,'site_write':True,
            'site_scope':'AUTOSEARCH-002: manager search requests on the site and one-tap WhatsApp group messages; ua_lot_alerts.py, ua_lot_alerts_web.py, ua_lot_alerts_view.py replaced, ua_lot_alerts_whatsapp.py and ua_lot_alerts_crm.py new, ua_lot_alerts_bot.py removed; ua_auction_clients_bot.py (requests per viewer, «👔 Права менеджера на сайте» for the owner), ua_auction_web.py (docstring), lead_bot.py back to the version before AUTOSEARCH-001; video/kabinet.html: the client «🔔 Автопошук» removed, the manager section added; alerts.db: AUTOSEARCH-001 tables dropped on first use, new tables created; bot paused and resumed, web app reloaded; no CRM or client record change',
            'pending_requests_preserved':True}
    atomic(directory/'plan.json',canonical(plan))
    return plan


# Runs in a separate python3.10 (the bots' interpreter) with the candidate modules first on the path and the live
# server root: the modules import with the installed telegram library; every record goes to a temporary database in the
# server's local /tmp; matching runs on the live lot list; the CRM screens build from the live clients and staff (read
# only, counts only); the manager messages go to a stand-in bot; the job registers on a bot application never started.
SMOKE = r"""
import asyncio, faulthandler, json, sqlite3, sys, tempfile, pathlib, time
faulthandler.dump_traceback_later(150, exit=True)  # a hang prints where it stands, then stops the smoke
after, root = sys.argv[1], sys.argv[2]
sys.path[:0] = [after, root]
START = time.monotonic()
def stage(name):
    sys.stderr.write('STAGE %s %.1fs\n' % (name, time.monotonic() - START)); sys.stderr.flush()
stage('start')
import ua_lot_alerts as alerts
live = {}
if alerts.DB.exists():  # what AUTOSEARCH-001 left (read only), reported for the owner
    with sqlite3.connect(alerts.DB.as_uri() + '?mode=ro', uri=True, timeout=5) as c:
        for table in ('searches', 'links', 'codes', 'sent', 'views'):
            try:
                live[table] = c.execute('SELECT COUNT(*) FROM %s' % table).fetchone()[0]
            except sqlite3.Error:
                live[table] = None
stage('live_counts')
class Bot:
    def __init__(self):
        self.sent = []
    async def send_message(self, chat, text, **kw):
        self.sent.append((chat, text, kw.get('reply_markup')))
with tempfile.TemporaryDirectory(dir='/tmp') as folder:  # the server's local /tmp, not the network home disk
    alerts.DB = pathlib.Path(folder) / 'alerts.db'
    import ua_lot_alerts_web as web, ua_lot_alerts_view as alerts_view, ua_lot_alerts_crm as crm_job
    import ua_lot_alerts_whatsapp as whatsapp
    import ua_auction_web, ua_auction_clients as store, ua_auction_clients_bot as crm
    stage('modules')
    options = web.options()
    maker = max(options['makers'], key=lambda m: len(options['makers'][m])) if options['makers'] else ''
    people = store.all_clients()
    manager_phone = '+380000000001'
    alerts.set_manager(manager_phone, 1, 'Smoke', True)
    own = alerts.own_clients(alerts.manager(manager_phone), people, alerts.manager_phones())
    client = people[0]['phone'] if people else '+380000000002'
    rid = alerts.add_request(client, 1, 'https://chat.whatsapp.com/AbCdEfGhIj123', {'maker': maker})
    stage('records')
    bot = Bot()
    sent = asyncio.run(crm_job.check(bot))
    again = asyncio.run(crm_job.check(bot))
    stage('manager_messages')
    status, body = web.handle('alerts', {}, {'phone': manager_phone})
    home = crm._home_screen(None)
    screen = crm._alerts_screen(None)
    cards = [crm._client_screen(c['phone'], None) for c in people[:5]]
    role = crm._role_screen(people[0]['phone']) if people else {'buttons': [[None]]}
    stage('crm_screens')
    from telegram.ext import ApplicationBuilder
    app = ApplicationBuilder().token('123:smoke').build()
    crm_job.register(app)
    stage('job')
    after_dir = pathlib.Path(after)
    page = (after_dir / 'video/kabinet.html').read_text(encoding='utf-8')
    lead = (after_dir / 'lead_bot.py').read_text(encoding='utf-8')
    welcome = bot.sent[0][1] if bot.sent else ''
    button = bot.sent[0][2].inline_keyboard[0][0].url if bot.sent else ''
    print(json.dumps({'live_alerts_db': live, 'lots': len(crm_job.lots()[1]), 'makers': len(options['makers']),
                      'maker': maker, 'clients': len(people), 'own_clients': len(own), 'sent': sent, 'again': again,
                      'welcome_first': 'Здравствуйте! Создан запрос' in welcome,
                      'share_button': button.startswith('https://wa.me/?text='),
                      'api': [status, len(body.get('requests', [])), len(body.get('clients', []))],
                      'home_buttons': [row[0][1] for row in home['buttons']], 'screen_ok': '🔔 Автопоиск' in screen['text'],
                      'cards': len(cards), 'role_choices': len(role['buttons']) - 1,
                      'job': bool(app.job_queue and app.job_queue.get_jobs_by_name(crm_job.JOB)),
                      'cabinet_page': page.count('id="mr-form"') == 1 and 'ua-autosearch-v1' not in page,
                      'lead_clean': 'ua_lot_alerts_bot' not in lead}, ensure_ascii=False))
"""


def smoke(directory):
    try:
        result = subprocess.run(['python3.10', '-B', '-c', SMOKE, str(directory/'after'), str(ROOT)],
                                capture_output=True, text=True, timeout=240, check=False, cwd=str(directory))
    except subprocess.TimeoutExpired as error:
        stages = (error.stderr or b'')
        stages = stages.decode(errors='replace') if isinstance(stages, bytes) else stages
        raise DeploymentError('SMOKE_TIMEOUT:'+' | '.join(stages.strip().splitlines()[-12:])[-700:])
    if result.returncode != 0:
        raise DeploymentError('SMOKE:'+' | '.join(result.stderr.strip().splitlines()[-14:])[-700:])
    value = json.loads(result.stdout.strip().splitlines()[-1])
    value['stages'] = [line for line in result.stderr.splitlines() if line.startswith('STAGE ')][-12:]
    if (not value.get('lots') or not value.get('sent') or value.get('again') != 0
            or value.get('welcome_first') is not True or value.get('share_button') is not True
            or value.get('api', [''])[0] != '200 OK' or value.get('own_clients') != value.get('clients')
            or value.get('home_buttons') != ['ac:new', 'ac:list', 'ac:days', 'ac:mgrs', 'ac:alerts', 'menu']
            or value.get('screen_ok') is not True or value.get('job') is not True
            or value.get('cabinet_page') is not True or value.get('lead_clean') is not True):
        raise DeploymentError('SMOKE_RESULT:'+json.dumps(value, ensure_ascii=False)[:600])
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
                    restore(directory,plan)
                    result={'status':'PASS' if mode=='rollback' else 'FAIL',
                            'restored':True,'interrupted_install':applied}
                else:
                    verify_files(plan,False)
                    state.update(stage='APPLYING',data_before=before)
                    atomic(journal,canonical(state));applied=True
                    try:
                        for relative in plan['files']:
                            if plan['files'][relative]['after'] is None:
                                (ROOT/relative).unlink()
                            else:
                                atomic(ROOT/relative,read(directory/'after'/relative),plan['files'][relative]['mode'])
                        verify_files(plan,True)
                        if protected_data(plan)!=before: raise DeploymentError('PROTECTED_DATA_CHANGED_DURING_INSTALL')
                        result={'status':'PASS','installed':True}
                    except BaseException:
                        restore(directory,plan);applied=False
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



def sync_state():
    """The CRM public sync's failure picture (retry count per card and the last success), read only."""
    try:
        value = json.loads(read(ROOT/'.crm_public_sync_state.json'))
    except Exception as error:
        return {'error': type(error).__name__}
    retry = value.get('retry') or {}
    return {'retry_cards': len(retry), 'ua115_retries': sum('UA115' in str(v.get('error', '')) for v in retry.values()),
            'last_success': value.get('last_success')}


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
    # A file another program removes while du walks the tree (a SQLite -journal) is only "No such file":
    # du still totals everything else; any other error refuses the measurement.
    vanished = all(line.endswith('No such file or directory') for line in result.stderr.strip().splitlines())
    if (result.returncode != 0 and not (result.returncode == 1 and result.stderr.strip() and vanished)) or len(sizes) != 2:
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
                value.update(status='PASS', plan=plan, plan_sha256=sha(canonical(plan)), smoke=smoke(work/'preview'), sync=sync_state())
                value['storage_probe'] = storage_probe()
            elif args.mode == 'backup':
                value.update(backup(args.run, args.plan), status='PASS')
            elif args.mode in ('install', 'rollback'):
                value.update(lifecycle(args.mode, args.run, args.plan, args.backup))
            else:
                manifest, result = installed(args.run, args.plan, args.backup)
                value.update(status='PASS',backup_manifest_sha256=args.backup,sync=sync_state(),
                             plan_sha256=args.plan,crm_unchanged=True,protected_files_unchanged=True,
                             preservation_scope=result['preservation_scope'],
                             code_sha256={name: item['after'] for name, item in manifest['plan']['files'].items()})
            value['safe_to_stop'] = True
        except Exception as error:
            value['error'] = type(error).__name__+':'+str(error)[:900]
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
