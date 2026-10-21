"""Read-only package CLI and offline-tested code-install transaction.

Explicit installation is owned by the separately admitted lifecycle_controller,
which preserves the existing global halt and production authority checks.
"""
from __future__ import annotations
import argparse
import ast
import base64
from contextlib import closing
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import sqlite3
import stat
import time


TASK = 'UA-ART-CRM-DELETE-RECOVERY-002-v1.0'
PRODUCTION_ROOT = Path('/home/Carix')
SUPERVISOR_ID = 266084
SUPERVISOR_COMMAND = 'python3.10 /home/Carix/start_safe.py'
DELETION_TABLES = {'ua_delete_confirmations', 'ua_delete_intents', 'ua_delete_jobs'}
HEX = re.compile(r'[0-9a-f]{64}')


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def canonical_root(root):
    root = Path(root)
    require(root.is_absolute() and root.resolve(strict=True) == root and root.is_dir(),
            'CANONICAL_EXISTING_ROOT_REQUIRED')
    return root


def relative(root, name, *, code=False):
    require(isinstance(name, str) and name == str(PurePosixPath(name)) and
            not name.startswith('/') and '..' not in PurePosixPath(name).parts,
            'EXACT_RELATIVE_PATH_REQUIRED')
    path = root / name
    require(path.resolve(strict=False) == path and not path.is_symlink(), 'SYMLINK_OR_NONCANONICAL_PATH')
    if code:
        require(path.suffix == '.py' and PurePosixPath(name).parts[0] not in ('site', 'video') and
                all(not part.startswith('.') for part in PurePosixPath(name).parts), 'PRIVATE_PYTHON_ONLY')
    return path


def fingerprint(path):
    if not path.exists():
        return None
    info = path.stat(follow_symlinks=False)
    require(stat.S_ISREG(info.st_mode) and not path.is_symlink(), 'REGULAR_FILE_REQUIRED')
    return sha(path.read_bytes())


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic(path, data, mode=0o600):
    temporary = path.with_name(path.name + '.tmp-' + secrets.token_hex(8))
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def application_schema(conn):
    rows = [list(row) for row in conn.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master "
        "WHERE name NOT GLOB 'sqlite_*' ORDER BY type,name") if row[1] not in DELETION_TABLES]
    return sha(encoded(rows))


def application_data(conn):
    """Logical comparison includes WAL-visible committed rows and sequence values."""
    result = {}
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
              if row[0] not in DELETION_TABLES]
    def cell(value):
        if type(value) is bytes:
            return ['bytes', base64.b64encode(value).decode()]
        if type(value) is float:
            return ['float', value.hex()]
        return [type(value).__name__, value]
    for table in tables:
        quoted = '"' + table.replace('"', '""') + '"'
        rows = sorted(encoded([cell(value) for value in row]) for row in conn.execute('SELECT * FROM ' + quoted))
        require(len(rows) <= 200000, 'DATABASE_TABLE_SIZE_REVIEW_REQUIRED')
        result[table] = {'rows': len(rows), 'sha256': sha(b'\n'.join(rows))}
    return sha(encoded({'schema': application_schema(conn), 'tables': result}))


