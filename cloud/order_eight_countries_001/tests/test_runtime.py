import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from ua_order import host, runtime
from ua_order.rate_limit import RateLimit
from ua_order.repository import Repository
from test_bot import CONSENT, ROOT


class RuntimeTest(unittest.TestCase):
    def test_enabled_runtime_uses_explicit_private_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            private = Path(folder)
            Repository(private/'order_requests.db').initialize()
            (private/'session.key').write_bytes(b'offline-only-session-secret-key-32')
            path = private/'settings.json'
            path.write_text(json.dumps({
                'enabled': True, 'storage': 'local_sqlite', 'origin': 'https://example.test',
                'consent_text': CONSENT, 'consent_version': 'offline-test',
                'catalog_path': str(ROOT.parent/'ua_order_ge_8country_guard_016/country_models.json'),
                'strings_path': str(ROOT/'strings.json'), 'media_root': str(ROOT/'web'),
            }))
            with patch.dict('os.environ', {'BOT_TOKEN': '456:offline-only-token'}):
                loaded = runtime.load(path)
            self.assertEqual(loaded.service.repository.path, private/'order_requests.db')
            self.assertEqual(loaded.consent_text, CONSENT)
            self.assertFalse(loaded.allow_request({}, SimpleNamespace(owner='web:test')))
            self.assertTrue(loaded.allow_request({'REMOTE_ADDR':'127.0.0.1'}, SimpleNamespace(owner='web:test')))

    def test_runtime_refuses_test_database_before_connecting(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'settings.json'
            path.write_text(json.dumps({
                'enabled': True, 'storage': 'mysql', 'origin': 'https://example.test',
                'consent_text': CONSENT, 'consent_version': 'offline-test',
                'mysql': {'user': 'Carix', 'database': 'Carix$orders_test'},
            }))
            with patch('ua_order.mysql_repository.MySQLRepository.check_ready') as check:
                with self.assertRaisesRegex(ValueError, 'production orders database'):
                    runtime.load(path)
                check.assert_not_called()

    def test_missing_or_disabled_settings_do_not_create_database_or_change_host(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'settings.json'
            self.assertIsNone(runtime.load(path))
            path.write_text(json.dumps({'enabled': False}))
            self.assertIsNone(runtime.load(path))
            self.assertEqual(list(Path(folder).iterdir()), [path])
        with patch.object(host, 'current', return_value=None):
            original = object()
            self.assertIs(host.mount_application(original), original)
            self.assertIsNone(host.register_customer(original, owner_id=789))

    def test_uninitialized_repository_does_not_create_a_database(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'order_requests.db'
            with self.assertRaises(sqlite3.OperationalError):
                with Repository(path).connection():
                    pass
            self.assertFalse(path.exists())

    def test_config_failure_isolated_from_existing_wsgi_routes_and_bot_handlers(self):
        host.current.cache_clear()
        try:
            with patch.object(runtime, 'load', side_effect=ValueError('network filesystem')):
                with self.assertLogs('ua_order.host', level='ERROR'):
                    self.assertIs(host.current(), host.UNAVAILABLE)
                existing = []
                def application(env, start_response):
                    existing.append(env['PATH_INFO'])
                    return [b'old route']
                wrapped = host.mount_application(application)
                self.assertEqual(wrapped({'PATH_INFO': '/api/prices'}, lambda *_: None), [b'old route'])
                statuses = []
                result = wrapped({'PATH_INFO': '/api/orders/submit'}, lambda status, headers: statuses.append(status))
                self.assertEqual(statuses, ['503 Service Unavailable'])
                self.assertIn(b'temporarily_unavailable', b''.join(result))
                self.assertEqual(existing, ['/api/prices'])
                original = object()
                app = SimpleNamespace(handlers={-1: [original]})
                app.add_handler = lambda handler, group: app.handlers.setdefault(group, []).append(handler)
                host.register_customer(app, owner_id=789)
                self.assertIs(app.handlers[-1][0], original)
                self.assertIn(-2, app.handlers)
        finally:
            host.current.cache_clear()

    def test_network_mount_overrides_local_root_and_blocks_wal(self):
        mounts = '1 0 0:1 / / rw - ext4 /dev/root rw\n2 1 0:2 / /home rw - nfs4 host:/users rw\n'
        self.assertEqual(runtime.storage_filesystem('/home/Carix/orders/db', mounts), 'nfs4')
        self.assertEqual(runtime.storage_filesystem('/var/db', mounts), 'ext4')
        with patch.object(Path, 'read_text', return_value=mounts):
            with self.assertRaisesRegex(ValueError, 'network filesystem'):
                runtime.require_local_storage('/home/Carix/orders/db')

    def test_rate_limit_is_bounded_and_recovers_without_evicting_active_keys(self):
        now = [0]
        limiter = RateLimit(2, seconds=60, capacity=2, clock=lambda: now[0])
        self.assertTrue(limiter.allow('a'))
        self.assertTrue(limiter.allow('a'))
        self.assertFalse(limiter.allow('a'))
        self.assertTrue(limiter.allow('b'))
        self.assertFalse(limiter.allow('c'))
        self.assertFalse(limiter.allow('a'))
        now[0] = 61
        self.assertTrue(limiter.allow('c'))
        self.assertTrue(limiter.allow('a'))


if __name__ == '__main__':
    unittest.main()
