#!/usr/bin/env python3
"""Private, source-pinned UA-0022 publication transaction.

The canonical lifecycle controller must pause CRM always-on 266084 before
invocation and resume it afterwards. This program never controls services or
uses a credential. Production originals and the complete target row remain in
the private backup directory. No whole-database restore is implemented.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import gzip
import hashlib
import importlib
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

ROOT = Path('/home/Carix')
CONTRACT = 'UA-ART-UA0022-REBUILD-SERIALIZATION-001-v1.0'
CODE = 'UA-0022'
TARGET_ID = 32
CRM_ALWAYS_ON = 266084
MAX_FILE = 256 * 1024 * 1024
MAX_BACKUP_BYTES = 1536 * 1024 * 1024
MAX_FILES = 20000
MUTATED_SOURCES = ('cars_ui.py', 'stranica.py', 'publish_transaction_guard.py')
FLAGS = ('published', 'publish_pending')
HEX = re.compile(r'^[0-9a-f]{64}$')
TOKEN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{3,95}$')


class Stop(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise Stop(code)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(value):
    return sha(encoded(value))


def regular(path, absent=False):
    """Reject symlink parents as well as a symlink final component."""
    path = Path(path)
    require(path.is_absolute(), 'ABSOLUTE_PATH_REQUIRED')
    require(path.parent.resolve(strict=True) == path.parent, 'SYMLINK_PARENT')
    try:
        info = path.lstat()
    except FileNotFoundError:
        require(absent, 'REQUIRED_FILE_ABSENT:' + path.name)
        return None
    require(stat.S_ISREG(info.st_mode), 'REGULAR_FILE_REQUIRED:' + path.name)
    require(info.st_nlink == 1, 'HARDLINK_FORBIDDEN:' + path.name)
    return info


def read(path):
    info = regular(path)
    require(info.st_size <= MAX_FILE, 'FILE_SIZE_BOUND:' + Path(path).name)
    with open(path, 'rb') as handle:
        data = handle.read(MAX_FILE + 1)
    require(len(data) <= MAX_FILE, 'FILE_SIZE_BOUND:' + Path(path).name)
    return data


def fingerprint(path):
    info = regular(path, absent=True)
    if info is None:
        return {'exists': False}
    return {'exists': True, 'sha256': sha(read(path)),
            'mode': stat.S_IMODE(info.st_mode), 'bytes': info.st_size}


def atomic(path, data, mode=0o600):
    path = Path(path)
    regular(path, absent=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=str(path.parent))
    temporary = Path(temporary)
    try:
        with os.fdopen(fd, 'wb') as handle:
            os.fchmod(handle.fileno(), mode)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def json_read(path):
    return json.loads(read(path).decode('utf-8'))


def json_write(path, value):
    atomic(path, encoded(value) + b'\n')


@contextlib.contextmanager
def singleton(timeout=600):
    """Open only the pre-existing start_safe inode; never create or replace it."""
    path = ROOT / '.start_safe.singleton.lock'
    info = regular(path)
    fd = os.open(path, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(fd)
        require((opened.st_dev, opened.st_ino) == (info.st_dev, info.st_ino),
                'SINGLETON_INODE_CHANGED')
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                require(time.monotonic() < deadline, 'CRM_SINGLETON_STILL_RUNNING')
                time.sleep(0.1)
        linked = regular(path)
        require((opened.st_dev, opened.st_ino) == (linked.st_dev, linked.st_ino),
                'SINGLETON_INODE_CHANGED')
        yield
        linked = regular(path)
        require((opened.st_dev, opened.st_ino) == (linked.st_dev, linked.st_ino),
                'SINGLETON_INODE_CHANGED')
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def load_module(name, path):
    require(name not in sys.modules, 'MODULE_PRELOADED:' + name)
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, 'MODULE_LOADER_MISSING')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    # The controller uploads these SHA-bound files into a fresh private job
    # directory and invokes Python with -B. Use the standard audited loader.
    require(not Path(importlib.util.cache_from_source(str(path))).exists(), 'PACKAGE_BYTECODE_CACHE_FORBIDDEN')
    spec.loader.exec_module(module)
    return module


def target_file_name(name):
    return name == CODE + '.html' or name.startswith(CODE + '-')


def assert_native_video_dedup_inert():
    """Match the bound runtime's native video selection, without executing it."""
    count = 0
    for folder, _, names in os.walk(ROOT / 'video'):
        # These are the native exclusion substrings, including their scope.
        if '/preview' in folder or '/archive' in folder or '/stage' in folder:
            continue
        for name in sorted(names):
            if name.startswith('.') or not name.lower().endswith(('.mp4', '.mov', '.m4v', '.webm')):
                continue
            if name.startswith(CODE):
                regular(Path(folder) / name)
                count += 1
                require(count < 2, 'TARGET_VIDEO_DEDUP_WOULD_MUTATE_UNBACKED_FILES')
    return count


