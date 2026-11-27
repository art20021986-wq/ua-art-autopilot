"""Bounded USA-LOTS-FIX-002 release (the fixed IAAI listing reader: only usa_auction/pages.py, selection.py and job.py
change; no page, task or Korea change); preserve live data and pending requests."""
import argparse
import datetime
from contextlib import closing, contextmanager
import fcntl
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

from deployment_transport import API, USA_JOB_COMMAND, canonical, sha
from candidate_builder import INSTALLED_SHA256, SOURCE_FILES, DEPENDENCY_SHA256, build, is_page

ROOT = Path('/home/Carix')
HERE = Path(__file__).resolve().parent
# The account's PythonAnywhere disk quota (owner's Files page, 2026-10-20:
# "8.2 GB of your 35.0 GB quota"); decimal GB is the conservative reading.
QUOTA_BYTES = 35 * 10**9
PAGES = ('video/katalog.html', 'site/katalog.html', 'video/index.html', 'site/index.html')
# The USA job's outputs (video/usa/lots.json, feed.json, gallery/, lots/, usa_auction_data/) are valid data of the
# installed collector: neither the install nor a rollback removes them. A rollback restores the three previous files only.
USA_LOCK = '.usa_auction_job.lock'
USA_JOB = {'command': USA_JOB_COMMAND, 'interval': 'hourly'}
# USA-LOTS-FIX-002 leaves these as they are (checked before and after, and before a rollback), with every installed
# collector file it does not replace (candidate_builder.INSTALLED_SHA256).
UNTOUCHED = ('video/usa.html', 'video/korea.html', 'video/japan.html', 'japan_ticker_job.py',
             'japan_auction/__init__.py', 'japan_auction/job.py', 'japan_auction/lot_page.py', 'japan_auction/money.py',
             'japan_auction/photos.py', 'japan_auction/search.py', 'japan_auction/views.py')
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
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix='.ulfix2-')
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
    candidate = build(source, dependencies, sha=sha)
    for name, value in candidate.items():
        if name.endswith('.py'):
            compile(value, name, 'exec')
    protected_names = set(DEPENDENCY_SHA256) | {
        'start_safe.py','run_all.py','team_bot.py','lead_bot.py','db.py',
        'publication_fence.py','ua_public_freshness.py',
        'ua_site_counters.py','catalog_design_guard.py','cars_schema.py',
        'publish_transaction_guard.py','ua_spec_permanent.py',
        'ua_seo_sitemap.py','ua_seo_catalog.py',
        'ua_order/preference_summary.py','ua_order/storage.py',
        'ua_crm_public_sync.py','ua_google_tag.py','cars_ui.py','ua_finance_partners.py','ua_card_lang_job.py',
    } | set(UNTOUCHED) | (set(INSTALLED_SHA256) - set(candidate))
    protected = {name:sha(read(ROOT/name)) for name in sorted(protected_names)}
    files = {}
    for name,value in sorted(candidate.items()):
        before = source.get(name)
        if before is None:
            raise DeploymentError('NOT_INSTALLED:'+name)  # the fix only replaces installed files
        mode = stat.S_IMODE((ROOT/name).stat().st_mode)
        files[name] = {'before':sha(before),
                       'after':sha(value), 'mode':mode, 'page':is_page(name)}
        atomic(directory/'before'/name,before,mode)
        atomic(directory/'after'/name,value,mode)
    # A source-only plan stays valid across legitimate operator edits. Actual
    # CRM/page snapshots are captured again under locks at the write boundary.
    plan = {'schema_version':'TICKER-FIX4-INSTALL-1','files':files,'usa_job':USA_JOB,
            'protected':protected,'crm_write':False,'site_write':True,
            'site_scope':'usa_auction/pages.py, selection.py, job.py only (IAAI listing values read from their title attributes; model spellings such as MODEL-3; an unreadable listing stops the run; listings read before the fix are read again); the USA hourly task runs within minutes; no page, task, korea_auction, japan_auction or CRM changes; the USA outputs stay',
            'pending_requests_preserved':True}
    atomic(directory/'plan.json',canonical(plan))
    return plan


def smoke(directory):
    """The fixed collector imports on the server's Python with the installed fetch.py, views.py and __init__.py, reads a
    listing written as IAAI's live one (each value in a title attribute) and keeps its published lots when IAAI refuses;
    no network is used."""
    after = directory/'after'
    for name in read_names(directory):
        compile(read(after/name), name, 'exec')
    with tempfile.TemporaryDirectory() as folder:
        image = Path(folder)/'image'
        for name in sorted(INSTALLED_SHA256):
            if name.startswith('usa_auction/'):
                value = read(after/name) if (after/name).exists() else read(ROOT/name)
                if not (after/name).exists() and sha(value) != INSTALLED_SHA256[name]:
                    raise DeploymentError('SMOKE_SOURCE_CHANGED:'+name)
                atomic(image/name, value, 0o644)
        for name in [m for m in sys.modules if m.split('.')[0] == 'usa_auction']:
            del sys.modules[name]  # only the image's collector is checked
        sys.path.insert(0, str(image))
        try:
            value = usa_checks(Path(folder)/'run')
        finally:
            sys.path.remove(str(image))
            for name in [m for m in sys.modules if m.split('.')[0] == 'usa_auction']:
                del sys.modules[name]
    if not all(value.values()):
        raise DeploymentError('SMOKE_RESULT:'+json.dumps(value))
    return value


