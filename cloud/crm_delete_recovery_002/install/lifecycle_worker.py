"""Local worker for the separately admitted lifecycle; never runs on import."""
from contextlib import closing
import fcntl
import json
import os
from pathlib import Path
import time

from package_install import (CodeInstallTransaction, ExistingLocksLease, PRODUCTION_ROOT,
    application_schema, atomic, canonical_root, encoded, fingerprint, relative, require, sha)


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
                 wsgi_path=Path('/var/www/www_uaart_com_ua_wsgi.py'), inventory=None, fault=lambda phase, name: None):
        self.package, self.root = package, canonical_root(root)
        journal = self.root / 'ua_crm_installation_state'
        if not journal.exists():
            journal.mkdir(mode=0o700)
        self.transaction = CodeInstallTransaction(package, self.root, journal, fault=fault)
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

    def backup_and_apply(self):
        with self.lease() as lease:
            self.transaction.backup(lease)
            self.wsgi.backup()
            result = self.transaction.apply(lease)
        self.verify_images(installed=True)
        return result

    def verify_images(self, *, installed):
        for name, item in self.package.files.items():
            expected = item['payload_sha256'] if installed else item['before_sha256']
            require(fingerprint(relative(self.root, name, code=True)) == expected, 'CODE_READBACK_CHANGED:' + name)
        expected = self.wsgi.item['payload_sha256'] if installed else self.wsgi.item['before_sha256']
        require(fingerprint(self.wsgi.path) == expected, 'WSGI_READBACK_CHANGED')
        if installed:
            require(fingerprint(relative(self.root, self.package.runtime_config['destination'])) ==
                    self.package.runtime_config['payload_sha256'], 'RUNTIME_CONFIG_READBACK_CHANGED')
        with closing(self.transaction._connect(readonly=True)) as conn:
            require(conn.execute('PRAGMA integrity_check').fetchall() == [('ok',)] and
                    application_schema(conn) == self.package.manifest['application_schema_sha256'], 'DATABASE_SCHEMA_OR_INTEGRITY')

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
