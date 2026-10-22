"""Bounded fuel normalization: compare-and-set of the CRM fuel field only; preserve every other value."""
import argparse
from contextlib import closing, contextmanager
import datetime
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

from deployment_transport import API, canonical, sha
from fuel_vocabulary import normalize

ROOT = Path('/home/Carix')
HERE = Path(__file__).resolve().parent
# The account's PythonAnywhere disk quota (owner's Files page, 2026-10-20).
QUOTA_BYTES = 35 * 10**9
PROTECTED = ('start_safe.py', 'run_all.py', 'team_bot.py', 'lead_bot.py', 'db.py', 'cars_schema.py',
             'publication_fence.py', 'ua_public_freshness.py', 'ua_site_counters.py', 'catalog_design_guard.py',
             'stranica.py', 'master_card.py', 'publish_transaction_guard.py', 'ua_crm_public_sync.py',
             'ua_seo_metadata.py', 'ua_seo_sitemap.py', 'ua_seo_catalog.py', 'ua_seo_index.py', 'ua_seo_landings.py')


class DeploymentError(RuntimeError):
    pass


def read(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 256*1024*1024:
        raise DeploymentError('UNSAFE_FILE:'+path.name)
    if path.resolve() != path:
        raise DeploymentError('NONCANONICAL_PATH')
    return path.read_bytes()


def atomic(path, value, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix='.fuelnorm-')
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
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
    if 'fuel' not in columns or 'auto_number' not in columns:
        raise DeploymentError('CRM_SCHEMA')
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def read_only():
    return closing(sqlite3.connect((ROOT/'crm.db').as_uri()+'?mode=ro', uri=True, timeout=5))


def row_digest(value):
    return sha(canonical(value))


def changes_for(current):
    """Rows whose fuel is a known spelling of another canonical value."""
    found = []
    for row in current:
        target = normalize(row['fuel'])
        if target is not None and target != row['fuel']:
            found.append({'id': row['id'], 'auto_number': row['auto_number'], 'published': row.get('published'),
                          'before': row['fuel'], 'after': target})
    return found


def prepare():
    with read_only() as connection:
        current = rows(connection)
    values = sorted({str(r['fuel']) for r in current if r['fuel'] is not None})
    return {'schema_version': 'FUEL-NORMALIZE-INSTALL-1', 'changes': changes_for(current),
            'unknown_values': [v for v in values if normalize(v) is None],
            'protected': {name: sha(read(ROOT/name)) for name in PROTECTED if (ROOT/name).exists()},
            'crm_write': True, 'crm_scope': 'cars.fuel of the listed rows only',
            'site_write': 'the existing public sync worker republishes changed published cards after the bot resumes'}


def verify_protected(plan):
    for name, digest in plan['protected'].items():
        if sha(read(ROOT/name)) != digest:
            raise DeploymentError('PROTECTED_CHANGED:'+name)


def load_backup(digest):
    directory = HERE/'backups'/digest
    manifest = json.loads(read(directory/'manifest.json'))
    if sha(canonical(manifest)) != digest:
        raise DeploymentError('BACKUP_HASH')
    if sha(read(directory/'crm.db')) != manifest['database_backup_sha256']:
        raise DeploymentError('DATABASE_BACKUP_CHANGED')
    if sha(canonical(manifest['plan'])) != manifest['plan_sha256']:
        raise DeploymentError('BACKUP_PLAN_HASH')
    return directory, manifest


def backup(run_id, expected_plan):
    plan = prepare()
    if sha(canonical(plan)) != expected_plan:
        raise DeploymentError('LIVE_PLAN_DRIFT')
    workspace = HERE/'runs'/run_id/'backup-prepared'
    workspace.mkdir(parents=True, exist_ok=False, mode=0o700)
    database = workspace/'crm.db'
    with database.open('xb'):
        os.chmod(database, 0o600)
    with read_only() as source, closing(sqlite3.connect(database)) as target:
        deadline = time.monotonic()+60
        def progress(status, remaining, total):
            if time.monotonic() >= deadline:
                raise DeploymentError('BACKUP_TIMEOUT')
        source.backup(target, pages=256, progress=progress)
        if target.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise DeploymentError('BACKUP_DATABASE_VERIFY')
        snapshot = row_digest(rows(target))
    manifest = {'plan': plan, 'plan_sha256': expected_plan, 'run_id': run_id,
                'crm_rows_sha256': snapshot, 'database_backup_sha256': sha(read(database))}
    digest = sha(canonical(manifest))
    atomic(workspace/'manifest.json', canonical(manifest))
    target = HERE/'backups'/digest
    target.parent.mkdir(mode=0o700, exist_ok=True)
    os.rename(workspace, target)
    load_backup(digest)
    return {'backup_manifest_sha256': digest, 'backup': str(target), 'plan_sha256': expected_plan}


@contextmanager
def writer_exclusion():
    """The worker lock, the publication fence and a write transaction; the caller commits."""
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
        fence = load(ROOT/'publication_fence.py', 'fuelnorm_publication_fence')
        with fence.publication_fence(timeout=30):
            with closing(sqlite3.connect((ROOT/'crm.db').as_uri()+'?mode=rw', uri=True, timeout=5)) as connection:
                connection.execute('BEGIN IMMEDIATE')
                try:
                    yield connection
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


def apply(connection, changes, forward):
    """Compare-and-set each listed fuel; every other CRM value must stay identical. Idempotent."""
    before = rows(connection)
    by_id = {row['id']: row for row in before}
    for change in changes:
        old, new = (change['before'], change['after']) if forward else (change['after'], change['before'])
        row = by_id.get(change['id'])
        if row is None or row['auto_number'] != change['auto_number']:
            raise DeploymentError('ROW_IDENTITY:'+str(change['auto_number']))
        if row['fuel'] == new:
            continue
        if row['fuel'] != old:
            raise DeploymentError('CONCURRENT_CHANGE:'+str(change['auto_number']))
        if connection.execute('UPDATE cars SET fuel=? WHERE id=? AND fuel=?', (new, change['id'], old)).rowcount != 1:
            raise DeploymentError('UPDATE_COUNT:'+str(change['auto_number']))
    after = rows(connection)
    expected = {c['id']: (c['after'] if forward else c['before']) for c in changes}
    restored = [dict(r, fuel=by_id[r['id']]['fuel']) if r['id'] in expected else r for r in after]
    if row_digest(restored) != row_digest(before) or any(r['fuel'] != expected[r['id']] for r in after if r['id'] in expected):
        raise DeploymentError('UNEXPECTED_CRM_CHANGE')
    return row_digest(after)


def pending_pages():
    pages = {}
    for folder in ('video', 'site'):
        for path in sorted((ROOT/folder).glob('*.html')):
            pages[str(path.relative_to(ROOT))] = sha(read(path))
    return pages


def lifecycle(mode, run_id, expected_plan, backup_sha):
    directory, manifest = load_backup(backup_sha)
    if manifest['plan_sha256'] != expected_plan or manifest['run_id'] != run_id:
        raise DeploymentError('INSTALL_PLAN_IDENTITY')
    plan = manifest['plan']
    api = API(os.environ.get('API_TOKEN'))
    journal = directory/('journal-'+mode+'.json')
    previous = json.loads(read(journal)) if journal.exists() else None
    observed = api.bot()
    install_journal = directory/'journal-install.json'
    owner = json.loads(read(install_journal)) if install_journal.exists() else {}
    owned_pause = mode == 'rollback' and owner.get('stage') in ('PAUSED', 'RESUME', 'FINISHED')
    if not previous and not owned_pause and (observed.get('enabled') is not True
                                             or str(observed.get('state')).lower() != 'running'):
        raise DeploymentError('BOT_NOT_RUNNING_BEFORE_PAUSE')
    state = previous or {'stage': 'PAUSE_INTENT', 'mode': mode, 'backup_sha256': backup_sha}
    atomic(journal, canonical(state))
    result = state.get('result')
    if state['stage'] not in ('RESUME', 'FINISHED'):
        try:
            api.set_bot(False)
            no_bot_processes()
            state['stage'] = 'PAUSED'
            atomic(journal, canonical(state))
            verify_protected(plan)
            pages = pending_pages()
            with writer_exclusion() as connection:
                digest = apply(connection, plan['changes'], mode == 'install')
                connection.commit()
            if pending_pages() != pages:
                raise DeploymentError('PAGES_CHANGED_WHILE_PAUSED')
            verify_protected(plan)
            result = {'status': 'PASS', 'installed' if mode == 'install' else 'restored': True,
                      'crm_write': True, 'crm_changes': plan['changes'], 'crm_rows_sha256_after': digest,
                      'crm_unchanged': True, 'protected_files_unchanged': True,
                      'preservation_scope': 'ALL_CRM_ROWS_AND_FIELDS_EXCEPT_APPROVED_FUEL_VALUES_WHILE_BOT_PAUSED_UNDER_WRITER_LOCKS'}
        except Exception as error:
            # The SQL transaction commits all listed changes or none.
            result = {'status': 'FAIL', 'crm_write': True, 'error': type(error).__name__+':'+str(error)[:180]}
        state.update(stage='RESUME', result=result)
        atomic(journal, canonical(state))
    result['crm_resume'] = api.set_bot(True)
    state.update(stage='FINISHED', result=result)
    atomic(journal, canonical(state))
    return {**result, 'backup_manifest_sha256': backup_sha, 'plan_sha256': expected_plan}


def installed(run_id, expected_plan, backup_sha):
    _, manifest = load_backup(backup_sha)
    if manifest['run_id'] != run_id or manifest['plan_sha256'] != expected_plan:
        raise DeploymentError('VERIFY_BINDING')
    journal = json.loads(read(HERE/'backups'/backup_sha/'journal-install.json'))
    if journal.get('stage') != 'FINISHED' or journal.get('result', {}).get('installed') is not True:
        raise DeploymentError('INSTALL_JOURNAL_NOT_FINISHED')
    with read_only() as connection:
        current = {row['id']: row for row in rows(connection)}
    for change in manifest['plan']['changes']:
        if current[change['id']]['fuel'] != change['after']:
            raise DeploymentError('VERIFY_FUEL:'+change['auto_number'])
    verify_protected(manifest['plan'])
    return manifest


def account_used_bytes():
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
    resource.setrlimit(resource.RLIMIT_CPU, (20, 25))
    if not re.fullmatch(r'[0-9]+', args.run):
        raise DeploymentError('RUN_ID')
    work = HERE/'runs'/args.run
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = work/('receipt-'+args.mode+'.json')
    if receipt.exists():
        return 0 if json.loads(read(receipt))['status'] == 'PASS' else 1
    value = {'run_id': args.run, 'mode': args.mode, 'status': 'FAIL',
             'crm_write': args.mode in ('install', 'rollback')}
    with (HERE/'deployment.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if receipt.exists():
            return 0 if json.loads(read(receipt))['status'] == 'PASS' else 1
        try:
            if args.mode == 'preview':
                plan = prepare()
                value.update(status='PASS', plan=plan, plan_sha256=sha(canonical(plan)), storage_probe=storage_probe())
            elif args.mode == 'backup':
                value.update(backup(args.run, args.plan), status='PASS')
            elif args.mode in ('install', 'rollback'):
                value.update(lifecycle(args.mode, args.run, args.plan, args.backup))
            else:
                manifest = installed(args.run, args.plan, args.backup)
                value.update(status='PASS', backup_manifest_sha256=args.backup, plan_sha256=args.plan,
                             crm_changes=manifest['plan']['changes'], protected_files_unchanged=True)
            value['safe_to_stop'] = True
        except Exception as error:
            value['error'] = type(error).__name__+':'+str(error)[:180]
            if args.mode in ('preview', 'backup', 'verify'):
                value['safe_to_stop'] = True
            else:
                # A lifecycle journal must finish its own resume.
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