def listing_block(lot_id, year, damage, start):
    """One lot of a make-and-model listing as IAAI writes it (live 27.11): each value in its item's title attribute."""
    item = '<li class="data-list__item"><span class="data-list__value" title="%s: %s">%s</span></li>'
    return ('<div class="table-row"><a href="/VehicleDetail/%s~US"><img></a><h4><a href="/VehicleDetail/%s~US">'
            '%d TOYOTA RAV4 XLE</a></h4><ul>' % (lot_id, lot_id, year)
            + item % ('Primary Damage', damage, damage) + item % ('Odometer', '48,000 mi (Actual)', '48,000')
            + item % ('Start Code', start, start) + '</ul></div>')


LISTING = ('<html><body>' + listing_block('41000001', 2021, 'Minor Dent/Scratches', 'Run &amp; Drive')
           + listing_block('41000002', 2020, 'Normal Wear &amp; Tear', 'Stationary') + '</body></html>')
LOT_PAGE = ('<div>Primary Damage: Minor Dent/Scratches Start Code: Run &amp; Drive Odometer: 48,000 mi (Actual) '
            'Auction Date and Time: Wed Dec 2, 9:30am (CST) Actual Cash Value: $24,900 USD</div>'
            '<script>var u="https://vis.iaai.com/dimensions?imageKeys=41000001~SID~B1~S0~I1";</script>')


def usa_checks(folder):
    """USA-LOTS-FIX-002 on the server's Python, from fixtures only (an answering client, then one IAAI «refuses»)."""
    from usa_auction import fetch, job, pages, selection

    class Fixture:
        def __init__(self, refuse=False):
            self.refuse = refuse

        def _get(self, url):
            if self.refuse:
                raise fetch.Closed('SMOKE_NO_NETWORK')
            for part, answer in (('sitemap_index', '<loc>https://www.iaai.com/x/ms-sitemapMakeModel1.xml</loc>'),
                                 ('MakeModel1', '<urlset><url><loc>https://www.iaai.com/Vehiclelisting/TOYOTA/RAV4/</loc>'
                                                '</url></urlset>'),
                                 ('Vehiclelisting/TOYOTA/RAV4', LISTING), ('VehicleDetail/41000001', LOT_PAGE),
                                 ('dimensions', {'keys': [{'K': '41000001~SID~B1~S0~I1'}]}), ('resizer', b'jpeg')):
                if part in url:
                    return answer
            raise OSError('404')

        page = json = photo = _get

    lots = pages.listing(LISTING, 'TOYOTA', 'RAV4')
    now = datetime.datetime(2026, 11, 28, 9, 0, tzinfo=datetime.timezone.utc)
    empty = job.run(Fixture(True), {'models': {}, 'models_at': '', 'listings': {}, 'pages': {}}, now, folder/'empty')
    data = {'models': {}, 'models_at': '', 'listings': {}, 'pages': {}}
    first = job.run(Fixture(), data, now, folder/'usa')
    shown = json.loads((folder/'usa'/'lots.json').read_bytes())['lots']
    for entry in data['listings'].values():
        entry['at'] = '2026-11-01T00:00Z'  # due again: IAAI is asked and refuses
    refused = job.run(Fixture(True), data, now, folder/'usa')
    kept = json.loads((folder/'usa'/'lots.json').read_bytes())['lots']
    blank = {'models': {'toyota|rav4': 'https://www.iaai.com/Vehiclelisting/TOYOTA/RAV4/'}, 'models_at': job.stamp(now),
             'listings': {}, 'pages': {}}

    class Unreadable(Fixture):
        def _get(self, url):
            return LISTING.replace('Primary Damage', 'Something')

        page = _get

    return {'usa_imports': callable(getattr(pages, 'titled', None)) and callable(job.run),
            'usa_listing_titles': [(l['id'], l['damage'], l['odometer_mi'], l['runs']) for l in lots]
                                  == [('41000001', 'Minor Dent/Scratches', 48000, True),
                                      ('41000002', 'Normal Wear & Tear', 48000, False)],
            'usa_popular': selection.popular('TESLA', 'MODEL-3') and selection.popular('TOYOTA', 'RAV4')
                           and not selection.popular('TOYOTA', 'TUNDRA'),
            'usa_offline_run': empty['stop'] == 'SMOKE_NO_NETWORK' and empty['shown'] == 0
                               and json.loads((folder/'empty'/'feed.json').read_bytes())['items'] == [],
            'usa_fixture_run': first['stop'] == '' and first['shown'] == 1 and [l['id'] for l in shown] == ['41000001'],
            'usa_refusal_keeps_lots': refused['stop'] == 'SMOKE_NO_NETWORK' and refused['shown'] == 1 and kept == shown,
            'usa_unreadable_stops': job.run(Unreadable(), blank, now, folder/'blank')['stop'] == 'LISTING_UNREADABLE',
            'usa_gentle': fetch.UA == 'UAArtAutopilot/1.0 (+https://uaart.com.ua)' and fetch.PAUSE == 4
                          and job.REQUESTS == 60,
            'usa_paths': (str(job.OUT), str(job.DATA), str(job.LOCK))
                         == ('/home/Carix/video/usa', '/home/Carix/usa_auction_data', '/home/Carix/'+USA_LOCK)}


