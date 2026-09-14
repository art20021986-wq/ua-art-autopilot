"""Isolation and secret handling for the one-time new Preview provisioner."""
import contextlib
import getpass
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings

import provision_preview as P


class ProvisionPreviewTest(unittest.TestCase):
    PASSWORD = 'fixture-only-password-2026'

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.target = self.root / 'preview_wsgi.py'
        self.production = self.root / 'production_wsgi.py'
        self.target.write_bytes(b'default new preview fixture')
        self.production.write_bytes(b'protected production fixture')

    def test_fixed_target_rejects_production_before_any_input(self):
        with patch.object(P, 'TARGET', P.PRODUCTION), self.assertRaisesRegex(ValueError, 'EXACT_OBSERVED_PREVIEW_TARGET'):
            P.validate_inputs()

    def test_secret_file_permissions_symlink_and_nonregular_are_rejected(self):
        file = self.root / 'secret'; file.write_text(self.PASSWORD); file.chmod(0o644)
        with self.assertRaisesRegex(ValueError, '0600'): P.checked_read(file, True)
        file.chmod(0o600)
        self.assertEqual(P.checked_read(file, True), self.PASSWORD.encode())
        link = self.root / 'link'; link.symlink_to(file)
        with self.assertRaises(ValueError): P.checked_read(link, True)
        fifo = self.root / 'fifo'; os.mkfifo(fifo, 0o600)
        with self.assertRaisesRegex(ValueError, 'REGULAR_BOUNDED'): P.checked_read(fifo, True)

    def test_missing_tty_does_not_call_getpass(self):
        with patch.object(P.sys.stdin, 'isatty', return_value=False), patch.object(P.getpass, 'getpass') as prompt:
            with self.assertRaisesRegex(ValueError, 'OWNER_TTY_REQUIRED'): P.password_from_owner()
            prompt.assert_not_called()

    def test_getpass_echo_fallback_becomes_error(self):
        def warn(*args): warnings.warn('fixture fallback', getpass.GetPassWarning); return self.PASSWORD
        with patch.object(P.sys.stdin, 'isatty', return_value=True), patch.object(P.getpass, 'getpass', side_effect=warn):
            with self.assertRaises(getpass.GetPassWarning): P.password_from_owner()

    def test_owner_input_requires_matching_strong_password_without_output(self):
        output = io.StringIO()
        with patch.object(P.sys.stdin, 'isatty', return_value=True), patch.object(P.getpass, 'getpass', return_value=self.PASSWORD):
            with contextlib.redirect_stdout(output): self.assertEqual(P.password_from_owner(), self.PASSWORD)
        self.assertEqual(output.getvalue(), '')
        with patch.object(P.sys.stdin, 'isatty', return_value=True), patch.object(P.getpass, 'getpass', side_effect=[self.PASSWORD, 'different']):
            with self.assertRaisesRegex(ValueError, 'CONFIRMATION'): P.password_from_owner()
        for value in ('', 'too-short', 'has-control\ncharacters'):
            with self.subTest(value=value), patch.object(P.sys.stdin, 'isatty', return_value=True), patch.object(P.getpass, 'getpass', return_value=value):
                with self.assertRaisesRegex(ValueError, 'STRONG_NONEMPTY'): P.password_from_owner()

    def test_secret_file_input_is_exact_owner_stage_filename(self):
        path = self.root / 'preview-password.txt'; path.write_text(self.PASSWORD + '\n'); path.chmod(0o600)
        with patch.object(P, 'STAGE', self.root): self.assertEqual(P.password_from_owner(True), self.PASSWORD)

    def test_host_observation_is_get_only_and_filters_credentials(self):
        class Response:
            status = 200
            def __init__(self, value): self.value = value
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, size): return json.dumps(self.value).encode()
        calls = []
        configs = {'domain_name': 'Carix.pythonanywhere.com', 'python_version': '3.10', 'force_https': True,
                   'password_protection_password': 'must-never-leak'}
        class Opener:
            def open(self, request, timeout):
                calls.append((request.method, request.full_url))
                return Response([] if request.full_url.endswith('static_files/') else configs)
        with patch.dict(os.environ, API_TOKEN='private-fixture-token'), patch.object(P.urllib.request, 'build_opener', return_value=Opener()):
            result = P.host_state()
            self.assertNotIn('must-never-leak', json.dumps(result))
            self.assertTrue(all(method == 'GET' and '/webapps/Carix.pythonanywhere.com/' in url for method, url in calls))
            configs['force_https'] = False
            with self.assertRaises(ValueError): P.host_state()
            configs.update(force_https=True, domain_name='www.uaart.com.ua')
            with self.assertRaises(ValueError): P.host_state()

    def test_preview_write_rejects_other_target_and_detects_cas_drift(self):
        with patch.object(P, 'TARGET', self.target), patch.object(P, 'PRODUCTION', self.production):
            with self.assertRaisesRegex(ValueError, 'ONLY_NEW_PREVIEW'): P.replace_new_preview_wsgi(self.production, b'', b'bad')
            with self.assertRaisesRegex(ValueError, 'CHANGED_BEFORE'): P.replace_new_preview_wsgi(self.target, b'wrong-before', b'bad')
        self.assertEqual(self.target.read_bytes(), b'default new preview fixture')
        self.assertEqual(self.production.read_bytes(), b'protected production fixture')

    def test_hardlink_to_production_is_rejected(self):
        self.target.unlink(); os.link(self.production, self.target)
        with patch.object(P, 'TARGET', self.target), patch.object(P, 'PRODUCTION', self.production):
            with self.assertRaisesRegex(ValueError, 'HARDLINK'): P.replace_new_preview_wsgi(self.target, self.target.read_bytes(), b'bad')
        self.assertEqual(self.production.read_bytes(), b'protected production fixture')

    def test_write_failure_restores_only_new_app(self):
        before = self.target.read_bytes()
        real = os.fsync
        calls = []
        def fail_once(fd):
            calls.append(fd)
            if len(calls) == 1: raise OSError('isolated fixture fsync failure')
            return real(fd)
        with patch.object(P, 'TARGET', self.target), patch.object(P, 'PRODUCTION', self.production), patch.object(P.os, 'fsync', side_effect=fail_once):
            with self.assertRaises(OSError): P.replace_new_preview_wsgi(self.target, before, b'candidate')
        self.assertEqual(self.target.read_bytes(), before)
        self.assertEqual(self.production.read_bytes(), b'protected production fixture')

    def make_fixture(self):
        package = self.root / 'package/cloud/task088_v5_preview'; package.mkdir(parents=True, mode=0o700)
        for name, expected in P.RUNTIME.items():
            runtime = Path(P.__file__).resolve().parents[1] / 'task088_v5_preview'
            if not runtime.is_dir(): runtime = Path(P.__file__).with_name('reviewed_runtime')
            raw = (runtime / name).read_bytes()
            self.assertEqual(P.sha(raw), expected)
            P.write_private(package / name, raw)
        candidate = self.root / 'candidate'; (candidate / 'public/video').mkdir(parents=True, mode=0o700)
        html = b'<html><body>Public fixture home</body></html>'
        P.write_private(candidate / 'public/video/index.html', html)
        manifest = {'contract': 'UA-ART-V5-PROTECTED-PREVIEW-1', 'preview_gate': 'NOT_PASSED',
            'source_origin': 'https://www.uaart.com.ua', 'asset_roots': {}, 'files': {
            '/video/index.html': {'storage': 'bundle', 'path': 'public/video/index.html', 'sha256': P.sha(html),
                'bytes': len(html), 'content_type': 'text/html; charset=utf-8'}}}
        raw = P.encode(manifest); P.write_private(candidate / 'manifest.json', raw)
        return P.sha(raw)

    def fixture_patches(self, manifest_sha):
        stack = contextlib.ExitStack()
        for name, value in {'STAGE': self.root, 'TARGET': self.target, 'PRODUCTION': self.production,
            'EXPECTED_DEFAULT_WSGI': P.sha(self.target.read_bytes()), 'EXPECTED_PRODUCTION_WSGI': P.sha(self.production.read_bytes()),
            'EXPECTED_MANIFEST': manifest_sha}.items(): stack.enter_context(patch.object(P, name, value))
        stack.enter_context(patch.object(P, 'validate_inputs', return_value={'fixture': 'validated separately'}))
        stack.enter_context(patch.object(P, 'host_state', return_value={'fixture': 'validated separately'}))
        stack.enter_context(patch.object(P, 'password_from_owner', return_value=self.PASSWORD))
        return stack

    def test_provision_uses_real_auth_gate_before_new_wsgi_write_and_never_persists_plaintext(self):
        manifest_sha = self.make_fixture(); before = self.target.read_bytes(); production = self.production.read_bytes()
        output = io.StringIO()
        with self.fixture_patches(manifest_sha), contextlib.redirect_stdout(output): result = P.provision()
        self.assertEqual(result['auth_selftest']['status'], 'PASS')
        self.assertEqual(Path(result['backup']).read_bytes(), before)
        self.assertEqual(self.production.read_bytes(), production)
        self.assertFalse(result['reload_requested']); self.assertFalse(result['production_written'])
        self.assertNotIn(self.PASSWORD, json.dumps(result) + output.getvalue())
        self.assertNotIn(self.PASSWORD.encode(), self.target.read_bytes())
        config = Path(result['config_path']); self.assertEqual(config.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(self.PASSWORD.encode(), config.read_bytes())
        self.assertEqual(json.loads(config.read_bytes())['basic_auth']['iterations'], 600000)

    def test_auth_gate_failure_cannot_write_wsgi(self):
        manifest_sha = self.make_fixture(); before = self.target.read_bytes()
        with self.fixture_patches(manifest_sha), patch.object(P, 'auth_selftest', side_effect=ValueError('fixture auth failure')):
            with self.assertRaises(ValueError): P.provision()
        self.assertEqual(self.target.read_bytes(), before)

    def test_runtime_tamper_is_rejected_before_code_can_execute(self):
        self.make_fixture()
        runtime = self.root / 'package/cloud/task088_v5_preview'
        source = runtime / 'common.py'
        sentinel = self.root / 'must-not-exist'
        source.write_bytes(source.read_bytes() + ('\nfrom pathlib import Path\nPath(' + repr(str(sentinel)) + ').write_text("executed")\n').encode())
        with self.assertRaisesRegex(ValueError, 'BEFORE_ANY_IMPORT'):
            P.auth_selftest(runtime, self.root / 'unused-config', self.PASSWORD)
        self.assertFalse(sentinel.exists())

    def test_check_only_never_requests_password_or_installs(self):
        output = io.StringIO()
        with patch.object(P.sys, 'argv', ['provision_preview.py', '--check-only']), patch.object(P, 'validate_inputs', return_value={'fixture': True}), \
                patch.object(P, 'password_from_owner') as secret, patch.object(P, 'provision') as install, contextlib.redirect_stdout(output):
            self.assertEqual(P.main(), 0)
            secret.assert_not_called(); install.assert_not_called()
        self.assertFalse(json.loads(output.getvalue())['files_written'])

    def test_post_write_observation_failure_reports_installed_state(self):
        manifest_sha = self.make_fixture()
        with self.fixture_patches(manifest_sha), patch.object(P, 'host_state', side_effect=OSError('fixture unavailable')):
            with self.assertRaises(P.InstalledPreviewVerificationError) as error: P.provision()
        self.assertEqual(P.sha(self.target.read_bytes()), error.exception.wsgi_sha256)
        self.assertTrue(Path(error.exception.backup).is_file())

    def test_last_preflight_failure_cannot_write_wsgi(self):
        manifest_sha = self.make_fixture(); before = self.target.read_bytes()
        with self.fixture_patches(manifest_sha), patch.object(P, 'validate_inputs', side_effect=[{'fixture': 'validated separately'}, ValueError('fixture drift')]):
            with self.assertRaises(ValueError): P.provision()
        self.assertEqual(self.target.read_bytes(), before)


if __name__ == '__main__': unittest.main()
