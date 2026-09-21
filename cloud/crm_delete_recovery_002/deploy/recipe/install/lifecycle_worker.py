"""Local worker for the separately admitted lifecycle; never runs on import."""
from contextlib import closing
import fcntl
import json
import os
from pathlib import Path
import time

from package_install import (CodeInstallTransaction, ExistingLocksLease, PRODUCTION_ROOT,
    application_data, application_schema, atomic, canonical_root, encoded, fingerprint, relative, require, sha)


class WsgiChange:
    def __init__(self, package, folder, path=Path('/var/www/www_uaart_com_ua_wsgi.py')):
        require(package.route_patch is not None, 'EXACT_WSGI_RELEASE_REQUIRED')
        self.package, self.folder, self.path = package, Path(folder), Path(path)
        self.item = package.route_patch
        require(self.path.is_absolute() and self.path.resolve(strict=True) == self.path and
                self.path.is_file(), 'CANONICAL_EXISTING_WSGI_REQUIRED')
        self.payload = relative(package.directory, self.item['payload']).read_bytes()
        require(sha(self.payload) == self.item['payload_sha256'], 'WSGI_PAYLOAD_CHANGED')

    def backup(self):
        require(fingerprint(self.path) == self.item['before_sha256'], 'WSGI_BASELINE_CHANGED')
        raw = self.path.read_bytes()
        atomic(self.folder / 'wsgi.before', raw)
        require(fingerprint(self.folder / 'wsgi.before') == self.item['before_sha256'], 'WSGI_BACKUP_CHECKSUM')
        atomic(self.folder / 'wsgi.json', encoded({'stage': 'BACKED_UP',
            'package_manifest_sha256': self.package.manifest_sha, 'mode': self.path.stat().st_mode & 0o777}))

    def _journal(self):
        value = json.loads((self.folder / 'wsgi.json').read_bytes())
        require(value['package_manifest_sha256'] == self.package.manifest_sha and
                fingerprint(self.folder / 'wsgi.before') == self.item['before_sha256'], 'WSGI_BACKUP_BINDING')
        return value

    def install(self):
        value = self._journal()
        require(fingerprint(self.path) == self.item['before_sha256'], 'WSGI_CURRENT_CHANGED')
        value['stage'] = 'REPLACING'
        atomic(self.folder / 'wsgi.json', encoded(value))
        atomic(self.path, self.payload, value['mode'])
        require(fingerprint(self.path) == self.item['payload_sha256'], 'WSGI_AFTER_READBACK')
        value['stage'] = 'REPLACED'
        atomic(self.folder / 'wsgi.json', encoded(value))

    def rollback_preflight(self):
        self._journal()
        require(fingerprint(self.path) in (self.item['before_sha256'], self.item['payload_sha256']),
                'NEWER_WSGI_PRESERVED')

    def rollback(self):
        self.rollback_preflight()
        value = self._journal()
        if fingerprint(self.path) != self.item['before_sha256']:
            atomic(self.path, (self.folder / 'wsgi.before').read_bytes(), value['mode'])
        require(fingerprint(self.path) == self.item['before_sha256'], 'WSGI_ROLLBACK_READBACK')
        value['stage'] = 'ROLLED_BACK'
        atomic(self.folder / 'wsgi.json', encoded(value))


