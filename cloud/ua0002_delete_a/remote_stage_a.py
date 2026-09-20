#!/usr/bin/env python3
"""Source-bound, forward-only retirement of the already deleted UA-0002.

Run only through the reviewed lifecycle owner after its provider-side CRM pause.
The target must already be absent from CRM with its real delete audit event.
No bot imports, media deletion, database write, broad rebuild or old-page restore.
All production observations are private except compact hashes and booleans.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import fcntl
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import tempfile
import time
from types import SimpleNamespace
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

ROOT = Path('/home/Carix')
CODE = 'UA-0002'
TARGET_ID = 8
VIN = 'WDD2452322J561014'
CONTRACT = 'UA-ART-UA0002-CRITICAL-DELETE-001-v1.0'
MAX_FILE = 256 * 1024 * 1024
HEX = re.compile(r'^[0-9a-f]{64}$')
PACKAGE = {'remote_stage_a.py', 'visibility_lifecycle.py', 'publication_fence.py',
           'ua_site_counters.py', 'uaart_price_sync_runtime.py', 'provenance.json', 'remote_lifecycle.py'}


class Stop(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise Stop(code)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def regular(path, absent=False):
    path = Path(path)
    require(path.is_absolute() and path.parent.resolve(strict=True) == path.parent,
            'CANONICAL_FILE_PARENT_REQUIRED')
    try:
        info = path.lstat()
    except FileNotFoundError:
        require(absent, 'REQUIRED_FILE_ABSENT:' + path.name)
        return None
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
            'EXACT_REGULAR_FILE_REQUIRED:' + path.name)
    return info


def read(path):
    info = regular(path)
    require(info.st_size <= MAX_FILE, 'FILE_SIZE_BOUND')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as handle:
        data = handle.read(MAX_FILE + 1)
    require(len(data) <= MAX_FILE, 'FILE_SIZE_BOUND')
    return data


def fingerprint(path):
    info = regular(path, absent=True)
    return ({'exists': False} if info is None else
            {'exists': True, 'sha256': sha(read(path)),
             'mode': stat.S_IMODE(info.st_mode), 'bytes': info.st_size})


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic(path, data):
    path = Path(path)
    regular(path, absent=True)
    fd, name = tempfile.mkstemp(prefix='.ua0002-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.replace(name, path)
        sync_directory(path.parent)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def json_write(path, value):
    atomic(path, encoded(value) + b'\n')


def json_read(path):
    return json.loads(read(path).decode('utf-8'))


def relative_path(value):
    require(isinstance(value, str), 'RELATIVE_PATH_REQUIRED')
    path = Path(value)
    require(not path.is_absolute() and path.parts and all(p not in ('.', '..') for p in path.parts),
            'RELATIVE_PATH_SCOPE')
    result = ROOT / path
    require(result.is_relative_to(ROOT), 'ROOT_ESCAPE')
    return result


def normalize_vin(value):
    return re.sub(r'[\s-]', '', str(value or '')).upper()


def db_state(path=None):
    """Digest all tables, including outboxes, without serializing private rows."""
    path = Path(path or ROOT / 'crm.db')
    regular(path)
    conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('BEGIN')
        integrity = [row[0] for row in conn.execute('PRAGMA integrity_check')]
        require(integrity == ['ok'], 'DATABASE_INTEGRITY_FAILED')
        schema = [tuple(row) for row in conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")]
        tables = {}
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            name = row[0]
            quoted = '"' + name.replace('"', '""') + '"'
            # SQL rows may contain binary application data; hex is lossless.
            values = [tuple({'bytes_hex': v.hex()} if isinstance(v, bytes) else v for v in r)
                      for r in conn.execute('SELECT * FROM ' + quoted)]
            values.sort(key=encoded)
            tables[name] = {'sha256': sha(encoded(values)), 'rows': len(values)}
        candidates = [dict(row) for row in conn.execute(
            'SELECT * FROM cars WHERE id=? OR auto_number=?', (TARGET_ID, CODE))]
        for row in candidates:
            require(row.get('id') == TARGET_ID and row.get('auto_number') == CODE,
                    'TARGET_IDENTITY_COLLISION')
            require(normalize_vin(row.get('vin')) == VIN, 'TARGET_VIN_MISMATCH')
        require(not candidates, 'TARGET_ROW_PRESENT_STAGE_B_TOMBSTONE_REQUIRED')
        # A recreated duplicate code or VIN blocks retirement admission.
        for row in conn.execute('SELECT id,auto_number,vin FROM cars'):
            if normalize_vin(row['vin']) == VIN:
                require(row['id'] == TARGET_ID and row['auto_number'] == CODE,
                        'TARGET_VIN_COLLISION')
        return {'integrity': 'ok', 'schema_sha256': sha(encoded(schema)), 'tables': tables,
                'target_absent': not candidates, 'target_sha256': sha(encoded(candidates)),
                'target_count': len(candidates)}
    finally:
        conn.close()


def db_structure():
    """Sanitized facts for the Stage B schema design; never client row values."""
    conn = sqlite3.connect((ROOT / 'crm.db').as_uri() + '?mode=ro', uri=True)
    try:
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        columns = [{'name': r[1], 'type': r[2], 'notnull': bool(r[3]), 'primary_key': r[5]}
                   for r in conn.execute('PRAGMA table_info(cars)')]
        foreign = []
        for name in names:
            quoted = '"' + name.replace('"', '""') + '"'
            for row in conn.execute('PRAGMA foreign_key_list(' + quoted + ')'):
                if name == 'cars' or row[2] == 'cars':
                    foreign.append({'from_table': name, 'to_table': row[2], 'from_column': row[3],
                                    'to_column': row[4], 'on_update': row[5], 'on_delete': row[6]})
        triggers = [{'name': row[0], 'table': row[1], 'definition_sha256': sha((row[2] or '').encode())}
                    for row in conn.execute("SELECT name,tbl_name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name")]
        observation = {'observed': False, 'reason': 'AUDIT_TABLE_UNAVAILABLE'}
        if 'audit' in names:
            fields = {r[1] for r in conn.execute('PRAGMA table_info(audit)')}
            if {'action', 'entity_type', 'entity_id', 'old_value', 'created_at'} <= fields:
                dates = [r[0] for r in conn.execute(
                    "SELECT created_at FROM audit WHERE action='card_delete' AND entity_type='cars' "
                    'AND entity_id=? AND old_value=? ORDER BY created_at', (TARGET_ID, CODE))]
                observation = {'observed': bool(dates), 'matches': len(dates),
                               'latest_created_at': str(dates[-1]) if dates else None,
                               'actor_omitted': True}
        return {'cars_columns': columns, 'cars_foreign_keys': foreign, 'triggers': triggers,
                'card_delete': observation}
    finally:
        conn.close()


def retire_sitemap(data):
    """Remove only exact UA-0002 page URL elements without reserializing XML."""
    source = data.decode('utf-8')
    tree = ET.fromstring(source)
    require(tree.tag.rsplit('}', 1)[-1] == 'urlset', 'SITEMAP_ROOT_UNSUPPORTED')
    spans = []
    pattern = re.compile(r'<url\b[^>]*>.*?</url\s*>', re.S)
    for match in pattern.finditer(source):
        element = ET.fromstring(match.group())
        locations = [e.text or '' for e in element if e.tag.rsplit('}', 1)[-1] == 'loc']
        require(len(locations) == 1, 'SITEMAP_LOCATION_AMBIGUOUS')
        name = urlsplit(locations[0]).path.rsplit('/', 1)[-1]
        if re.fullmatch(re.escape(CODE) + r'(?:-diag)?(?:-[0-9a-f]{6,10})?\.html', name):
            spans.append(match.span())
    require(len(list(tree)) == len(list(pattern.finditer(source))), 'SITEMAP_UNBOUND_ELEMENT')
    for start, end in reversed(spans):
        source = source[:start] + source[end:]
    ET.fromstring(source)
    require(not re.search(re.escape(CODE) + r'(?:-diag)?(?:-[0-9a-f]{6,10})?\.html', source), 'SITEMAP_RESIDUAL_TARGET')
    return source.encode('utf-8')


def process_inventory():
    """Only command hashes are exported; arbitrary process arguments stay private."""
    own = set()
    pid = os.getpid()
    while pid > 1 and pid not in own:
        own.add(pid)
        try:
            fields = Path('/proc/%d/status' % pid).read_text().splitlines()
            pid = int(next(v.split(':', 1)[1] for v in fields if v.startswith('PPid:')))
        except (OSError, StopIteration, ValueError):
            break
    result = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name) in own:
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            cmdline = (entry / 'cmdline').read_bytes()
            executable = Path(cmdline.split(b'\0', 1)[0].decode('utf-8', 'replace')).name
            if 'python' not in executable.lower():
                continue
            argv = [part.decode('utf-8', 'strict') for part in cmdline.rstrip(b'\0').split(b'\0')]
            argv[0] = Path(argv[0]).name
            result.append({'pid': int(entry.name), 'command_sha256': sha(encoded(argv))})
        except FileNotFoundError:
            continue
    return sorted(result, key=lambda row: row['pid'])


@contextlib.contextmanager
def singleton(timeout=120):
    path = ROOT / '.start_safe.singleton.lock'
    info = regular(path)
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        opened = os.fstat(fd)
        require((opened.st_dev, opened.st_ino) == (info.st_dev, info.st_ino), 'SINGLETON_INODE_CHANGED')
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                require(time.monotonic() < deadline, 'CRM_SINGLETON_STILL_RUNNING')
                time.sleep(0.1)
        linked = regular(path)
        require((opened.st_dev, opened.st_ino) == (linked.st_dev, linked.st_ino), 'SINGLETON_INODE_CHANGED')
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


class Transaction:
    def __init__(self, plan, plan_sha, package):
        self.plan, self.plan_sha = plan, plan_sha
        self.package = Path(package).resolve(strict=True)
        require(plan.get('contract') == CONTRACT and plan.get('version') == 1, 'PLAN_CONTRACT')
        require(plan.get('root') == str(ROOT) and plan.get('alwayson_id') == 266084, 'PLAN_SCOPE')
        require(plan.get('target') == {'id': TARGET_ID, 'auto_number': CODE, 'vin': VIN}, 'PLAN_TARGET')
        require(re.fullmatch(r'[A-Za-z0-9_-]{8,96}', str(plan.get('nonce', ''))), 'NONCE_SCOPE')
        self.backup = ROOT / 'rezerv_publikacii' / ('UA0002-delete-' + plan['nonce'])
        require(plan.get('backup_dir') == str(self.backup), 'BACKUP_PATH_SCOPE')
        require(set(plan.get('package_sha256', {})) == PACKAGE, 'PACKAGE_BINDING_INCOMPLETE')
        for name, expected in plan['package_sha256'].items():
            require(HEX.fullmatch(str(expected)) and sha(read(self.package / name)) == expected,
                    'PACKAGE_HASH:' + name)
        require({'db.py', 'cars_ui.py', 'publikaciya.py', 'stranica.py', 'start_safe.py', 'run_all.py'}
                <= set(plan.get('source_sha256', {})), 'LIVE_SOURCE_BINDING_REQUIRED')
        require(plan.get('database_state_sha256') is None or
                HEX.fullmatch(str(plan['database_state_sha256'])), 'DATABASE_BINDING_INVALID')
        writers = plan.get('writers', {})
        require(writers.get('reviewed') is True and HEX.fullmatch(str(writers.get('provider_snapshot_sha256', ''))),
                'FRESH_PROVIDER_WRITER_REVIEW_REQUIRED')
        require(isinstance(writers.get('allowed_python_cmdline_sha256'), list)
                and all(HEX.fullmatch(str(v)) for v in writers['allowed_python_cmdline_sha256']),
                'READONLY_BACKGROUND_PROCESS_BINDING_REQUIRED')
        # The modules imported below are immutable, reviewed files in this job.
        # The production root must never be present on their import path.
        require(str(ROOT) not in sys.path, 'PRODUCTION_IMPORT_PATH_FORBIDDEN')
        for name in ('publication_fence', 'uaart_price_sync_runtime', 'ua_site_counters', 'visibility_lifecycle'):
            existing = sys.modules.get(name)
            require(existing is None or Path(existing.__file__).parent == self.package, 'PRELOADED_MODULE_COLLISION')
        if str(self.package) not in sys.path:
            sys.path.insert(0, str(self.package))
        import publication_fence
        import visibility_lifecycle
        self.fence, self.visibility = publication_fence, visibility_lifecycle
        surfaces = []
        for item in plan.get('shared_surfaces', []):
            path = relative_path(item.get('path'))
            require(item.get('kind') in {'HOME', 'CATALOG'} and path.name in {'index.html', 'katalog.html'},
                    'SHARED_ROUTE_SCOPE')
            require(path.parent in {ROOT / 'video', ROOT / 'site'}, 'SHARED_PUBLIC_ROOT_SCOPE')
            surfaces.append(SimpleNamespace(path=path, kind=item['kind']))
        require({str(s.path.relative_to(ROOT)) for s in surfaces} >=
                {'video/index.html', 'video/katalog.html', 'site/index.html', 'site/katalog.html'},
                'BOTH_PUBLIC_ROOTS_REQUIRED')
        # Persisted aliases remain part of the binding after their unlink, so
        # a restarted worker sees the same exact route set as the first run.
        card_pattern = re.compile(re.escape(CODE) + r'(?:-diag)?(?:-[0-9a-f]{6,10})?\.html$')
        for relative in plan.get('public_preimage', {}):
            path = relative_path(relative)
            if path.name not in {'index.html', 'katalog.html', 'sitemap.xml'}:
                require(path.parent in {ROOT / 'video', ROOT / 'site'} and card_pattern.fullmatch(path.name),
                        'CARD_ROUTE_SCOPE')
                surfaces.append(SimpleNamespace(path=path, kind='CARD'))
        self.binding = SimpleNamespace(db_path=ROOT / 'crm.db', journal_root=self.backup,
                                       resolve_surfaces=lambda code: tuple(surfaces),
                                       retirement_home_modes={str(relative_path(name)): mode
                                           for name, mode in plan.get('home_modes', {}).items()})
        self.cards, self.shared = self.visibility._paths(self.binding, CODE)
        self.sitemaps = [relative_path(name) for name in plan.get('sitemaps', [])]
        require(all(p in {ROOT / 'video/sitemap.xml', ROOT / 'site/sitemap.xml'} for p in self.sitemaps),
                'SITEMAP_PATH_SCOPE')
        require(set(plan.get('public_preimage', {})) ==
                {str(p.relative_to(ROOT)) for p in self.cards + self.shared + self.sitemaps}, 'EXACT_ROUTE_BINDING_REQUIRED')
        for name, pin in plan['public_preimage'].items():
            require(isinstance(pin, dict) and type(pin.get('exists')) is bool, 'PUBLIC_EXISTENCE_PIN_REQUIRED')
            if pin['exists']:
                require(HEX.fullmatch(str(pin.get('sha256', ''))), 'PUBLIC_CONTENT_PIN_REQUIRED')
            else:
                require(relative_path(name) in self.cards and set(pin) == {'exists'}, 'PUBLIC_ABSENCE_PIN_SCOPE')
        self.journal_path, self.manifest_path = self.backup / 'transaction.json', self.backup / 'backup_manifest.json'

    def sources(self):
        for name, expected in self.plan['source_sha256'].items():
            require('/' not in name and name.endswith('.py'), 'SOURCE_PATH_SCOPE')
            require(HEX.fullmatch(str(expected)) and sha(read(ROOT / name)) == expected,
                    'SOURCE_CHANGED:' + name)

    def writers(self):
        allowed = set(self.plan['writers']['allowed_python_cmdline_sha256'])
        require(all(p['command_sha256'] in allowed for p in process_inventory()), 'UNREVIEWED_ACTIVE_PYTHON_WRITER')

    def routes(self):
        cards, shared = self.visibility._paths(self.binding, CODE)
        require(cards == self.cards and shared == self.shared, 'PUBLIC_ROUTE_SET_DRIFT')

    def public(self):
        return {str(p.relative_to(ROOT)): fingerprint(p) for p in self.cards + self.shared + self.sitemaps}

    def protected(self):
        excluded = set(self.cards + self.shared)
        result = {}
        for root in (ROOT / 'video', ROOT / 'site'):
            for path in root.glob('*.html'):
                if path not in excluded:
                    result[str(path.relative_to(ROOT))] = sha(read(path))
        require(len(result) <= 20000, 'PROTECTED_PAGE_BOUND')
        return result

    def check_admission(self):
        self.sources(); self.writers(); self.routes()
        state = db_state()
        require(db_structure()['card_delete']['observed'], 'TARGET_DELETE_AUDIT_EVENT_REQUIRED')
        if self.plan.get('database_state_sha256') is not None:
            require(sha(encoded(state)) == self.plan['database_state_sha256'], 'DATABASE_STATE_DRIFT')
        observed = self.public()
        require(all(all(observed[name].get(k) == v for k, v in pin.items())
                    for name, pin in self.plan['public_preimage'].items()), 'PUBLIC_PREIMAGE_DRIFT')
        # This is historical public identity evidence, not a fabricated row.
        require(VIN in read(ROOT / 'video' / (CODE + '.html')).decode('utf-8').upper(),
                'HISTORICAL_PUBLIC_VIN_EVIDENCE_REQUIRED')
        return state

    def journal(self, value=None):
        if value is None:
            result = json_read(self.journal_path)
            require(result.get('plan_sha256') == self.plan_sha, 'JOURNAL_PLAN_DRIFT')
            return result
        json_write(self.journal_path, dict(value, plan_sha256=self.plan_sha))

    def manifest(self):
        journal = self.journal()
        require(sha(read(self.manifest_path)) == journal['backup_manifest_sha256'], 'BACKUP_MANIFEST_SHA_MISMATCH')
        value = json_read(self.manifest_path)
        require(value.get('plan_sha256') == self.plan_sha, 'BACKUP_PLAN_MISMATCH')
        for name, item in value['files'].items():
            if item['exists']:
                require(sha(gzip.decompress(read(self.backup / item['stored']))) == item['sha256'],
                        'BACKUP_READBACK_FAILED:' + name)
        require(sha(read(self.backup / 'crm.snapshot.db')) == value['snapshot_sha256'], 'DATABASE_BACKUP_HASH')
        require(db_state(self.backup / 'crm.snapshot.db') == value['database_state'], 'DATABASE_BACKUP_LOGICAL_DRIFT')
        return value

    def backup_phase(self):
        if self.backup.exists():
            require(self.journal()['state'] == 'BACKED_UP', 'BACKUP_ALREADY_USED')
            manifest = self.manifest()
            require(self.check_admission() == manifest['database_state'], 'BACKUP_DATABASE_STATE_DRIFT')
            require(self.protected() == manifest['protected'], 'PROTECTED_PAGES_DRIFT')
            return self.receipt('backup', idempotent=True)
        before = self.check_admission()
        protected = self.protected()
        require(self.backup.parent.resolve(strict=True) == self.backup.parent, 'BACKUP_PARENT_UNSAFE')
        self.backup.mkdir(mode=0o700)
        (self.backup / 'files').mkdir(mode=0o700)
        (self.backup / 'visibility').mkdir(mode=0o700)
        self.journal({'state': 'BACKUP_STARTED'})
        paths = set(self.cards + self.shared + self.sitemaps) | {ROOT / n for n in self.plan['source_sha256']}
        paths |= {ROOT / 'crm.db', ROOT / 'crm.db-wal', ROOT / 'crm.db-shm'}
        files = {str(p.relative_to(ROOT)): fingerprint(p) for p in sorted(paths)}
        total = sum(item.get('bytes', 0) for item in files.values())
        require(total < 1024 * 1024 * 1024 and os.statvfs(self.backup).f_bavail * os.statvfs(self.backup).f_frsize
                > total + 2 * regular(ROOT / 'crm.db').st_size + 64 * 1024 * 1024, 'BACKUP_CAPACITY')
        for index, (name, item) in enumerate(files.items()):
            if item['exists']:
                data = read(ROOT / name)
                require(sha(data) == item['sha256'], 'BACKUP_SOURCE_CHANGED')
                item['stored'] = 'files/%d.gz' % index
                atomic(self.backup / item['stored'], gzip.compress(data, mtime=0))
                require(sha(gzip.decompress(read(self.backup / item['stored']))) == item['sha256'], 'BACKUP_CHECKSUM')
        conn = sqlite3.connect((ROOT / 'crm.db').as_uri() + '?mode=ro', uri=True)
        destination = sqlite3.connect(self.backup / 'crm.snapshot.db')
        try:
            conn.backup(destination)
        finally:
            destination.close(); conn.close()
        os.chmod(self.backup / 'crm.snapshot.db', 0o600)
        require(db_state(self.backup / 'crm.snapshot.db') == before, 'DATABASE_SNAPSHOT_CHANGED')
        require(self.check_admission() == before and self.protected() == protected, 'BACKUP_ADMISSION_DRIFT')
        sitemap_after = {str(p.relative_to(ROOT)): base64.b64encode(retire_sitemap(read(p))).decode()
                         for p in self.sitemaps}
        value = {'plan_sha256': self.plan_sha, 'files': files, 'database_state': before,
                 'database_structure': db_structure(), 'sitemap_after': sitemap_after,
                 'protected': protected, 'snapshot_sha256': sha(read(self.backup / 'crm.snapshot.db'))}
        json_write(self.manifest_path, value)
        self.journal({'state': 'BACKED_UP', 'backup_manifest_sha256': sha(read(self.manifest_path))})
        self.manifest()
        return self.receipt('backup')

    def receipt(self, operation, **extra):
        manifest = json_read(self.manifest_path)
        value = {'status': 'PASS', 'operation': operation, 'contract': CONTRACT, 'plan_sha256': self.plan_sha,
                 'backup_manifest_sha256': self.journal()['backup_manifest_sha256'],
                 'source_checksum_pass': True, 'integrity_pass': True,
                 'database_state_sha256': sha(encoded(manifest['database_state'])),
                 'target_absent': manifest['database_state']['target_absent'],
                 'database_structure': manifest['database_structure'], **extra}
        json_write(self.backup / (operation + '_receipt.json'), value)
        return value

    def retire(self, operation='install_verify'):
        manifest, journal = self.manifest(), self.journal()
        self.sources(); self.writers(); self.routes()
        require(db_state() == manifest['database_state'], 'DATABASE_STATE_DRIFT')
        require(self.protected() == manifest['protected'], 'PROTECTED_PAGES_DRIFT')
        if journal['state'] == 'BACKED_UP':
            self.check_admission()
            # Durable intent precedes every public mutation. Recovery follows
            # this exact record; never generic restore or new broad rendering.
            journal['state'] = 'RETIRE_STARTED'
            self.journal(journal)
        require(journal['state'] in {'RETIRE_STARTED', 'VERIFIED'}, 'RETIREMENT_JOURNAL_STATE')
        self.visibility.retire_lists(self.binding, CODE, self.plan_sha)
        for path in self.sitemaps:
            name = str(path.relative_to(ROOT))
            data = base64.b64decode(manifest['sitemap_after'][name], validate=True)
            current = read(path)
            require(sha(current) in {manifest['files'][name]['sha256'], sha(data)}, 'NEWER_SITEMAP_PRESERVED')
            if current != data:
                # Reuse the exact atomic helper, retaining the existing mode.
                self.visibility.atomic_bytes(path, data, manifest['files'][name]['mode'])
        for path in self.cards:
            item = manifest['files'][str(path.relative_to(ROOT))]
            if not path.exists():
                continue
            require(item['exists'] and sha(read(path)) == item['sha256'], 'NEWER_TARGET_PAGE_PRESERVED')
            path.unlink()
            sync_directory(path.parent)
        require(not any(p.exists() for p in self.cards), 'TARGET_ROUTE_STILL_PRESENT')
        for path in self.shared:
            require(not self.visibility.listing_present(read(path).decode('utf-8'), CODE), 'TARGET_LISTING_STILL_PRESENT')
            item = manifest['files'][str(path.relative_to(ROOT))]
            before = gzip.decompress(read(self.backup / item['stored'])).decode('utf-8')
            after = read(path).decode('utf-8')
            scripts = lambda value: re.findall(r'<script\b[^>]*>.*?</script\s*>', value, re.I | re.S)
            require(scripts(before) == scripts(after), 'EXISTING_PAGE_SCRIPT_CHANGED')
        import ua_site_counters as counters
        expected_records = None
        count_proof = None
        for path in self.shared:
            if path.name != 'katalog.html':
                continue
            source = read(path).decode('utf-8')
            records, counts = counters.catalog_snapshot(source)
            require(sum(counts[s] for s in counters.STAGES) == counts['all'], 'CATALOG_UNKNOWN_STAGE')
            require(counters.patch_catalog(source, counts) == source, 'CATALOG_COUNTERS_MISMATCH')
            require(expected_records is None or expected_records == records, 'CATALOG_MIRROR_MISMATCH')
            expected_records, count_proof = records, counts
        require(expected_records is not None, 'NO_CATALOG_PROOF')
        for path in self.shared:
            if self.binding.retirement_home_modes.get(str(path)) == 'MODERN_COUNTERS':
                source = read(path).decode('utf-8')
                require(counters.patch_home(source, count_proof) == source, 'HOME_COUNTERS_MISMATCH')
        conn = sqlite3.connect((ROOT / 'crm.db').as_uri() + '?mode=ro', uri=True)
        try:
            published_codes = {row[0] for row in conn.execute('SELECT auto_number FROM cars WHERE published=1')}
        finally:
            conn.close()
        # A separate pre-existing publication mismatch is evidence, not scope
        # to remove another advert or rebuild another vehicle's prices.
        catalog_db_diagnostic = {'catalog_only_count': len(set(expected_records) - published_codes),
                                 'database_only_count': len(published_codes - set(expected_records))}
        self.sources(); self.writers(); self.routes()
        require(db_state() == manifest['database_state'], 'DATABASE_CHANGED')
        require(self.protected() == manifest['protected'], 'OTHER_PUBLIC_PAGES_CHANGED')
        journal.update(state='VERIFIED', public_after=self.public())
        self.journal(journal)
        return self.receipt(operation, post_check_pass=True, target_retired_local=True,
                            database_unchanged=True, other_pages_unchanged=True, media_mutations=0,
                            rollback_policy='FORWARD_RETIREMENT_ONLY', live_http_verified=False,
                            counter_proof=count_proof, catalog_db_diagnostic=catalog_db_diagnostic,
                            absent=[str(p.relative_to(ROOT)) for p in self.cards],
                            shared_sha256={str(p.relative_to(ROOT)): sha(read(p)) for p in self.shared + self.sitemaps})

    def execute(self, operation):
        require(operation in {'backup', 'install_verify', 'recover'}, 'OPERATION_SCOPE')
        regular(ROOT / '.ua_art_publish_transaction.lock')
        with singleton(), self.fence.publication_fence(timeout=90):
            return self.backup_phase() if operation == 'backup' else self.retire(operation)


def recovery_status(plan, plan_sha, package):
    """Phase proof remains usable when live source/DB admission has drifted."""
    require(plan.get('contract') == CONTRACT and plan.get('root') == str(ROOT), 'RECOVERY_PLAN_SCOPE')
    require(re.fullmatch(r'[A-Za-z0-9_-]{8,96}', str(plan.get('nonce', ''))), 'RECOVERY_NONCE_SCOPE')
    backup = ROOT / 'rezerv_publikacii' / ('UA0002-delete-' + plan['nonce'])
    require(plan.get('backup_dir') == str(backup), 'RECOVERY_BACKUP_SCOPE')
    require(set(plan.get('package_sha256', {})) == PACKAGE, 'RECOVERY_PACKAGE_BINDING')
    for name, expected in plan['package_sha256'].items():
        require(sha(read(Path(package) / name)) == expected, 'RECOVERY_PACKAGE_HASH')
    require(str(ROOT) not in sys.path, 'RECOVERY_PRODUCTION_IMPORT_PATH_FORBIDDEN')
    if str(package) not in sys.path:
        sys.path.insert(0, str(package))
    import publication_fence
    require(Path(publication_fence.__file__).parent == Path(package), 'RECOVERY_FENCE_MODULE_COLLISION')
    regular(ROOT / '.ua_art_publish_transaction.lock')
    with singleton(), publication_fence.publication_fence(timeout=90):
        if not backup.exists():
            stage = 'NOT_STARTED'
        else:
            require(backup.resolve(strict=True) == backup and not backup.stat().st_mode & 0o077,
                    'RECOVERY_PRIVATE_JOURNAL_REQUIRED')
            record = json_read(backup / 'transaction.json')
            require(record.get('plan_sha256') == plan_sha, 'RECOVERY_JOURNAL_PLAN_DRIFT')
            stage = record.get('state')
            require(stage in {'BACKUP_STARTED', 'BACKED_UP', 'RETIRE_STARTED', 'VERIFIED'}, 'RECOVERY_STATE_UNKNOWN')
    return {'status': 'PASS', 'operation': 'recovery_status', 'plan_sha256': plan_sha,
            'no_mutation': stage in {'NOT_STARTED', 'BACKUP_STARTED', 'BACKED_UP'}, 'durable_stage': stage}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--operation', choices=('backup', 'install_verify', 'recover', 'recovery_status'), required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--plan-sha256', required=True)
    args = parser.parse_args()
    try:
        data = read(args.plan)
        require(HEX.fullmatch(args.plan_sha256) and sha(data) == args.plan_sha256, 'PLAN_SHA_MISMATCH')
        if args.operation == 'recovery_status':
            result = recovery_status(json.loads(data), args.plan_sha256, Path(__file__).parent)
        else:
            transaction = Transaction(json.loads(data), args.plan_sha256, Path(__file__).parent)
            result = transaction.execute(args.operation)
    except Exception as exc:
        # No private source snippets, full rows, process args or traceback.
        result = {'status': 'FAIL', 'operation': args.operation, 'plan_sha256': args.plan_sha256,
                  'error_code': str(exc) if isinstance(exc, Stop) else type(exc).__name__}
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