class Package:
    def __init__(self, directory, manifest_sha256):
        self.directory = canonical_root(directory)
        raw = relative(self.directory, 'manifest.json').read_bytes()
        require(HEX.fullmatch(str(manifest_sha256)) and sha(raw) == manifest_sha256, 'MANIFEST_HASH_MISMATCH')
        self.manifest_sha = manifest_sha256
        self.manifest = json.loads(raw)
        m = self.manifest
        require(m.get('format') == 1 and m.get('task') == TASK, 'MANIFEST_CONTRACT')
        require(m.get('root') == str(PRODUCTION_ROOT), 'PRODUCTION_ROOT_BINDING')
        require(m.get('supervisor') == {'id': SUPERVISOR_ID, 'command': SUPERVISOR_COMMAND}, 'SUPERVISOR_BINDING')
        require(HEX.fullmatch(str(m.get('application_schema_sha256'))), 'SCHEMA_BINDING_REQUIRED')
        require(isinstance(m.get('files'), list) and m['files'], 'CODE_PAYLOAD_REQUIRED')
        require(isinstance(m.get('source_guards'), dict) and
                {'db.py', 'run_all.py', 'start_safe.py', 'publication_fence.py'} <= set(m['source_guards']),
                'LIFECYCLE_SOURCE_GUARDS_REQUIRED')
        for name, digest in m['source_guards'].items():
            relative(PRODUCTION_ROOT, name, code=True)
            require(HEX.fullmatch(str(digest)), 'SOURCE_GUARD_SHA_REQUIRED')
        self.files, self.payloads = {}, {}
        for item in m['files']:
            require(set(item) == {'destination', 'before_sha256', 'payload', 'payload_sha256', 'role'},
                    'EXACT_FILE_CONTRACT')
            name = item['destination']
            relative(PRODUCTION_ROOT, name, code=True)
            require(name not in self.files, 'DUPLICATE_DESTINATION')
            require(item['before_sha256'] is None or HEX.fullmatch(str(item['before_sha256'])), 'BASELINE_SHA_REQUIRED')
            require(item['role'] in ('helper', 'writer', 'entrypoint'), 'FILE_ROLE_REQUIRED')
            require((name == 'cars_ui.py') == (item['role'] == 'entrypoint'), 'CARS_UI_ONLY_ENTRYPOINT')
            payload = relative(self.directory, item['payload']).read_bytes()
            require(HEX.fullmatch(str(item['payload_sha256'])) and sha(payload) == item['payload_sha256'], 'PAYLOAD_HASH_MISMATCH')
            compile(payload, name, 'exec')  # No source import/startup.
            self.files[name], self.payloads[name] = item, payload
        require('cars_ui.py' in self.files, 'CARS_UI_ENTRYPOINT_REQUIRED')
        self.schema_source = relative(self.directory, m['deletion_schema']['payload']).read_bytes()
        require(sha(self.schema_source) == m['deletion_schema']['sha256'], 'DELETION_SCHEMA_SOURCE_HASH')
        assignments = [node for node in ast.parse(self.schema_source).body if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == 'SCHEMA' for target in node.targets)]
        require(len(assignments) == 1, 'EXACT_ADDITIVE_SCHEMA_DEFINITION_REQUIRED')
        self.schema = ast.literal_eval(assignments[0].value)
        require(isinstance(self.schema, dict) and set(self.schema) == DELETION_TABLES, 'ADDITIVE_SCHEMA_SCOPE')
        for name, ddl in self.schema.items():
            require(isinstance(ddl, str) and ddl.startswith('CREATE TABLE ' + name + ' ('), 'CREATE_TABLE_ONLY')
        config = m.get('runtime_config')
        require(isinstance(config, dict) and set(config) == {'destination', 'payload', 'payload_sha256', 'before_sha256'} and
                config['destination'] == 'ua_crm_deletion_state/runtime.json' and config['before_sha256'] is None,
                'EXACT_NEW_PRIVATE_RUNTIME_CONFIG_REQUIRED')
        self.runtime_config = config
        self.config_payload = relative(self.directory, config['payload']).read_bytes()
        require(sha(self.config_payload) == config['payload_sha256'], 'RUNTIME_CONFIG_PAYLOAD_HASH')
        parsed = json.loads(self.config_payload)
        require(set(parsed) == {'version', 'application_schema_sha256', 'source_sha256', 'shared', 'shared_routes',
                               'direct_route_prefixes', 'writers_receipt_sha256'} and parsed['version'] == 1 and
                parsed['application_schema_sha256'] == m['application_schema_sha256'] and
                HEX.fullmatch(str(parsed['writers_receipt_sha256'])), 'EXACT_RUNTIME_CONFIG_FIELDS_REQUIRED')
        require(isinstance(parsed['source_sha256'], dict) and
                all(HEX.fullmatch(str(value)) for value in parsed['source_sha256'].values()), 'RUNTIME_SOURCE_HASHES_REQUIRED')
        for name, digest in parsed['source_sha256'].items():
            require(re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*\.py', name), 'RUNTIME_SOURCE_PIN_NAME')
            expected = (self.files[name]['payload_sha256'] if name in self.files else m['source_guards'].get(name))
            require(digest == expected, 'RUNTIME_SOURCE_RELEASE_BINDING_MISMATCH:' + name)
        self.route_patch = m.get('route_patch')
        if self.route_patch is not None:
            route = self.route_patch
            require(set(route) == {'destination', 'before_sha256', 'payload', 'payload_sha256', 'role'} and
                    route['destination'] == '/var/www/www_uaart_com_ua_wsgi.py' and route['role'] == 'route' and
                    HEX.fullmatch(str(route['before_sha256'])), 'EXACT_SEPARATE_WSGI_SCOPE_REQUIRED')
            payload = relative(self.directory, route['payload']).read_bytes()
            require(sha(payload) == route['payload_sha256'], 'WSGI_PAYLOAD_HASH_MISMATCH')
            compile(payload, route['destination'], 'exec')

    def order(self):
        levels = {'helper': 0, 'writer': 1, 'entrypoint': 2}
        return sorted(self.files, key=lambda name: (levels[self.files[name]['role']], name))

    def check_sources(self, root):
        root = canonical_root(root)
        for name, digest in self.manifest['source_guards'].items():
            require(fingerprint(relative(root, name, code=True)) == digest, 'GUARDED_SOURCE_CHANGED:' + name)
        for name, item in self.files.items():
            require(fingerprint(relative(root, name, code=True)) == item['before_sha256'], 'SOURCE_CHANGED:' + name)
        require(fingerprint(relative(root, self.runtime_config['destination'])) is None, 'NEW_RUNTIME_CONFIG_ALREADY_EXISTS')

    def report(self):
        required = {'ua_crm_delete_bot.py', 'ua_crm_resilient_list.py', 'ua_delete_public_guard.py',
                    'ua_delete_runtime.py', 'ua_crm_deleted_routes.py'} | {
                        'ua_crm_deletion_core/' + name + '.py' for name in
                        ('__init__', 'coordinator', 'deletion_state', 'retirement', 'public_write_guard', 'runtime')}
        missing = sorted(required - set(self.files))
        writer_missing = sorted({'cars_ui.py', 'publikaciya.py', 'publish_transaction_guard.py', 'stranica.py',
                                 'ua_spec84_runtime.py', 'ua_spec_permanent.py', 'yadro.py', 'kadry_diagnostiki.py'} - set(self.files))
        return {'status': 'OFFLINE_VALIDATED', 'manifest_sha256': self.manifest_sha,
                'files': len(self.files), 'install_order': self.order(),
                'runtime_payload_missing': missing, 'production_ready': False,
                'writer_payload_missing': writer_missing,
                'separate_wsgi_payload_validated': self.route_patch is not None,
                'runtime_config_payload_validated': True,
                'remaining': ['register and admit the exact controller through the existing critical workflow',
                              'stage and bind the current plan, package, controller sources and authority',
                              'bind the already received installation instruction through normal Gate B authorization',
                              'respect existing unrelated SEO emergency HALT; do not bypass or clear it',
                              'obtain fresh provider/process observations and held live locks',
                              'verify exact WSGI reload, runtime startup and live acceptance after installation'],
                'database_restoration': 'never automatic', 'public_or_media_writes': 0}


def process_inventory():
    """Inspect actual /proc; permission failures are uncertainty, not absence."""
    own = os.getpid()
    ancestors = {own}
    pid = own
    while pid > 1:
        fields = Path('/proc/%d/stat' % pid).read_text().rsplit(')', 1)[1].split()
        pid = int(fields[1])
        ancestors.add(pid)
    rows = []
    for item in Path('/proc').iterdir():
        if not item.name.isdigit() or int(item.name) in ancestors:
            continue
        try:
            if item.stat().st_uid != os.getuid():
                continue
            raw = (item / 'cmdline').read_bytes()
            if not raw:
                continue
            argv = [part.decode('utf-8') for part in raw.rstrip(b'\0').split(b'\0')]
            if 'python' not in Path(argv[0]).name.lower() and not any(x.endswith('.py') for x in argv):
                continue
            argv[0] = Path(argv[0]).name
            rows.append({'pid': int(item.name), 'command_sha256': sha(encoded(argv))})
        except FileNotFoundError:
            continue  # Process demonstrably disappeared during observation.
    return sorted(rows, key=lambda row: row['pid'])


class ExistingLocksLease:
    """Actual cooperative exclusion; does not claim provider/schedule quiescence.

    For production this must sit INSIDE the new authenticated lifecycle owner.
    It never disables, restarts, or signals any process.
    """
    def __init__(self, root, *, allowed_python_sha256=(), inventory=process_inventory, timeout=0):
        self.root = canonical_root(root)
        self.allowed = set(allowed_python_sha256)
        self.inventory = inventory
        require(type(timeout) in (int, float) and 0 <= timeout <= 45, 'BOUNDED_LOCK_TIMEOUT_REQUIRED')
        self.timeout = timeout
        self.descriptors = []

    def __enter__(self):
        deadline = time.monotonic() + self.timeout
        try:
            for name in ('.start_safe.singleton.lock', '.ua_art_publish_transaction.lock'):
                path = relative(self.root, name)
                fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
                self.descriptors.append((path, fd))
                require(stat.S_ISREG(os.fstat(fd).st_mode), 'REGULAR_EXISTING_LOCK_REQUIRED')
                while True:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise
                        time.sleep(min(.05, remaining))
            self.assert_held()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def assert_held(self):
        require(len(self.descriptors) == 2, 'REAL_LOCK_LEASE_REQUIRED')
        for path, fd in self.descriptors:
            opened, linked = os.fstat(fd), path.stat(follow_symlinks=False)
            require(stat.S_ISREG(linked.st_mode) and
                    (opened.st_dev, opened.st_ino) == (linked.st_dev, linked.st_ino), 'LOCK_INODE_CHANGED')
        require(all(row['command_sha256'] in self.allowed for row in self.inventory()), 'UNREVIEWED_ACTIVE_PYTHON_PROCESS')

    def __exit__(self, *_):
        while self.descriptors:
            _, fd = self.descriptors.pop()
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


class CodeInstallTransaction:
    """Code mechanics; callable only inside an owning lifecycle and real locks."""
    def __init__(self, package, root, journal_root, *, fault=lambda phase, name: None,
                 before_entrypoint=lambda: None, before_code_rollback=lambda: None, transaction_id=None):
        self.package, self.root = package, canonical_root(root)
        self.journal_root = canonical_root(journal_root)
        require(not self.journal_root.is_relative_to(self.root / 'site') and
                not self.journal_root.is_relative_to(self.root / 'video') and
                self.journal_root.stat().st_mode & 0o077 == 0, 'PRIVATE_JOURNAL_REQUIRED')
        require(transaction_id is None or (isinstance(transaction_id, str) and
                re.fullmatch(r'tx-[A-Za-z0-9._-]{16,120}', transaction_id)), 'INSTALL_TRANSACTION_ID_REQUIRED')
        suffix = '' if transaction_id is None else '-' + sha(transaction_id.encode())[:20]
        self.folder = self.journal_root / ('install-' + package.manifest_sha[:20] + suffix)
        self.fault = fault
        self.before_entrypoint = before_entrypoint
        self.before_code_rollback = before_code_rollback

    def _connect(self, path=None, readonly=False):
        path = path or self.root / 'crm.db'
        conn = sqlite3.connect(path.as_uri() + ('?mode=ro' if readonly else '?mode=rw'), uri=True, timeout=2)
        conn.execute('PRAGMA foreign_keys=ON')
        return conn

    def _lease(self, lease):
        require(isinstance(lease, ExistingLocksLease) and lease.root == self.root, 'SAME_ROOT_REAL_LOCK_LEASE_REQUIRED')
        lease.assert_held()

    def journal(self, stage, **extra):
        atomic(self.folder / 'journal.json', encoded(dict(stage=stage, manifest_sha256=self.package.manifest_sha, **extra)))

    def backup(self, lease):
        self._lease(lease)
        self.package.check_sources(self.root)
        require(not self.folder.exists(), 'BACKUP_EXISTS_USE_REVIEWED_RECOVERY')
        self.folder.mkdir(mode=0o700)
        self.journal('BACKUP_STARTED')
        files = {}
        config_name = self.package.runtime_config['destination']
        names = sorted(set(self.package.files) | set(self.package.manifest['source_guards']) | {config_name})
        for i, name in enumerate(names):
            path = relative(self.root, name, code=name != config_name)
            digest = fingerprint(path)
            item = {'sha256': digest, 'stored': None, 'mode': None}
            if digest is not None:
                item.update(stored='%d.before' % i, mode=path.stat().st_mode & 0o777)
                atomic(self.folder / item['stored'], path.read_bytes())
                require(fingerprint(self.folder / item['stored']) == digest and fingerprint(path) == digest,
                        'SOURCE_BACKUP_CHECKSUM_FAILED')
            files[name] = item
        snapshot = self.folder / 'crm.snapshot.db'
        fd = os.open(snapshot, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        with closing(self._connect(readonly=True)) as source, closing(sqlite3.connect(snapshot)) as target:
            source.execute('BEGIN')
            require(application_schema(source) == self.package.manifest['application_schema_sha256'], 'LIVE_SCHEMA_CHANGED')
            before = application_data(source)
            require(source.execute('PRAGMA integrity_check').fetchall() == [('ok',)], 'LIVE_DATABASE_INTEGRITY_FAILED')
            source.backup(target)
            target.commit()
            require(target.execute('PRAGMA integrity_check').fetchall() == [('ok',)], 'BACKUP_INTEGRITY_FAILED')
            require(application_data(target) == before, 'BACKUP_LOGICAL_CHECKSUM_MISMATCH')
        self._lease(lease)
        self.package.check_sources(self.root)
        database_sha = fingerprint(snapshot)
        fd = os.open(snapshot, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        manifest = {'package_sha256': self.package.manifest_sha, 'files': files,
                    'database_file': snapshot.name, 'database_sha256': database_sha,
                    'database_logical_sha256': before, 'database_integrity': 'ok'}
        raw = encoded(manifest)
        atomic(self.folder / 'backup_manifest.json', raw)
        self.journal('BACKED_UP', backup_manifest_sha256=sha(raw))
        return manifest

    def _manifest(self):
        journal = json.loads((self.folder / 'journal.json').read_bytes())
        require(journal['manifest_sha256'] == self.package.manifest_sha, 'JOURNAL_PACKAGE_DRIFT')
        raw = (self.folder / 'backup_manifest.json').read_bytes()
        require(sha(raw) == journal['backup_manifest_sha256'], 'BACKUP_MANIFEST_HASH_MISMATCH')
        manifest = json.loads(raw)
        require(manifest['package_sha256'] == self.package.manifest_sha, 'BACKUP_PACKAGE_MISMATCH')
        require(fingerprint(self.folder / manifest['database_file']) == manifest['database_sha256'], 'BACKUP_DATABASE_HASH_MISMATCH')
        for item in manifest['files'].values():
            if item['stored']:
                require(fingerprint(self.folder / item['stored']) == item['sha256'], 'BACKUP_SOURCE_HASH_MISMATCH')
        return manifest, sha(raw)

    def apply(self, lease):
        self._lease(lease)
        self.package.check_sources(self.root)
        manifest, manifest_sha = self._manifest()
        require(json.loads((self.folder / 'journal.json').read_bytes())['stage'] == 'BACKED_UP', 'FRESH_BACKED_UP_STATE_REQUIRED')
        with closing(self._connect()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            require(application_data(conn) == manifest['database_logical_sha256'], 'DATABASE_CHANGED_AFTER_BACKUP')
            for name, ddl in self.package.schema.items():
                old = conn.execute('SELECT sql FROM sqlite_master WHERE name=?', (name,)).fetchone()
                if old:
                    require(old[0] == ddl, 'DELETION_SCHEMA_COLLISION')
                else:
                    conn.execute(ddl)
            require(application_data(conn) == manifest['database_logical_sha256'], 'APPLICATION_ROWS_CHANGED')
            conn.commit()
        self.journal('SCHEMA_READY', backup_manifest_sha256=manifest_sha)
        self.fault('schema_committed', '')
        installed = []
        for name in self.package.order():
            self._lease(lease)
            if name == 'cars_ui.py':
                config_path = relative(self.root, self.package.runtime_config['destination'])
                require(fingerprint(config_path) is None, 'NEW_RUNTIME_CONFIG_ALREADY_EXISTS')
                config_path.parent.mkdir(mode=0o700, exist_ok=True)
                require(config_path.parent.stat().st_mode & 0o077 == 0, 'PRIVATE_CONFIG_DIRECTORY_MODE_REQUIRED')
                self.journal('CONFIG_REPLACING', backup_manifest_sha256=manifest_sha, installed=installed)
                atomic(config_path, self.package.config_payload, 0o600)
                require(fingerprint(config_path) == self.package.runtime_config['payload_sha256'] and
                        config_path.stat().st_mode & 0o077 == 0, 'CONFIG_READBACK_FAILED')
                self.fault('runtime_config_written', self.package.runtime_config['destination'])
                self.before_entrypoint()
            path, item = relative(self.root, name, code=True), self.package.files[name]
            require(fingerprint(path) == item['before_sha256'], 'SOURCE_CHANGED_DURING_INSTALL:' + name)
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.journal('REPLACING', backup_manifest_sha256=manifest_sha, installed=installed, replacing=name)
            atomic(path, self.package.payloads[name], manifest['files'][name]['mode'] or 0o600)
            require(fingerprint(path) == item['payload_sha256'], 'INSTALLED_READBACK_FAILED:' + name)
            installed.append(name)
            self.fault('file_replaced', name)
            self.journal('REPLACED', backup_manifest_sha256=manifest_sha, installed=installed)
        with closing(self._connect(readonly=True)) as conn:
            require(conn.execute('PRAGMA integrity_check').fetchall() == [('ok',)] and
                    application_data(conn) == manifest['database_logical_sha256'], 'POSTCHECK_DATABASE_CHANGED')
        self.journal('CODE_INSTALLED_OFFLINE', backup_manifest_sha256=manifest_sha, installed=installed)
        return {'status': 'OFFLINE_CODE_INSTALL_PASS', 'backup_manifest_sha256': manifest_sha,
                'installed': installed, 'schema_additive_only': True,
                'runtime_config_retained_for_audit_on_rollback': True,
                'production_restart_verified': False, 'public_or_media_writes': 0}

    def rollback_code(self, lease):
        self._lease(lease)
        manifest, manifest_sha = self._manifest()
        with closing(self._connect(readonly=True)) as conn:
            found = conn.execute("SELECT 1 FROM sqlite_master WHERE name='ua_delete_intents'").fetchone()
            require(not found or conn.execute('SELECT count(*) FROM ua_delete_intents').fetchone()[0] == 0,
                    'DURABLE_DELETION_EXISTS_FORWARD_RECOVERY_REQUIRED')
        # Check every current image first; a newer operator change stops rollback
        # before any code is restored. Never replace or restore the database.
        for name, item in self.package.files.items():
            require(fingerprint(relative(self.root, name, code=True)) in
                    (item['before_sha256'], item['payload_sha256']), 'NEWER_CODE_PRESERVED:' + name)
        # Persist rollback ownership before restoring either entrypoint. All
        # code images and the durable-intent guard have passed before the WSGI
        # callback can replace its entrypoint or any helper can be removed.
        self.journal('ROLLING_BACK', backup_manifest_sha256=manifest_sha)
        self.before_code_rollback()
        self.fault('rollback_route_restored', '')
        restored = []
        for name in reversed(self.package.order()):
            self._lease(lease)
            path, item = relative(self.root, name, code=True), self.package.files[name]
            current = fingerprint(path)
            require(current in (item['before_sha256'], item['payload_sha256']), 'NEWER_CODE_PRESERVED:' + name)
            if current == item['before_sha256']:
                continue
            saved = manifest['files'][name]
            if saved['stored']:
                atomic(path, (self.folder / saved['stored']).read_bytes(), saved['mode'])
            else:
                path.unlink()
                fsync_directory(path.parent)
            restored.append(name)
            self.fault('file_restored', name)
        self.journal('CODE_ROLLED_BACK_SCHEMA_RETAINED', backup_manifest_sha256=manifest_sha, restored=restored)
        return {'status': 'OFFLINE_CODE_ROLLBACK_PASS', 'restored': restored, 'database_restored': False}


class FixtureInstallTransaction(CodeInstallTransaction):
    """Test-only entrypoint explicitly refuses the actual production root."""
    def __init__(self, package, root, journal_root, **kwargs):
        require(canonical_root(root) != PRODUCTION_ROOT, 'PRODUCTION_LIFECYCLE_NOT_IMPLEMENTED')
        super().__init__(package, root, journal_root, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--check-source-root', type=Path)
    args = parser.parse_args()
    package = Package(args.package, args.manifest_sha256)
    if args.check_source_root:
        package.check_sources(args.check_source_root)
    print(json.dumps(package.report(), sort_keys=True))


if __name__ == '__main__':
    main()
