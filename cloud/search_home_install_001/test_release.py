"""The SEARCH-HOME-001 install A candidate: the collector zipped flat and rebuilt on the server, the Korea page and
prices file edits, the new USA files."""
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
    """The collector as KOREA-TOP-TILE-INSTALL installed it (its package in this repository), the live Korea page and
    the live Korea prices file."""
    live = HERE.parent / 'korea_top_tile_001' / 'korea_auction'
    source = {name: (live / name.split('/')[1]).read_bytes() for name in candidate_builder.INSTALLED_SHA256}
    source[candidate_builder.KOREA] = (HERE / 'fixtures' / 'korea_live.html').read_bytes()
    source[candidate_builder.LOGISTICS] = (HERE / 'fixtures' / 'logistics_live.json').read_bytes()
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
        return zipfile.ZipFile(io.BytesIO(api.files[deployment_transport.INBOX + '/shome1-' + digest + '.zip']))

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
        self.assertEqual(set(files), {'korea_auction/__init__.py', candidate_builder.KOREA, candidate_builder.LOGISTICS,
                                      'video/usa.html'} | set(candidate_builder.NEW_FILES)
                         | {'korea_auction/%s.py' % m for m in candidate_builder.MODULES})
        korea = files[candidate_builder.KOREA].decode('utf-8')
        self.assertIn("з понеділка по п'ятницю", korea)
        self.assertIn('Авто з усіх країн під ключ', korea)
        self.assertNotIn('Авто з Кореї під ключ', korea)
        import offer_text
        self.assertEqual(korea.replace(offer_text._line(offer_text.NEW), offer_text._line(offer_text.OLD)).encode(),
                         installed()[candidate_builder.KOREA])  # every other byte stays
        self.assertIn(b'"port": 400', files[candidate_builder.LOGISTICS])
        self.assertIn('id="usa-calc"', files['video/usa.html'].decode('utf-8'))
        source = HERE / 'korea_auction'
        for module in candidate_builder.MODULES:
            self.assertEqual(files['korea_auction/%s.py' % module], (source / (module + '.py')).read_bytes())
        for name, value in files.items():
            if name.endswith('.py'):
                compile(value, name, 'exec')
        self.assertFalse(any(candidate_builder.is_page(name) for name in files))

    def test_only_this_release_modules_differ_from_the_installed_collector(self):
        """The package never rolls back another install: only ticker changes; country_tabs is new."""
        live = installed()
        for module in candidate_builder.MODULES:
            name = 'korea_auction/%s.py' % module
            if module == 'country_tabs':
                self.assertNotIn(name, live)
                continue
            self.assertEqual((HERE / name).read_bytes() != live[name], module == 'ticker',
                             name)

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
