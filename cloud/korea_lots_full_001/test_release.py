"""The KOREA-LOTS-FULL candidate: the collector (zipped flat, rebuilt on the server) and the Korea page lot list."""
import io
from pathlib import Path
import sys
import unittest
import zipfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import edit_order  # noqa: E402
import deployment_transport  # noqa: E402


def installed():
    """The collector as TICKER-FIX6-INSTALL-20261112-R2 installed it (its package here) and the live Korea page."""
    collector = HERE.parent / 'korea_ticker_fix6_001' / 'korea_auction'
    value = {name: (collector / name.split('/')[1]).read_bytes() for name in candidate_builder.INSTALLED_SHA256}
    value[candidate_builder.PAGE] = (HERE / 'fixtures' / 'korea_live.html').read_bytes()
    for name in edit_order.SOURCE_FILES:
        value[name] = (HERE / 'fixtures' / 'order' / name.rsplit('/', 1)[1]).read_bytes()
    return value


class FakeAPI:
    def __init__(self):
        self.files = {}

    def upload(self, path, payload):
        self.files[path] = payload


class CandidateTests(unittest.TestCase):
    def bundle(self):
        api = FakeAPI()
        digest = deployment_transport.upload_package(api)
        return zipfile.ZipFile(io.BytesIO(api.files[deployment_transport.INBOX + '/koreafull-' + digest + '.zip']))

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
        self.assertEqual(set(files), {'korea_auction/__init__.py', candidate_builder.PAGE} | set(edit_order.SOURCE_FILES)
                         | {'korea_auction/%s.py' % m for m in candidate_builder.MODULES})
        for name in edit_order.SOURCE_FILES:
            self.assertIn(edit_order.CHECKS[name], files.pop(name).decode('utf-8'))
        page = files.pop(candidate_builder.PAGE).decode('utf-8')
        self.assertIn('id="kl-days"', page)
        self.assertIn('row("vin",l.vin)', page)
        self.assertIn('korea_auction/public.py', files)
        source = HERE / 'korea_auction'
        for module in candidate_builder.MODULES:
            self.assertEqual(files['korea_auction/%s.py' % module], (source / (module + '.py')).read_bytes())
        for name, value in files.items():
            compile(value, name, 'exec')
        self.assertFalse(any(candidate_builder.is_page(name) for name in files))

    def test_other_installed_collector_is_refused(self):
        source = installed()
        source['korea_auction/job.py'] += b'# edited'
        with self.assertRaises(ValueError):
            candidate_builder.build(source, {}, sha=deployment_transport.sha)

    def test_page_already_updated_is_refused(self):
        source = installed()
        archive = self.bundle()
        unpacked = Path(self._tmp())
        for name in archive.namelist():
            (unpacked / name).write_bytes(archive.read(name))
        once = candidate_builder.build(source, {}, here=unpacked, sha=deployment_transport.sha)
        source[candidate_builder.PAGE] = once[candidate_builder.PAGE]
        with self.assertRaisesRegex(ValueError, 'KOREA_LOTS_PAGE_UNEXPECTED'):
            candidate_builder.build(source, {}, here=unpacked, sha=deployment_transport.sha)

    def _tmp(self):
        import tempfile
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return directory.name


if __name__ == '__main__':
    unittest.main()
