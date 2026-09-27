"""Prepare, inspect, apply or roll back a bounded SEO release with file locks."""
import argparse
from contextlib import contextmanager
import datetime
import difflib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

from candidate_builder import SOURCE_SHA256, build
from ua_seo_metadata import CORE, normalize
from ua_seo_sitemap import CatalogLinks, sitemap
from verify_seo import verify_page

ROOT = Path('/home/Carix')
HERE = Path(__file__).resolve().parent
RUN = HERE/'release'
WSGI = Path('/var/www/www_uaart_com_ua_wsgi.py')
RUNTIME = ('ua_seo_metadata.py', 'ua_seo_sitemap.py')
PROTECTED = ('db.py', 'cars_ui.py', 'cars_schema.py', 'run_all.py', 'start_safe.py',
             'lead_bot.py', 'team_bot.py', 'catalog_design_guard.py',
             'publication_fence.py', 'publish_transaction_guard.py',
             'ua_site_counters.py', 'ua_order/host.py')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or path.resolve() != path or info.st_size > 16000000:
        raise ValueError('UNSAFE_PATH:' + str(path))
    return path.read_bytes()


def atomic(path, value, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.seo-release-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def code_path(name):
    return WSGI if name == WSGI.name else ROOT/name


def prepare():
    if RUN.exists():
        raise ValueError('RELEASE_ALREADY_PREPARED')
    sources = {name: read(code_path(name)) for name in SOURCE_SHA256}
    candidates = build(sources)
    changes = {str(code_path(name)): value for name, value in candidates.items()}
    for name in RUNTIME:
        if (ROOT/name).exists():
            raise ValueError('NEW_MODULE_ALREADY_EXISTS:' + name)
        changes[str(ROOT/name)] = read(HERE/name)
    # The existing catalog validator compares against its approved template.
    # Update that template's SEO fields too, keeping its body/layout intact.
    golden_path = ROOT/'catalog_design_golden.html'
    golden_before = read(golden_path).decode('utf-8')
    golden_after = normalize(golden_before, 'katalog.html')
    verify_page(golden_before, golden_after, 'katalog.html')
    changes[str(golden_path)] = golden_after.encode('utf-8')
    results = []
    for folder in ('video', 'site'):
        directory = ROOT/folder
        if not directory.exists():
            continue
        catalog = (directory/'katalog.html').read_text(encoding='utf-8')
        # The old site/ order/info/home copies are not served by the web app
        # and use a different legacy shell. Only synchronize its catalog and
        # cards, which remain publication outputs of the CRM.
        names = list(CORE if folder == 'video' else ('katalog.html',)) + sorted(CatalogLinks(catalog).names)
        for name in names:
            path = directory/name
            if not path.is_file():
                raise ValueError('CATALOG_TARGET_MISSING:' + str(path))
            before = read(path).decode('utf-8')
            after = normalize(before, name)
            result = verify_page(before, after, name)
            result['directory'] = folder
            results.append(result)
            changes[str(path)] = after.encode('utf-8')
        changes[str(directory/'sitemap.xml')] = sitemap(directory, catalog)
    titles = [r['title'] for r in results if r['directory'] == 'video']
    if len(titles) != len(set(titles)):
        raise ValueError('DUPLICATE_TITLES')
    protected = {str(ROOT/name):digest(read(ROOT/name)) for name in PROTECTED}
    plan = {'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'protected': protected, 'files': {}, 'pages': results,
            'crm_write': False, 'media_write': False}
    RUN.mkdir(mode=0o700)
    differences = []
    for index, (key, value) in enumerate(changes.items()):
        path = Path(key)
        before = read(path) if path.exists() else None
        mode = stat.S_IMODE(path.stat().st_mode) if before is not None else 0o644
        item = {'before': digest(before) if before is not None else None,
                'after': digest(value), 'mode': mode, 'index': index}
        plan['files'][key] = item
        if before is not None:
            atomic(RUN/'before'/str(index), before, 0o600)
        atomic(RUN/'after'/str(index), value, 0o600)
        if path.suffix == '.py':
            differences.extend(difflib.unified_diff((before or b'').decode().splitlines(True), value.decode().splitlines(True), fromfile=key, tofile=key))
    atomic(RUN/'changes.diff', ''.join(differences).encode(), 0o600)
    atomic(RUN/'plan.json', json.dumps(plan, ensure_ascii=False, indent=2).encode(), 0o600)
    print(json.dumps({'prepared': True, 'files': len(changes), 'pages': len(results),
                      'public_pages': len(titles), 'plan_sha256': digest(read(RUN/'plan.json'))}))


@contextmanager
def exclusion():
    # Same ordering as the existing publication deployment workflow.
    with open(ROOT/'.crm_public_sync_worker.lock', 'a+') as lock:
        deadline = time.monotonic()+30
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('PUBLICATION_WORKER_BUSY')
                time.sleep(.1)
        sys.path.insert(0, str(ROOT))
        from publication_fence import publication_fence
        with publication_fence(timeout=30):
            yield


def verify(plan, state):
    for key, item in plan['files'].items():
        expected = item[state]
        path = Path(key)
        if expected is None:
            if path.exists() or path.is_symlink():
                raise ValueError('UNEXPECTED_FILE:' + key)
        elif digest(read(path)) != expected:
            raise ValueError('FILE_CHANGED:' + key)
        if digest(read(RUN/'after'/str(item['index']))) != item['after']:
            raise ValueError('CANDIDATE_CHANGED:' + key)
        if item['before'] is not None and digest(read(RUN/'before'/str(item['index']))) != item['before']:
            raise ValueError('BACKUP_CHANGED:' + key)
    for key, expected in plan['protected'].items():
        if digest(read(Path(key))) != expected:
            raise ValueError('PROTECTED_CHANGED:' + key)


def restore(plan, written):
    for key in reversed(written):
        item = plan['files'][key]
        if item['before'] is None:
            # Keep new, now-unreferenced pure modules; no destructive cleanup.
            continue
        atomic(Path(key), read(RUN/'before'/str(item['index'])), item['mode'])


def apply(expected):
    raw = read(RUN/'plan.json')
    if digest(raw) != expected:
        raise ValueError('PLAN_HASH')
    plan = json.loads(raw)
    with exclusion():
        verify(plan, 'before')
        written = []
        try:
            # Dependencies first, callers next, static output, WSGI last.
            keys = sorted(plan['files'], key=lambda p:
                          (0 if Path(p).name in RUNTIME else 3 if p == str(WSGI) else 1 if p.endswith('.py') else 2, p))
            for key in keys:
                item = plan['files'][key]
                atomic(Path(key), read(RUN/'after'/str(item['index'])), item['mode'])
                written.append(key)
            verify(plan, 'after')
            current = sitemap(ROOT/'video')
            if current != read(ROOT/'video/sitemap.xml'):
                raise ValueError('SITEMAPS_DIVERGED')
            result = {'installed': True, 'plan_sha256': expected, 'files': len(written),
                      'sitemap_urls': len(ET.fromstring(current)), 'protected_files_unchanged': True,
                      'crm_write': False, 'media_write': False}
            atomic(RUN/'installed.json', json.dumps(result, indent=2).encode(), 0o600)
            print(json.dumps(result))
        except Exception:
            restore(plan, written)
            raise


def rollback():
    plan = json.loads(read(RUN/'plan.json'))
    with exclusion():
        verify(plan, 'after')
        restore(plan, list(plan['files']))
    print(json.dumps({'rolled_back': True, 'new_unreferenced_modules_retained': True}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare','apply','verify','rollback'))
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare()
    elif args.action == 'apply':
        apply(args.plan_sha256)
    elif args.action == 'rollback':
        rollback()
    else:
        verify(json.loads(read(RUN/'plan.json')), 'after')
        print(json.dumps({'verified': True}))
