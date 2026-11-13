"""The KOREA-TILE candidate: the collector zipped flat and rebuilt on the server."""
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
    """The collector as KOREA-TIME-INSTALL installs it (its package in this repository) and the live Korea page."""
    ticker = HERE.parent / 'korea_time_001' / 'korea_auction'
    source = {name: (ticker / name.split('/')[1]).read_bytes() for name in candidate_builder.INSTALLED_SHA256}
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
        return zipfile.ZipFile(io.BytesIO(api.files[deployment_transport.INBOX + '/kttile1-' + digest + '.zip']))

    def test_zip_carries_the_collector_flat(self):
        names = self.bundle().namelist()
        for module in candidate_builder.MODULES:
            self.assertIn('kauc_%s.py' % module, names)
        self.assertTrue(all('/' not in name for name in names))

    def test_candidate_is_new_files_only(self):
        archive = self.bundle()
        unpacked = Path(self._tmp())
        for name in archive.namelist():
            (unpacked / name).write_bytes(archive.read(name))
        files = candidate_builder.build(installed(), {}, here=unpacked, sha=deployment_transport.sha)
        self.assertEqual(set(files), {'korea_auction/__init__.py', candidate_builder.KOREA}
                         | {'korea_auction/%s.py' % m for m in candidate_builder.MODULES})
        page = files[candidate_builder.KOREA].decode('utf-8')
        self.assertIn('function engine(l){', page)  # KOREA-ENGINE-001: engine type in the lot card
        self.assertIn('createElement("optgroup")', page)  # KOREA-ENGINE-001: models grouped by make
        self.assertIn('korea_auction/public.py', files)
        source = HERE / 'korea_auction'
        for module in candidate_builder.MODULES:
            self.assertEqual(files['korea_auction/%s.py' % module], (source / (module + '.py')).read_bytes())
        for name, value in files.items():
            if name.endswith('.py'):  # the page is checked above
                compile(value, name, 'exec')
        self.assertFalse(any(candidate_builder.is_page(name) for name in files))

    def test_only_the_tile_modules_differ_from_the_installed_collector(self):
        """The package never rolls back another install: every module but the tile's and KOREA-ENGINE's own equals the
        installed one (fuel.py is new)."""
        changed = {'collect', 'selection', 'ticker', 'prices', 'public'}
        live = installed()
        for module in candidate_builder.MODULES:
            name = 'korea_auction/%s.py' % module
            if module == 'fuel':
                self.assertNotIn(name, live)
                continue
            mine = (HERE / name).read_bytes()
            self.assertEqual(mine != live[name], module in changed, name)

    def test_other_installed_collector_is_refused(self):
        source = installed()
        source['korea_auction/job.py'] += b'# edited'
        with self.assertRaises(ValueError):
            candidate_builder.build(source, {}, sha=deployment_transport.sha)

    def _tmp(self):
        import tempfile
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return directory.name


if __name__ == '__main__':
    unittest.main()