def public_paths():
    """Exact target pages/media and the two catalogs/homepages only."""
    result = set()
    for root in (ROOT / 'video', ROOT / 'site'):
        require(root.is_dir() and root.resolve() == root, 'PUBLIC_ROOT_REQUIRED')
        result.update(root / name for name in (CODE + '.html', CODE + '-diag.html',
                                                'katalog.html', 'index.html'))
        for path in root.iterdir():
            if target_file_name(path.name) and path.suffix == '.html':
                result.add(path)
        for folder in (root / 'foto' / CODE, root / 'diag' / CODE):
            if folder.exists():
                require(folder.is_dir() and folder.resolve() == folder, 'MEDIA_DIRECTORY_UNSAFE')
                for path in folder.rglob('*'):
                    require(not path.is_symlink(), 'MEDIA_SYMLINK_FORBIDDEN')
                    if path.is_file():
                        result.add(path)
        require(len(result) <= MAX_FILES, 'TARGET_FILE_COUNT_BOUND')
    archive = ROOT / 'archive' / 'video_dubli'
    if archive.exists():
        require(archive.is_dir() and archive.resolve() == archive, 'ARCHIVE_DIRECTORY_UNSAFE')
        for path in archive.iterdir():
            if target_file_name(path.name) and path.is_file():
                result.add(path)
    return result


def fingerprints(paths):
    return {str(path.relative_to(ROOT)): fingerprint(path) for path in sorted(paths)}


def public_snapshot():
    return fingerprints(public_paths())


def public_http_sha256():
    """Bind live controller GET checks to exact local public-route bytes."""
    result = {}
    for name in ('index.html', 'katalog.html', CODE + '.html', CODE + '-diag.html'):
        path = ROOT / 'video' / name
        if regular(path, absent=True) is not None:
            result['https://www.uaart.com.ua/video/' + name] = sha(read(path))
    require(any(url.endswith('/katalog.html') for url in result), 'PUBLIC_CATALOG_REQUIRED')
    return result


def protected_pages():
    result = {}
    for root in (ROOT / 'video', ROOT / 'site'):
        for path in sorted(root.rglob('*.html')):
            relative = path.relative_to(root)
            allowed = (len(relative.parts) == 1 and
                       (path.name in ('index.html', 'katalog.html') or target_file_name(path.name)))
            # Target media is also snapshotted separately, including any HTML.
            allowed = allowed or (len(relative.parts) >= 3 and
                                   relative.parts[0] in ('foto', 'diag') and relative.parts[1] == CODE)
            if not allowed:
                result[str(path.relative_to(ROOT))] = sha(read(path))
            require(len(result) <= MAX_FILES, 'PROTECTED_FILE_COUNT_BOUND')
    return result


def connection(write=False):
    conn = sqlite3.connect('file:' + str(ROOT / 'crm.db') + '?mode=' + ('rw' if write else 'ro'),
                           uri=True, timeout=15)
    conn.row_factory = sqlite3.Row
    if not write:
        conn.execute('PRAGMA query_only=ON')
    return conn