class InstallWorker:
    """Called only after authenticated admission and observed CRM pause."""
    def __init__(self, package, *, allowed_python_sha256, root=PRODUCTION_ROOT,
                 wsgi_path=Path('/var/www/www_uaart_com_ua_wsgi.py'), inventory=None,
                 fault=lambda phase, name: None, transaction_id=None):
        self.package, self.root = package, canonical_root(root)
        journal = self.root / 'ua_crm_installation_state'
        if not journal.exists():
            journal.mkdir(mode=0o700)
        self.transaction_id = transaction_id
        self.transaction = CodeInstallTransaction(package, self.root, journal, fault=fault, transaction_id=transaction_id)
        self.wsgi = WsgiChange(package, self.transaction.folder, path=wsgi_path)
        self.transaction.before_entrypoint = self.wsgi.install
        self.transaction.before_code_rollback = lambda: self.wsgi.rollback()
        self.allowed = tuple(allowed_python_sha256)
        self.inventory = inventory

    def lease(self):
        # Provider disabling is asynchronous. Wait only on the actual existing
        # process/publication locks, within the watchdog's recovery budget.
        kwargs = {'allowed_python_sha256': self.allowed, 'timeout': 45}
        if self.inventory is not None:
            kwargs['inventory'] = self.inventory
        return ExistingLocksLease(self.root, **kwargs)

    @staticmethod
    def held_singleton_owner(path, pid):
        """Require a real FLOCK owned by this visible process, not a provider flag."""
        path = Path(path)
        require(path.resolve(strict=True) == path and not path.is_symlink(), 'SINGLETON_PATH_CHANGED')
        linked = path.stat()
        device = (os.major(linked.st_dev), os.minor(linked.st_dev), linked.st_ino)
        matches = []
        for line in Path('/proc/locks').read_text().splitlines():
            parts = line.split()
            if len(parts) < 6 or parts[1:4] != ['FLOCK', 'ADVISORY', 'WRITE'] or parts[4] != str(pid):
                continue
            fields = parts[5].split(':')
            if len(fields) == 3 and (int(fields[0],16), int(fields[1],16), int(fields[2])) == device:
                matches.append(line)
        require(len(matches) == 1, 'VISIBLE_CRM_SINGLETON_OWNERSHIP_UNPROVEN')
        fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
        try:
            opened = os.fstat(fd)
            require((opened.st_dev,opened.st_ino) == (linked.st_dev,linked.st_ino), 'SINGLETON_PATH_CHANGED')
            try:
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                pass
            else:
                fcntl.flock(fd,fcntl.LOCK_UN)
                raise RuntimeError('VISIBLE_CRM_SINGLETON_NOT_HELD')
        finally:
            os.close(fd)
        return {'device_major':device[0], 'device_minor':device[1], 'inode':device[2], 'owner_pid':pid}

    def pre_pause_namespace(self):
        """Refuse a remote host whose process namespace cannot prove CRM ownership."""
        matches = []
        for entry in Path('/proc').iterdir():
            if not entry.name.isdigit():
                continue
            try:
                if entry.stat().st_uid != os.getuid():
                    continue
                argv = (entry/'cmdline').read_bytes().rstrip(b'\0').split(b'\0')
                if len(argv) == 2 and Path(argv[0].decode()).name == 'python3.10' and argv[1] == b'/home/Carix/start_safe.py':
                    ticks = (entry/'stat').read_text().rsplit(')',1)[1].split()[19]
                    matches.append((int(entry.name),ticks))
            except FileNotFoundError:
                continue
        require(len(matches) == 1, 'CRM_PROCESS_NAMESPACE_UNPROVEN_BEFORE_PAUSE')
        pid,ticks = matches[0]
        lock = self.held_singleton_owner(self.root/'.start_safe.singleton.lock',pid)
        require(Path('/proc/%d/stat'%pid).read_text().rsplit(')',1)[1].split()[19] == ticks,
                'CRM_PROCESS_IDENTITY_CHANGED_BEFORE_PAUSE')
        return {'status':'CRM_NAMESPACE_VERIFIED', 'pid':pid, 'start_ticks':ticks,
                'lock':lock, 'observed_epoch':time.time()}

    def backup_and_apply(self):
        with self.lease() as lease:
            backup = self._prepare_backup(lease)
            result = self._apply_existing(lease, backup['backup_manifest_sha256'])
        self.verify_images(installed=True)
        return result

    def _prepare_backup(self, lease):
        # Exactly one backup per transaction. A later execute never resnapshots
        # data that changed after the workflow opened that original backup.
        require(not self.transaction.folder.exists(), 'ORIGINAL_BACKUP_EXISTS_USE_VERIFIED_IDENTITY')
        self.transaction.backup(lease)
        self.wsgi.backup()
        code_manifest, code_sha = self.transaction._manifest()
        value = {'format': 1, 'package_manifest_sha256': self.package.manifest_sha,
                 'transaction_id': self.transaction_id, 'code_backup_manifest_sha256': code_sha,
                 'wsgi_before_sha256': self.wsgi.item['before_sha256'],
                 'wsgi_destination': self.wsgi.item['destination'],
                 'wsgi_backup_mode': self.wsgi._journal()['mode']}
        raw = encoded(value)
        atomic(self.transaction.folder / 'phase_backup_manifest.json', raw)
        return self.verify_existing_backup(sha(raw))

    def prepare_backup(self):
        with self.lease() as lease:
            result = self._prepare_backup(lease)
        self.verify_images(installed=False)
        return result

    def verify_existing_backup(self, expected_sha):
        require(isinstance(expected_sha, str) and len(expected_sha) == 64 and
                all(char in '0123456789abcdef' for char in expected_sha), 'EXACT_ORIGINAL_BACKUP_HASH_REQUIRED')
        path = self.transaction.folder / 'phase_backup_manifest.json'
        require(fingerprint(path) == expected_sha, 'ORIGINAL_PHASE_BACKUP_HASH_MISMATCH')
        value = json.loads(path.read_bytes())
        code_manifest, code_sha = self.transaction._manifest()
        expected = {'format': 1, 'package_manifest_sha256': self.package.manifest_sha,
                    'transaction_id': self.transaction_id, 'code_backup_manifest_sha256': code_sha,
                    'wsgi_before_sha256': self.wsgi.item['before_sha256'],
                    'wsgi_destination': self.wsgi.item['destination'],
                    'wsgi_backup_mode': self.wsgi._journal()['mode']}
        require(value == expected, 'ORIGINAL_PHASE_BACKUP_BINDING')
        return {'status': 'BACKUP_VERIFIED', 'backup_manifest_sha256': expected_sha,
                'code_backup_manifest_sha256': code_sha, 'package_manifest_sha256': self.package.manifest_sha,
                'transaction_id': self.transaction_id, 'database_restored': False,
                'backup_manifest': value, 'code_backup_manifest': code_manifest,
                'backup_database_sha256': code_manifest['database_sha256'],
                'backup_database_logical_sha256': code_manifest['database_logical_sha256'],
                'backup_database_integrity': code_manifest['database_integrity'],
                'backup_durable': True, 'public_or_media_writes': 0}

    def _apply_existing(self, lease, expected_sha):
        backup = self.verify_existing_backup(expected_sha)
        result = self.transaction.apply(lease)
        return dict(result, backup_manifest_sha256=backup['backup_manifest_sha256'],
                    code_backup_manifest_sha256=backup['code_backup_manifest_sha256'])

    def apply_existing(self, expected_sha):
        with self.lease() as lease:
            result = self._apply_existing(lease, expected_sha)
        self.verify_images(installed=True)
        return result

    def rollback_existing(self, expected_sha):
        self.verify_existing_backup(expected_sha)
        return self.rollback()

    def perform_phase(self, operation, expected_sha, before_callback, after_callback):
        """Observe the preimage after actual shutdown and keep its lease to apply.

        Provider disabling alone is asynchronous. The phase owner can journal
        its read-back in this callback only after both live locks are held.
        """
        require(operation in ('backup', 'execute', 'rollback'), 'EXACT_WORKER_PHASE_REQUIRED')
        with self.lease() as lease:
            before_callback()
            if operation == 'backup':
                require(expected_sha is None, 'BACKUP_CANNOT_REPLACE_EXISTING_DIGEST')
                result, installed = self._prepare_backup(lease), False
            elif operation == 'execute':
                result, installed = self._apply_existing(lease, expected_sha), True
            else:
                self.verify_existing_backup(expected_sha)
                self.wsgi.rollback_preflight()
                result, installed = self.transaction.rollback_code(lease), False
            self.verify_images(installed=installed)
            after = after_callback()
            if operation == 'execute':
                after['rollback_readiness'] = self.rollback_readiness(lease,expected_sha)
        return {'mechanical': result, 'after': after}

    def rollback_readiness(self, lease, expected_sha):
        self.transaction._lease(lease)
        backup = self.verify_existing_backup(expected_sha)
        self.verify_phase_before('rollback')
        self.wsgi.rollback_preflight()
        with closing(self.transaction._connect(readonly=True)) as conn:
            conn.execute('BEGIN')
            counts = {name:conn.execute('SELECT count(*) FROM '+name).fetchone()[0]
                      for name in sorted(self.package.schema)}
            require(counts['ua_delete_intents'] == 0, 'DURABLE_DELETION_EXISTS_FORWARD_RECOVERY_REQUIRED')
        self.transaction._lease(lease)
        return {'status':'PASS', 'scope':'BACKUP_AND_CODE_RESTORE_READINESS_VERIFIED',
                'backup_manifest_sha256':expected_sha, 'code_backup_manifest_sha256':backup['code_backup_manifest_sha256'],
                'deletion_state_counts':counts, 'code_restore_performed':False,
                'database_restored':False, 'checked_epoch':time.time()}

    def config_readback(self, *, installed):
        config = self.package.runtime_config
        actual = fingerprint(relative(self.root, config['destination']))
        if installed:
            require(actual == config['payload_sha256'], 'RUNTIME_CONFIG_READBACK_CHANGED')
        elif actual is not None:
            # Retention is allowed only for this release's own journaled config
            # write. A coincidentally matching caller-created config is not a
            # baseline, and an arbitrary later config must be preserved/refused.
            path = self.transaction.folder / 'journal.json'
            require(path.is_file(), 'RETAINED_CONFIG_OWNERSHIP_REQUIRED')
            journal = json.loads(path.read_bytes())
            require(journal.get('manifest_sha256') == self.package.manifest_sha and
                    journal.get('stage') in ('CONFIG_REPLACING', 'REPLACING', 'REPLACED',
                        'CODE_INSTALLED_OFFLINE', 'ROLLING_BACK', 'CODE_ROLLED_BACK_SCHEMA_RETAINED') and
                    actual == config['payload_sha256'], 'RETAINED_CONFIG_OWNERSHIP_REQUIRED')
            self.transaction._manifest()
        return actual

    def verify_phase_before(self, operation):
        require(operation in ('backup', 'execute', 'rollback'), 'EXACT_WORKER_PHASE_REQUIRED')
        if operation != 'rollback':
            value = self.verify_images(installed=False)
            require(value['runtime_config_sha256'] is None, 'FRESH_BASELINE_CONFIG_REQUIRED')
            return value
        images, guarded = {}, {}
        for name, item in self.package.files.items():
            images[name] = fingerprint(relative(self.root, name, code=True))
            require(images[name] in (item['before_sha256'], item['payload_sha256']), 'NEWER_CODE_PRESERVED:' + name)
        for name, digest in self.package.manifest['source_guards'].items():
            guarded[name] = fingerprint(relative(self.root, name, code=True))
            require(guarded[name] == digest, 'GUARDED_SOURCE_READBACK_CHANGED:' + name)
        wsgi_sha = fingerprint(self.wsgi.path)
        require(wsgi_sha in (self.wsgi.item['before_sha256'], self.wsgi.item['payload_sha256']), 'NEWER_WSGI_PRESERVED')
        config_sha = self.config_readback(installed=False)
        with closing(self.transaction._connect(readonly=True)) as conn:
            conn.execute('BEGIN')
            require(conn.execute('PRAGMA integrity_check').fetchall() == [('ok',)] and
                    application_schema(conn) == self.package.manifest['application_schema_sha256'], 'DATABASE_SCHEMA_OR_INTEGRITY')
            data_sha = application_data(conn)
        return {'installed': None, 'files_sha256': images, 'guarded_sources_sha256': guarded,
                'runtime_config_sha256': config_sha, 'wsgi_sha256': wsgi_sha,
                'application_schema_sha256': self.package.manifest['application_schema_sha256'],
                'application_data_sha256': data_sha, 'database_integrity': 'ok',
                'database_restored': False, 'public_or_media_writes': 0}

    def deletion_schema_evidence(self, conn, *, installed):
        projection = {}
        for name, expected in sorted(self.package.schema.items()):
            row = conn.execute('SELECT sql FROM sqlite_master WHERE type=? AND name=?', ('table',name)).fetchone()
            projection[name] = row[0] if row else None
            require(projection[name] in (None,expected), 'DELETION_SCHEMA_READBACK_CHANGED:' + name)
        present = sum(value is not None for value in projection.values())
        require(present == 3 if installed else present in (0,3), 'DELETION_SCHEMA_PROJECTION_INCOMPLETE')
        raw = (json.dumps(projection,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8')
        return {'deletion_schema_projection':projection, 'deletion_schema_sha256':sha(raw)}

    def verify_images(self, *, installed):
        images = {}
        guarded = {}
        for name, item in self.package.files.items():
            expected = item['payload_sha256'] if installed else item['before_sha256']
            images[name] = fingerprint(relative(self.root, name, code=True))
            require(images[name] == expected, 'CODE_READBACK_CHANGED:' + name)
        for name, expected in self.package.manifest['source_guards'].items():
            guarded[name] = fingerprint(relative(self.root, name, code=True))
            require(guarded[name] == expected, 'GUARDED_SOURCE_READBACK_CHANGED:' + name)
        expected = self.wsgi.item['payload_sha256'] if installed else self.wsgi.item['before_sha256']
        require(fingerprint(self.wsgi.path) == expected, 'WSGI_READBACK_CHANGED')
        config_sha = self.config_readback(installed=installed)
        with closing(self.transaction._connect(readonly=True)) as conn:
            conn.execute('BEGIN')
            require(conn.execute('PRAGMA integrity_check').fetchall() == [('ok',)] and
                    application_schema(conn) == self.package.manifest['application_schema_sha256'], 'DATABASE_SCHEMA_OR_INTEGRITY')
            data_sha = application_data(conn)
            deletion_schema = self.deletion_schema_evidence(conn,installed=installed)
        return {'installed': installed, 'files_sha256': images, 'guarded_sources_sha256': guarded,
                'runtime_config_sha256': config_sha,
                'wsgi_sha256': expected,
                'application_schema_sha256': self.package.manifest['application_schema_sha256'],
                'application_data_sha256': data_sha, 'database_integrity': 'ok',
                'database_restored': False, 'public_or_media_writes': 0, **deletion_schema}

    def recover(self):
        """No new install on recovery: verify full completion, else restore code."""
        path = self.transaction.folder / 'journal.json'
        if not path.exists():
            self.verify_images(installed=False)
            return 'UNCHANGED'
        journal = json.loads(path.read_bytes())
        require(journal['manifest_sha256'] == self.package.manifest_sha, 'RECOVERY_PACKAGE_DRIFT')
        if journal['stage'] in ('BACKUP_STARTED', 'BACKED_UP'):
            # No DDL/code effect is allowed before BACKED_UP; additive DDL may
            # have committed just before SCHEMA_READY was journalled. It is
            # retained and does not justify replacing any current application.
            self.verify_images(installed=False)
            return 'UNCHANGED'
        if journal['stage'] == 'CODE_INSTALLED_OFFLINE':
            self.transaction._manifest()
            self.verify_images(installed=True)
            return 'INSTALLED'
        if journal['stage'] == 'CODE_ROLLED_BACK_SCHEMA_RETAINED':
            with self.lease():
                self.wsgi.rollback()
            self.verify_images(installed=False)
            return 'ROLLED_BACK'
        with self.lease() as lease:
            self.wsgi.rollback_preflight()
            self.transaction.rollback_code(lease)
        self.verify_images(installed=False)
        return 'ROLLED_BACK'

    def rollback(self):
        with self.lease() as lease:
            self.wsgi.rollback_preflight()
            self.transaction.rollback_code(lease)
        self.verify_images(installed=False)
        return 'ROLLED_BACK'

    def startup(self, *, since_epoch, timeout=45, installed=True):
        """Actual process/receipt read-back, not a claim of a Telegram test."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if not installed:
                    return self._baseline_startup(since_epoch)
                receipt_path = self.root / 'ua_crm_deletion_state/startup.json'
                require(receipt_path.resolve(strict=True) == receipt_path, 'STARTUP_RECEIPT_PATH')
                receipt = json.loads(receipt_path.read_bytes())
                require(receipt['phase'] == 'RUNNING' and receipt['adapter_registered'] is True and
                        receipt['application_running'] is True and receipt['updater_running'] is True and
                        receipt['deletion_job_name'] == 'ua-delete-recovery-002', 'RUNTIME_NOT_RUNNING')
                require(since_epoch <= receipt['observed_epoch'] <= time.time() + 2 and
                        time.time() - receipt['observed_epoch'] <= 60, 'STARTUP_RECEIPT_NOT_FRESH')
                require(receipt['config_sha256'] == self.package.runtime_config['payload_sha256'] and
                        receipt['adapter_source_sha256'] == self.package.files['ua_crm_delete_bot.py']['payload_sha256'],
                        'STARTUP_RELEASE_BINDING')
                pid = receipt['pid']
                require(type(pid) is int and pid > 1, 'STARTUP_PID_REQUIRED')
                ticks = Path('/proc/%d/stat' % pid).read_text().rsplit(')', 1)[1].split()[19]
                require(ticks == receipt['start_ticks'], 'STARTUP_PID_REUSED')
                argv = Path('/proc/%d/cmdline' % pid).read_bytes().rstrip(b'\0').split(b'\0')
                require(len(argv) == 2 and Path(argv[0].decode()).name == 'python3.10' and
                        argv[1].decode() == '/home/Carix/start_safe.py', 'STARTUP_COMMAND_MISMATCH')
                self.verify_images(installed=True)
                return {'status': 'RUNTIME_RUNNING', 'pid': pid, 'start_ticks': ticks,
                        'config_sha256': receipt['config_sha256'], 'live_telegram_action_verified': False}
            except (OSError, ValueError, KeyError, RuntimeError):
                if time.monotonic() >= deadline:
                    break
                time.sleep(.2)
        raise RuntimeError('LIVE_RUNTIME_STARTUP_NOT_CONFIRMED')

    def _baseline_startup(self, since_epoch):
        matches = []
        boot_epoch = time.time() - float(Path('/proc/uptime').read_text().split()[0])
        for entry in Path('/proc').iterdir():
            if not entry.name.isdigit():
                continue
            try:
                if entry.stat().st_uid != os.getuid():
                    continue
                argv = (entry / 'cmdline').read_bytes().rstrip(b'\0').split(b'\0')
                if len(argv) != 2 or Path(argv[0].decode()).name != 'python3.10' or argv[1].decode() != '/home/Carix/start_safe.py':
                    continue
                ticks = int((entry / 'stat').read_text().rsplit(')', 1)[1].split()[19])
                require(boot_epoch + ticks / os.sysconf('SC_CLK_TCK') >= since_epoch - 2, 'BASELINE_PROCESS_NOT_NEW')
                matches.append((int(entry.name), ticks))
            except FileNotFoundError:
                continue
        require(len(matches) == 1, 'EXACT_BASELINE_CRM_PROCESS_REQUIRED')
        lock = self.root / '.start_safe.singleton.lock'
        fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                held = True
            else:
                held = False
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
        require(held, 'BASELINE_SINGLETON_NOT_HELD')
        self.verify_images(installed=False)
        return {'status': 'BASELINE_PROCESS_RUNNING', 'pid': matches[0][0], 'start_ticks': matches[0][1],
                'live_telegram_action_verified': False}
