"""The KOREA-TIME candidate: the collector zipped flat and rebuilt on the server, and the korea.html lot card."""
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
    """The collector as TICKER-FIX6-INSTALL-20261112-R2 installed it (its package in this repository), live korea.html."""
    ticker = HERE.parent / 'korea_ticker_fix6_001' / 'korea_auction'
    files = {name: (ticker / name.split('/')[1]).read_bytes() for name in candidate_builder.INSTALLED_SHA256}
    files[candidate_builder.PAGE] = (HERE / 'fixtures' / 'korea_lots_live.txt').read_bytes()
    return files


class FakeAPI:
    def __init__(self):
        self.files = {}

    def upload(self, path, payload):
        self.files[path] = payload


class CandidateTests(unittest.TestCase):
    def bundle(self):
        api = FakeAPI()
        digest = deployment_transport.upload_package(api)
        return zipfile.ZipFile(io.BytesIO(api.files[deployment_transport.INBOX + '/kttime1-' + digest + '.zip']))

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
        self.assertEqual(set(files), {'korea_auction/__init__.py', candidate_builder.PAGE}
                         | {'korea_auction/%s.py' % m for m in candidate_builder.MODULES})
        self.assertIn('korea_auction/public.py', files)
        source = HERE / 'korea_auction'
        for module in candidate_builder.MODULES:
            self.assertEqual(files['korea_auction/%s.py' % module], (source / (module + '.py')).read_bytes())
        for name, value in files.items():
            if name.endswith('.py'):
                compile(value, name, 'exec')
        self.assertFalse(any(candidate_builder.is_page(name) for name in files))

    def test_other_installed_collector_is_refused(self):
        source = installed()
        source['korea_auction/job.py'] += b'# edited'
        with self.assertRaises(ValueError):
            candidate_builder.build(source, {}, sha=deployment_transport.sha)

    def test_page_lot_card_gets_korea_and_kyiv_time_only(self):
        before = installed()[candidate_builder.PAGE].decode('utf-8')
        after = candidate_builder.patch_page(before)
        self.assertNotIn('(час Кореї)', after)
        self.assertIn('["Корея","Київ"],["Корея","Киев"],["კორეა","კიევი"]', after)
        self.assertIn('slice(11,16)+zones(s,i);', after)
        self.assertIn('slice(11,16)+zones(l.auction_start,i);', after)
        self.assertEqual(after.count('function kyiv('), 1)
        # nothing else changes: taking the replacements back gives the page as it was
        back = after
        for old, new in candidate_builder.PIECES:
            back = back.replace(new, old)
        self.assertEqual(back, before)

    def test_page_patched_twice_or_changed_is_refused(self):
        page = installed()[candidate_builder.PAGE].decode('utf-8')
        with self.assertRaises(ValueError):
            candidate_builder.patch_page(candidate_builder.patch_page(page))
        with self.assertRaises(ValueError):
            candidate_builder.patch_page(page.replace(candidate_builder.STAMP_FROM, ''))

    def _tmp(self):
        import tempfile
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return directory.name


if __name__ == '__main__':
    unittest.main()