def db_state(conn=None):
    own = conn is None
    conn = conn or connection()
    try:
        row = conn.execute('SELECT * FROM cars WHERE id=?', (TARGET_ID,)).fetchone()
        require(row is not None, 'TARGET_ROW_ABSENT')
        row = dict(row)
        require(row.get('auto_number') == CODE, 'TARGET_IDENTITY_CHANGED')
        require(all(name in row for name in ('published', 'status', 'publish_pending',
                                             'price_uah', 'price_georgia')), 'TARGET_SCHEMA_UNSUPPORTED')
        duplicate = conn.execute('SELECT COUNT(*) FROM cars WHERE auto_number=?', (CODE,)).fetchone()[0]
        require(duplicate == 1, 'TARGET_CODE_NOT_UNIQUE')
        other = [dict(value) for value in conn.execute('SELECT * FROM cars WHERE id<>? ORDER BY id', (TARGET_ID,))]
        prices = [dict(value) for value in conn.execute(
            'SELECT id,price_uah,price_georgia FROM cars ORDER BY id')]
        schema = [list(value) for value in conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")]
        media_columns = [str(value[1]) for value in conn.execute('PRAGMA table_info(media)')]
        require(media_columns, 'MEDIA_TABLE_REQUIRED')
        media = [dict(value) for value in conn.execute('SELECT * FROM media ORDER BY rowid')]
        return {'target_row': row, 'target_row_sha256': digest(row),
                'other_rows_sha256': digest(other), 'other_rows_count': len(other),
                'prices_sha256': digest(prices), 'schema_sha256': digest(schema),
                'media_sha256': digest(media), 'media_count': len(media)}
    finally:
        if own:
            conn.close()


def integrity(conn):
    values = [str(row[0]) for row in conn.execute('PRAGMA integrity_check')]
    require(values == ['ok'], 'DATABASE_INTEGRITY_FAILED')


def compare_invariants(before, after, target_published):
    for key in ('other_rows_sha256', 'other_rows_count', 'prices_sha256', 'schema_sha256',
                'media_sha256', 'media_count'):
        require(before[key] == after[key], 'DATABASE_INVARIANT_CHANGED:' + key)
    expected = dict(before['target_row'])
    expected['published'] = target_published
    require(after['target_row'] == expected, 'TARGET_NONPUBLICATION_FIELDS_CHANGED')


def cas_published(expected, published):
    """SQLite writer lock protects exact full-row compare and our one-field write."""
    conn = connection(write=True)
    try:
        conn.execute('BEGIN IMMEDIATE')
        current = db_state(conn)['target_row']
        require(current == expected, 'TARGET_ROW_CAS_FAILED')
        result = conn.execute('UPDATE cars SET published=? WHERE id=? AND auto_number=? AND published IS ?',
                              (published, TARGET_ID, CODE, expected['published']))
        require(result.rowcount == 1, 'TARGET_ROW_UPDATE_COUNT')
        after = dict(expected)
        after['published'] = published
        require(db_state(conn)['target_row'] == after, 'TARGET_ROW_READBACK_FAILED')
        conn.commit()
        return after
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


class Installer:
    def __init__(self, plan, package_dir):
        self.plan = plan
        self.package = Path(package_dir).resolve(strict=True)
        require(plan.get('contract') == CONTRACT and plan.get('version') == 1, 'PLAN_CONTRACT_INVALID')
        require(plan.get('root') == str(ROOT), 'PLAN_ROOT_INVALID')
        for key in ('task_id', 'nonce'):
            require(isinstance(plan.get(key), str) and TOKEN.fullmatch(plan[key]), 'PLAN_ID_INVALID:' + key)
        target = plan.get('target', {})
        require(target.get('id') == TARGET_ID and target.get('auto_number') == CODE and
                target.get('published') == 0 and target.get('status') == 'kr_bought' and
                'publish_pending' in target, 'PLAN_TARGET_SCOPE_INVALID')
        require(HEX.fullmatch(str(target.get('expected_row_sha256', ''))), 'PLAN_ROW_DIGEST_REQUIRED')
        require(plan.get('alwayson_id') == CRM_ALWAYS_ON, 'PLAN_CRM_SCOPE_INVALID')
        require(set(plan.get('runtime_entrypoint_sha256', {})) == {'start_safe.py', 'run_all.py'},
                'RUNTIME_ENTRYPOINT_BINDING_REQUIRED')
        for name, expected in plan['runtime_entrypoint_sha256'].items():
            require(HEX.fullmatch(str(expected)) and sha(read(ROOT / name)) == expected,
                    'RUNTIME_ENTRYPOINT_SHA_MISMATCH:' + name)
        # Controllers bind exact canonical plan.json bytes, including newline.
        # Row digests deliberately use compact JSON without a trailing newline.
        self.plan_sha = sha(encoded(plan) + b'\n')
        expected_backup = ROOT / 'rezerv_publikacii' / (plan['task_id'] + '-' + plan['nonce'])
        require(plan.get('backup_dir') == str(expected_backup), 'PLAN_BACKUP_PATH_INVALID')
        require(plan.get('receipt_dir') == str(expected_backup), 'PLAN_RECEIPT_PATH_INVALID')
        self.backup = expected_backup
        self.journal_path = self.backup / 'transaction.json'
        self.manifest_path = self.backup / 'backup_manifest.json'
        required_package = {'build_candidate.py', 'publication_fence.py', 'remote_installer.py'}
        require(set(plan.get('package_sha256', {})) == required_package, 'PACKAGE_BINDING_INCOMPLETE')
        for name, expected in plan['package_sha256'].items():
            require(HEX.fullmatch(str(expected)) and sha(read(self.package / name)) == expected,
                    'PACKAGE_SHA_MISMATCH:' + name)
        self.builder = load_module('_ua0022_bound_builder', self.package / 'build_candidate.py')
        require(plan.get('source_sha256') == self.builder.SOURCE_SHA256, 'SOURCE_BINDING_MISMATCH')
        require(plan.get('helper_sha256') == self.builder.HELPER_SHA256, 'HELPER_BINDING_MISMATCH')
        require(sha(read(self.package / 'publication_fence.py')) == self.builder.HELPER_SHA256,
                'HELPER_SHA_MISMATCH')
        self.helper = load_module('publication_fence', self.package / 'publication_fence.py')

    def lock(self):
        # Legacy publication lock must already exist as well. Keep its inode.
        regular(ROOT / '.ua_art_publish_transaction.lock')
        return self.helper.publication_fence(timeout=90)

    def check_preimage(self):
        assert_native_video_dedup_inert()
        for name, expected in self.plan['runtime_entrypoint_sha256'].items():
            require(sha(read(ROOT / name)) == expected, 'RUNTIME_ENTRYPOINT_CHANGED:' + name)
        for name, expected in self.plan['source_sha256'].items():
            require(sha(read(ROOT / name)) == expected, 'SOURCE_PREIMAGE_CHANGED:' + name)
        require(regular(ROOT / 'publication_fence.py', absent=True) is None, 'HELPER_ALREADY_EXISTS')
        state = db_state()
        row = state['target_row']
        require(state['target_row_sha256'] == self.plan['target']['expected_row_sha256'],
                'TARGET_ROW_PLAN_DIGEST_CHANGED')
        for key in ('id', 'auto_number', 'published', 'status', 'publish_pending'):
            require(row[key] == self.plan['target'][key], 'TARGET_ROW_PLAN_FIELD_CHANGED:' + key)
        return state

    def append_log(self, event):
        path = ROOT / 'publish_log.txt'
        regular(path, absent=True)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
        try:
            line = encoded({'timestamp': int(time.time()), 'task_id': self.plan['task_id'],
                            'nonce': self.plan['nonce'], 'plan_sha256': self.plan_sha,
                            'target': CODE, 'event': event}) + b'\n'
            os.write(fd, line)
            os.fsync(fd)
        finally:
            os.close(fd)

    def journal(self, value=None):
        if value is None:
            value = json_read(self.journal_path)
            require(value.get('plan_sha256') == self.plan_sha, 'JOURNAL_PLAN_MISMATCH')
            return value
        value['plan_sha256'] = self.plan_sha
        json_write(self.journal_path, value)
        return value

    def receipt(self, operation, status, **extra):
        value = {'contract': CONTRACT, 'task_id': self.plan['task_id'], 'nonce': self.plan['nonce'],
                 'plan_sha256': self.plan_sha, 'operation': operation, 'status': status,
                 'target': CODE, 'timestamp': int(time.time()), **extra}
        if self.backup.is_dir():
            json_write(self.backup / (operation + '_receipt.json'), value)
        return value

    def manifest(self):
        manifest = json_read(self.manifest_path)
        journal = self.journal()
        require(manifest.get('plan_sha256') == self.plan_sha, 'BACKUP_PLAN_MISMATCH')
        require(sha(read(self.manifest_path)) == journal['backup_manifest_sha256'], 'BACKUP_MANIFEST_SHA_MISMATCH')
        for relative, info in manifest['files'].items():
            if info['exists']:
                data = gzip.decompress(read(self.backup / info['stored']))
                require(sha(data) == info['sha256'], 'BACKUP_FILE_SHA_MISMATCH:' + relative)
        require(sha(read(self.backup / 'crm.snapshot.db')) == manifest['database_backup_sha256'],
                'BACKUP_DATABASE_SHA_MISMATCH')
        return manifest

    def backup_phase(self):
        if self.backup.exists():
            journal = self.journal()
            require(journal['state'] == 'BACKED_UP', 'BACKUP_ALREADY_USED')
            manifest = self.manifest()
            self.revalidate_backup(manifest)
            return self.receipt('backup', 'PASS', backup_manifest_sha256=journal['backup_manifest_sha256'],
                                backup_root=str(self.backup), source_checksum_pass=True,
                                integrity_pass=True, idempotent=True)
        before = self.check_preimage()
        before_pages = public_snapshot()
        before_protected = protected_pages()
        root = self.backup.parent
        require(root.is_dir() and root.resolve() == root, 'BACKUP_PARENT_REQUIRED')
        self.backup.mkdir(mode=0o700)
        (self.backup / 'files').mkdir(mode=0o700)
        self.journal({'state': 'BACKUP_STARTED'})
        files = fingerprints({ROOT / name for name in self.plan['source_sha256']} |
                             {ROOT / name for name in self.plan['runtime_entrypoint_sha256']} |
                             {ROOT / 'publication_fence.py'} | public_paths())
        total = sum(item.get('bytes', 0) for item in files.values())
        require(total <= MAX_BACKUP_BYTES and len(files) <= MAX_FILES, 'BACKUP_BOUND_EXCEEDED')
        require(os.statvfs(self.backup).f_bavail * os.statvfs(self.backup).f_frsize > total +
                2 * regular(ROOT / 'crm.db').st_size + 64 * 1024 * 1024, 'BACKUP_FREE_SPACE_INSUFFICIENT')
        for index, (relative, info) in enumerate(sorted(files.items())):
            if info['exists']:
                stored = 'files/' + str(index) + '.gz'
                data = read(ROOT / relative)
                require(sha(data) == info['sha256'], 'BACKUP_SOURCE_CHANGED:' + relative)
                atomic(self.backup / stored, gzip.compress(data, compresslevel=6, mtime=0))
                require(sha(gzip.decompress(read(self.backup / stored))) == info['sha256'],
                        'BACKUP_READBACK_FAILED:' + relative)
                info['stored'] = stored
        conn = connection()
        destination = sqlite3.connect(self.backup / 'crm.snapshot.db')
        try:
            integrity(conn)
            conn.backup(destination)
            destination.commit()
            integrity(destination)
        finally:
            destination.close()
            conn.close()
        os.chmod(self.backup / 'crm.snapshot.db', 0o600)
        compare_invariants(before, db_state(), 0)
        require(public_snapshot() == before_pages, 'PUBLIC_FILES_CHANGED_DURING_BACKUP')
        require(protected_pages() == before_protected, 'PROTECTED_FILES_CHANGED_DURING_BACKUP')
        self.check_preimage()
        manifest = {'plan_sha256': self.plan_sha, 'files': files, 'public_preimage': before_pages,
                    'protected_preimage': before_protected, 'database_state': before,
                    'database_backup_sha256': sha(read(self.backup / 'crm.snapshot.db')),
                    'database_integrity': 'ok', 'timestamp': int(time.time())}
        json_write(self.manifest_path, manifest)
        manifest_sha = sha(read(self.manifest_path))
        self.journal({'state': 'BACKED_UP', 'backup_manifest_sha256': manifest_sha,
                      'source_postimages': {}, 'public_postimage': None, 'db_write_intended': False})
        self.append_log('BACKUP_PASS')
        return self.receipt('backup', 'PASS', backup_manifest_sha256=manifest_sha,
                            backup_root=str(self.backup), source_checksum_pass=True, integrity_pass=True)

    def revalidate_backup(self, manifest):
        self.check_preimage()
        compare_invariants(manifest['database_state'], db_state(), 0)
        require(public_snapshot() == manifest['public_preimage'], 'PUBLIC_PREIMAGE_CHANGED_SINCE_BACKUP')
        require(protected_pages() == manifest['protected_preimage'], 'PROTECTED_PREIMAGE_CHANGED_SINCE_BACKUP')

    def install_phase(self):
        journal = self.journal()
        manifest = self.manifest()
        if journal['state'] == 'COMMITTED':
            media_evidence = self.verify_committed(manifest, journal)
            return self.receipt('install_verify', 'PASS', idempotent=True,
                                backup_manifest_sha256=journal['backup_manifest_sha256'],
                                publication_pass=True, post_check_pass=True, integrity_pass=True,
                                protected_pages_unchanged=True, other_rows_unchanged=True,
                                ua_ge_prices_unchanged=True, **media_evidence,
                                source_after_sha256=journal['source_postimages'],
                                public_http_sha256=public_http_sha256(),
                                public_url='https://www.uaart.com.ua/video/UA-0022.html')
        require(journal['state'] == 'BACKED_UP', 'INSTALL_REQUIRES_UNUSED_BACKUP')
        self.revalidate_backup(manifest)
        candidate = {name: self.builder.transform(name, read(ROOT / name).decode('utf-8')).encode('utf-8')
                     for name in MUTATED_SOURCES}
        candidate['publication_fence.py'] = read(self.package / 'publication_fence.py')
        for name, data in candidate.items():
            compile(data, name, 'exec')
        # Declare every own postimage before the first write, permitting CAS rollback.
        journal.update(state='INSTALLING', source_postimages={name: sha(data) for name, data in candidate.items()})
        self.journal(journal)
        try:
            for name, data in candidate.items():
                info = manifest['files'][name]
                expected = {key: value for key, value in info.items() if key != 'stored'}
                require(fingerprint(ROOT / name) == expected, 'SOURCE_INSTALL_CAS_FAILED:' + name)
                atomic(ROOT / name, data, info.get('mode', 0o600))
                require(sha(read(ROOT / name)) == journal['source_postimages'][name],
                        'SOURCE_INSTALL_READBACK_FAILED:' + name)
            journal.update(state='DB_WRITE_INTENDED', db_write_intended=True)
            self.journal(journal)
            cas_published(manifest['database_state']['target_row'], 1)
            journal['state'] = 'PUBLISHING'
            self.journal(journal)
            self.append_log('PUBLICATION_STARTED')
            previous_cwd = Path.cwd()
            old_path = list(sys.path)
            try:
                os.chdir(ROOT)
                sys.path.insert(0, str(ROOT))
                sys.dont_write_bytecode = True
                importlib.invalidate_caches()
                require('publikaciya' not in sys.modules, 'PUBLISHER_PRELOADED')
                log_path = self.backup / 'publisher_execution.log'
                regular(log_path, absent=True)
                with open(log_path, 'a', encoding='utf-8') as output:
                    os.chmod(log_path, 0o600)
                    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                        publisher = importlib.import_module('publikaciya')
                        result = publisher.opublikovat(CODE, proba=False)
                        print('PUBLISH_RESULT', repr(result))
                        require(isinstance(result, (tuple, list)) and len(result) >= 2 and result[0] is True,
                                'PUBLISHER_REPORTED_FAILURE')
                        # Capture mutation postimages before postchecks, inside both locks.
                        journal.update(state='PUBLISHED', public_postimage=public_snapshot())
                        self.journal(journal)
                        guard = importlib.import_module('publish_transaction_guard')
                        evidence = guard.verify_bundle([CODE])
                        require(CODE in evidence.get('targets', {}), 'PUBLISHER_BUNDLE_VERIFY_FAILED')
            finally:
                sys.path[:] = old_path
                os.chdir(previous_cwd)
            media_evidence = self.verify_committed(manifest, journal)
            conn = connection()
            try:
                integrity(conn)
            finally:
                conn.close()
            journal['state'] = 'COMMITTED'
            self.journal(journal)
            self.append_log('INSTALL_PUBLICATION_PASS')
            return self.receipt('install_verify', 'PASS',
                                backup_manifest_sha256=journal['backup_manifest_sha256'],
                                publication_pass=True, post_check_pass=True, integrity_pass=True,
                                protected_pages_count=len(manifest['protected_preimage']),
                                protected_pages_unchanged=True, other_rows_unchanged=True,
                                ua_ge_prices_unchanged=True, **media_evidence,
                                source_after_sha256=journal['source_postimages'],
                                public_http_sha256=public_http_sha256(),
                                public_url='https://www.uaart.com.ua/video/UA-0022.html')
        except BaseException as exc:
            # These postimages are attributable to this invocation: CRM was
            # paused and both locks have remained held without interruption.
            journal = self.journal()
            journal['public_postimage'] = public_snapshot()
            journal['failure_type'] = type(exc).__name__
            journal['state'] = 'FAILED_WITH_BOUND_POSTIMAGES'
            self.journal(journal)
            rollback = self.rollback_phase()
            self.append_log('INSTALL_FAILED_ROLLBACK_' + rollback['status'])
            return self.receipt('install_verify', 'FAIL', error_code=str(exc) if isinstance(exc, Stop)
                                else type(exc).__name__, rollback_status=rollback['status'],
                                backup_manifest_sha256=journal['backup_manifest_sha256'])

    def verify_committed(self, manifest, journal):
        for name, expected in journal['source_postimages'].items():
            require(sha(read(ROOT / name)) == expected, 'INSTALLED_SOURCE_CHANGED:' + name)
        require(sha(read(ROOT / 'publikaciya.py')) == self.plan['source_sha256']['publikaciya.py'],
                'UNMODIFIED_PUBLISHER_CHANGED')
        compare_invariants(manifest['database_state'], db_state(), 1)
        conn = connection()
        try:
            integrity(conn)
        finally:
            conn.close()
        require(protected_pages() == manifest['protected_preimage'], 'PROTECTED_PAGES_CHANGED')
        current = public_snapshot()
        require(journal.get('public_postimage') == current, 'PUBLIC_POSTIMAGE_CHANGED')
        for relative, before in manifest['public_preimage'].items():
            if '/foto/' in '/' + relative or '/diag/' in '/' + relative or relative.startswith('archive/'):
                require(current.get(relative) == before, 'TARGET_MEDIA_CHANGED')
        def is_media(relative):
            return ('/foto/' in '/' + relative or '/diag/' in '/' + relative or
                    relative.startswith('archive/'))
        media_before = {k for k in manifest['public_preimage'] if is_media(k)}
        media_after = {k for k in current if is_media(k)}
        require(media_before <= media_after, 'TARGET_MEDIA_REMOVED')
        additions = media_after - media_before
        for relative in additions:
            parts = Path(relative).parts
            # The bound native renderer may first create its m/s JPEG
            # variants. Permit only variants of an original protected by this
            # transaction, at the exact PAPKA_VID subtree used by umenshit.
            require(len(parts) == 5 and parts[:3] == ('video', 'foto', CODE) and
                    parts[3] in ('m', 's') and parts[4].endswith('.jpg'),
                    'TARGET_MEDIA_ADDITION_OUT_OF_SCOPE')
            original = str(Path('video') / 'foto' / CODE / parts[4])
            require(original in media_before and manifest['public_preimage'][original].get('exists'),
                    'TARGET_DERIVATIVE_ORIGINAL_NOT_BOUND')
        return {'target_media_unchanged': not additions,
                'target_original_media_unchanged': True,
                'target_new_media_derivatives_only': True,
                'target_media_derivatives_added': len(additions)}

    def rollback_phase(self):
        journal = self.journal()
        manifest = self.manifest()
        if journal['state'] == 'BACKED_UP':
            # Admission can fail because an operator changed a row/page after
            # the backup phase. No install write has occurred at BACKED_UP.
            # Do not restore that old snapshot or require external data stale.
            return self.receipt('rollback', 'PASS', no_mutation=True,
                                target_and_sources_untouched_by_installer=True,
                                public_http_sha256=public_http_sha256(),
                                backup_manifest_sha256=journal['backup_manifest_sha256'])
        if journal['state'] == 'ROLLED_BACK':
            self.revalidate_backup(manifest)
            return self.receipt('rollback', 'PASS', idempotent=True,
                                public_http_sha256=public_http_sha256(),
                                backup_manifest_sha256=journal['backup_manifest_sha256'])
        require(journal['state'] != 'BACKUP_STARTED', 'ROLLBACK_BACKUP_INCOMPLETE')
        if journal['state'] == 'PUBLISHING' and journal.get('public_postimage') is None:
            raise Stop('AMBIGUOUS_PUBLICATION_POSTIMAGE_RECOVERY_REQUIRES_REVIEW')
        require(protected_pages() == manifest['protected_preimage'], 'ROLLBACK_PROTECTED_PAGES_CHANGED')
        require(sha(read(ROOT / 'publikaciya.py')) == self.plan['source_sha256']['publikaciya.py'],
                'ROLLBACK_UNMODIFIED_PUBLISHER_CHANGED')
        before = manifest['database_state']
        after_row = dict(before['target_row'])
        after_row['published'] = 1
        current_state = db_state()
        require(current_state['target_row'] in (before['target_row'], after_row), 'ROLLBACK_TARGET_ROW_CAS_FAILED')
        compare_invariants(before, current_state, current_state['target_row']['published'])
        # Check all source and public pre/postimages before restoring anything.
        for name, after_sha in journal['source_postimages'].items():
            current = fingerprint(ROOT / name)
            original = manifest['files'][name]
            pre = {key: value for key, value in original.items() if key != 'stored'}
            is_post = (current.get('exists') and current.get('sha256') == after_sha and
                       current.get('mode') == original.get('mode', 0o600))
            require(current == pre or is_post, 'ROLLBACK_SOURCE_CAS_FAILED:' + name)
        allowed_post = journal.get('public_postimage') or manifest['public_preimage']
        current_public = public_snapshot()
        for relative in set(current_public) | set(manifest['public_preimage']) | set(allowed_post):
            current = current_public.get(relative, {'exists': False})
            pre = manifest['public_preimage'].get(relative, {'exists': False})
            post = allowed_post.get(relative, {'exists': False})
            require(current in (pre, post), 'ROLLBACK_PUBLIC_CAS_FAILED:' + relative)
        journal['state'] = 'ROLLING_BACK'
        self.journal(journal)
        if current_state['target_row'] == after_row:
            cas_published(after_row, before['target_row']['published'])
        for relative, info in manifest['files'].items():
            if relative in self.plan['runtime_entrypoint_sha256'] or (
                    relative in self.plan['source_sha256'] and relative not in MUTATED_SOURCES):
                continue
            path = ROOT / relative
            pre = {key: value for key, value in info.items() if key != 'stored'}
            if fingerprint(path) == pre:
                continue
            if info['exists']:
                data = gzip.decompress(read(self.backup / info['stored']))
                require(sha(data) == info['sha256'], 'ROLLBACK_BACKUP_SHA_FAILED')
                atomic(path, data, info['mode'])
            else:
                path.unlink(missing_ok=True)
        for relative in set(current_public) - set(manifest['public_preimage']):
            path = ROOT / relative
            if regular(path, absent=True) is not None:
                path.unlink()
        self.revalidate_backup(manifest)
        journal['state'] = 'ROLLED_BACK'
        self.journal(journal)
        self.append_log('ROLLBACK_PASS')
        return self.receipt('rollback', 'PASS', backup_manifest_sha256=journal['backup_manifest_sha256'],
                            targeted_files_restored=True, target_flag_restored=True,
                            protected_pages_unchanged=True, other_rows_unchanged=True,
                            public_http_sha256=public_http_sha256(),
                            whole_database_restore_performed=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--operation', required=True, choices=('backup', 'install_verify', 'rollback'))
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    try:
        plan_bytes = read(args.plan.resolve(strict=True))
        plan = json.loads(plan_bytes.decode('utf-8'))
        require(plan_bytes == encoded(plan) + b'\n', 'PLAN_CANONICAL_BYTES_REQUIRED')
        if args.plan_sha256:
            require(sha(plan_bytes) == args.plan_sha256, 'PLAN_SHA_MISMATCH')
        installer = Installer(plan, Path(__file__).resolve().parent)
        with singleton():
            with installer.lock():
                method = {'backup': installer.backup_phase, 'install_verify': installer.install_phase,
                          'rollback': installer.rollback_phase}[args.operation]
                result = method()
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result['status'] == 'PASS' else 2
    except BaseException as exc:
        # Never serialize arbitrary publisher exception text or private rows.
        code = str(exc) if isinstance(exc, Stop) else type(exc).__name__
        result = {'operation': args.operation, 'status': 'BLOCKED', 'error_code': code,
                  'target': CODE, 'timestamp': int(time.time())}
        if 'installer' in locals():
            result = installer.receipt(args.operation, 'BLOCKED', error_code=code)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
