"""The JAPAN-LHD-FIX candidate: everything as JAPAN-LHD-INSTALL-R2 installed it, with only japan_auction/job.py changed."""
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
    """The files as JAPAN-LHD-INSTALL-R2 installed them (its package in this repository) and the live Korea page."""
    package = HERE.parent / 'japan_lhd_001'
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
        return zipfile.ZipFile(io.BytesIO(api.files[deployment_transport.INBOX + '/jlfix1-' + digest + '.zip']))

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

    def test_only_the_japan_job_differs_from_the_install(self):
        """The fix never rolls back another install: only japan_auction/job.py changes."""
        live = installed()
        for folder, modules in (('korea_auction', candidate_builder.MODULES), ('japan_auction', candidate_builder.JAPAN_MODULES)):
            for module in modules:
                name = '%s/%s.py' % (folder, module)
                self.assertEqual((HERE / name).read_bytes() != live[name], name == 'japan_auction/job.py', name)

    def test_the_japan_page_is_rebuilt_unchanged(self):
        installed_page = HERE.parent / 'japan_lhd_001' / 'fixtures' / 'korea_live.html'
        import hashlib
        import japan_page
        self.assertEqual(hashlib.sha256(japan_page.build(installed_page.read_bytes())).hexdigest(),
                         'c10f48a25ee562db0ac25354709b738249ae7229871d3c41da98fbf7613af6ba')  # live japan.html

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
        self.assertIn("/jlfix1-", (HERE / 'deployment_transport.py').read_text(encoding='utf-8'))

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