def read_names(directory):
    return sorted(json.loads(read(directory/'plan.json'))['files'])


def verify_files(plan, after):
    for relative,item in plan['files'].items():
        expected = item['after' if after else 'before']
        path = ROOT/relative
        if expected is None:
            if path.exists() or path.is_symlink():
                raise DeploymentError('UNEXPECTED_FILE:'+relative)
        elif sha(read(path)) != expected and not (after and item.get('page') and has_mark(path)):
            # The home page the CRM sync rewrote after the install still carries the mark (inject_html adds it).
            raise DeploymentError('FILE_CHANGED:'+relative)
    for relative,digest in plan['protected'].items():
        if sha(read(ROOT/relative)) != digest:
            raise DeploymentError('PROTECTED_CHANGED:'+relative)


def has_mark(path):
    return False  # no page is part of this release


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


@contextmanager
def usa_job_stopped():
    """USA-LOTS-001: wait for a USA run still working (its lock) so it writes nothing after the rollback."""
    lock = open(ROOT/USA_LOCK, 'a')
    deadline = time.monotonic()+420
    try:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise DeploymentError('USA_JOB_BUSY')
                time.sleep(1)
        yield
    finally:
        lock.close()


def restore(directory, plan):
    # Every hourly task stays (after a rollback the USA task runs the previous collector again); the USA outputs stay.
    # Called only while usa_job_stopped() is held.
    for relative,digest in plan['protected'].items():
        if sha(read(ROOT/relative)) != digest:
            raise DeploymentError('PROTECTED_CHANGED:'+relative)
    for relative,item in plan['files'].items():
        path=ROOT/relative
        current=sha(read(path)) if path.exists() else None
        if path.is_symlink() or current not in (item['before'],item['after']):
            raise DeploymentError('ROLLBACK_CONCURRENT_CHANGE:'+relative)
    for relative,item in reversed(list(plan['files'].items())):
        atomic(ROOT/relative,read(directory/'before'/relative),item['mode'])
    for relative,item in plan['files'].items():
        if sha(read(ROOT/relative)) != item['before']:
            raise DeploymentError('FILE_CHANGED:'+relative)
    cache=ROOT/'usa_auction'/'__pycache__'
    if cache.is_dir() and not cache.is_symlink():
        shutil.rmtree(cache)


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
            # USA-LOTS-FIX-002: the files the USA job imports change only while no USA run works (its lock), taken before
            # the bot pause so a finishing USA run does not keep the bot paused
            with usa_job_stopped():
                api.set_bot(False); no_bot_processes()
                with writer_exclusion():
                    before=protected_data(plan)
                    if mode=='rollback' or applied:
                        restore(directory,plan)
                        result={'status':'PASS' if mode=='rollback' else 'FAIL',
                                'restored':True,'interrupted_install':applied}
                    else:
                        verify_files(plan,False); usa_job=api.usa_job()
                        state.update(stage='APPLYING',data_before=before)
                        atomic(journal,canonical(state));applied=True
                        try:
                            for relative in plan['files']:
                                atomic(ROOT/relative,read(directory/'after'/relative),plan['files'][relative]['mode'])
                            verify_files(plan,True)
                            # the existing USA hourly task runs the fixed collector within minutes (no task is created)
                            job={'usa':dict(usa_job,run_soon=api.run_soon(delay=2))}
                            if protected_data(plan)!=before: raise DeploymentError('PROTECTED_DATA_CHANGED_DURING_INSTALL')
                            result={'status':'PASS','installed':True,'job':job}
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
                    with usa_job_stopped(), writer_exclusion(): restore(directory,plan)
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
                # fails closed unless the USA hourly task is there as installed (exactly one, hourly, enabled)
                value['schedule'] = {'usa_job': API(os.environ.get('API_TOKEN')).usa_job()}
            elif args.mode == 'backup':
                value.update(backup(args.run, args.plan), status='PASS')
            elif args.mode in ('install', 'rollback'):
                value.update(lifecycle(args.mode, args.run, args.plan, args.backup))
            else:
                manifest, result = installed(args.run, args.plan, args.backup)
                api = API(os.environ.get('API_TOKEN'))
                value.update(status='PASS',job=result['job'],usa_job=api.usa_job(),backup_manifest_sha256=args.backup,sync=sync_state(),
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
