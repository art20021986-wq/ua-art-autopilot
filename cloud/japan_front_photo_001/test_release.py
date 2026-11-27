"""The JAPAN-FRONT-PHOTO candidate: everything as JAPAN-LHD-FIX-INSTALL-R3 installed it; only lot_page.py and job.py change."""
import io
from pathlib import Path
import sys
import unittest
import zipfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import deployment_transport  # noqa: E402


def installed():
    """The files as JAPAN-LHD-FIX-INSTALL-R3 installed them (its package in this repository) and the live Korea page."""
    package = HERE.parent / 'japan_lhd_fix_001'
    source = {name: (package / name).read_bytes() for name in candidate_builder.INSTALLED_SHA256
              if name != candidate_builder.LAUNCHER}
    source[candidate_builder.LAUNCHER] = candidate_builder.LAUNCHER_SOURCE
    source[candidate_builder.KOREA] = (HERE / 'fixtures' / 'korea_live.html').read_bytes()
    return source


class FakeAPI:
    def __init__(self):
        self.files = {}

    def upload(self, path, payload):
        self.files[path] = payload


class CandidateTests(unittest.TestCase):
    def bundle(self):
        api = FakeAPI()
        digest = deployment_transport.upload_package(api)
        return zipfile.ZipFile(io.BytesIO(api.files[deployment_transport.INBOX + '/jfront1-' + digest + '.zip']))

    def test_zip_carries_both_collectors_flat(self):
        names = self.bundle().namelist()
        for module in candidate_builder.MODULES:
            self.assertIn('kauc_%s.py' % module, names)
        for module in candidate_builder.JAPAN_MODULES:
            self.assertIn('jauc_%s.py' % module, names)
        self.assertIn('japan_page.py', names)
        self.assertTrue(all('/' not in name for name in names))

    def test_candidate(self):
        archive = self.bundle()
        unpacked = Path(self._tmp())
        for name in archive.namelist():
            (unpacked / name).write_bytes(archive.read(name))
        files = candidate_builder.build(installed(), {}, here=unpacked, sha=deployment_transport.sha)
        self.assertEqual(set(files), {'korea_auction/__init__.py', 'japan_auction/__init__.py', candidate_builder.LAUNCHER,
                                      candidate_builder.JAPAN}
                         | {'korea_auction/%s.py' % m for m in candidate_builder.MODULES}
                         | {'japan_auction/%s.py' % m for m in candidate_builder.JAPAN_MODULES})
        self.assertNotIn(candidate_builder.KOREA, files)  # the Korea page stays as it is
        japan = files[candidate_builder.JAPAN].decode('utf-8')
        self.assertIn('fetch("/video/japan/lots.json"', japan)
        self.assertIn('Авто з усіх країн під ключ', japan)  # the site-wide offer stays
        self.assertNotIn('/api/auction/bid', japan)
        for folder, modules in (('korea_auction', candidate_builder.MODULES), ('japan_auction', candidate_builder.JAPAN_MODULES)):
            for module in modules:
                self.assertEqual(files['%s/%s.py' % (folder, module)], (HERE / folder / (module + '.py')).read_bytes())
        for name, value in files.items():
            if name.endswith('.py'):
                compile(value, name, 'exec')
        self.assertIn(b'from japan_auction import job', files[candidate_builder.LAUNCHER])
        self.assertFalse(any(candidate_builder.is_page(name) for name in files))

    def test_only_the_japan_job_and_lot_page_differ_from_the_install(self):
        """The release never rolls back another install: only japan_auction/lot_page.py and job.py change."""
        live = installed()
        for folder, modules in (('korea_auction', candidate_builder.MODULES), ('japan_auction', candidate_builder.JAPAN_MODULES)):
            for module in modules:
                name = '%s/%s.py' % (folder, module)
                self.assertEqual((HERE / name).read_bytes() != live[name],
                                 name in ('japan_auction/job.py', 'japan_auction/lot_page.py', 'japan_auction/views.py'), name)

    def test_the_japan_page_changes_only_the_count_line(self):
        """Owner 27.11 «да»: no «десятки авто» (about 10 left-hand-drive cars a week)."""
        import japan_page
        page = japan_page.build((HERE / 'fixtures' / 'korea_live.html').read_bytes()).decode('utf-8')
        self.assertIn('Щотижня — авто з лівим кермом з аукціонів Японії.', page)
        self.assertNotIn('десятки', page)

    def test_every_candidate_file_is_an_installed_source(self):
        """JAPAN-LHD-FIX-PREFLIGHT halted on NEW_FILE_EXISTS:video/japan.html — nothing in this fix is a new file."""
        archive = self.bundle()
        unpacked = Path(self._tmp())
        for name in archive.namelist():
            (unpacked / name).write_bytes(archive.read(name))
        source = installed()
        source[candidate_builder.JAPAN] = b'installed japan page'
        files = candidate_builder.build(source, {}, here=unpacked, sha=deployment_transport.sha)
        self.assertEqual(set(files) - set(candidate_builder.SOURCE_FILES), set())

    def test_other_installed_collector_is_refused(self):
        source = installed()
        source['japan_auction/job.py'] += b'# edited'
        with self.assertRaises(ValueError):
            candidate_builder.build(source, {}, sha=deployment_transport.sha)

    def test_module_names_and_server_prefix(self):
        for path in HERE.rglob('*.py'):
            self.assertRegex(path.name, r'^[a-z_]+\.py$')
        for name in ('deployment_transport.py', 'deployment_bootstrap.py', 'deployment_remote.py'):
            text = (HERE / name).read_text(encoding='utf-8')
            self.assertNotIn('kplan1', text)
        self.assertIn("/jfront1-", (HERE / 'deployment_transport.py').read_text(encoding='utf-8'))

    def test_pre_install_health_checks_only_existing_pages(self):
        """Run 45936163206 halted on a page that did not exist yet; every page here is live (japan.html since R2)."""
        source = (HERE / 'make_release.py').read_text(encoding='utf-8')
        checks = source[source.index("'health_checks':"):source.index("'production_required': True")]
        for page in ('index', 'korea', 'japan', 'podbor'):
            self.assertIn('/video/%s.html' % page, checks)

    def _tmp(self):
        import tempfile
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return directory.name


if __name__ == '__main__':
    unittest.main()
