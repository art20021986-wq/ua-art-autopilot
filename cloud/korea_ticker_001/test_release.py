"""The KOREA-TICKER candidate: the collector as new files, zipped flat and rebuilt on the server."""
import io
from pathlib import Path
import sys
import unittest
import zipfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / 'automation'))
import candidate_builder  # noqa: E402
import deployment_transport  # noqa: E402
from korea_auction.test_korea_auction import *  # noqa: E402,F401,F403  the collector's own tests run here too


class FakeAPI:
    def __init__(self):
        self.files = {}

    def upload(self, path, payload):
        self.files[path] = payload


class CandidateTests(unittest.TestCase):
    def bundle(self):
        api = FakeAPI()
        digest = deployment_transport.upload_package(api)
        return zipfile.ZipFile(io.BytesIO(api.files[deployment_transport.INBOX + '/koreaticker-' + digest + '.zip']))

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
        files = candidate_builder.build({}, {}, here=unpacked)
        self.assertEqual(set(files), {'korea_auction/__init__.py', 'korea_ticker_job.py'}
                         | {'korea_auction/%s.py' % m for m in candidate_builder.MODULES})
        source = HERE.parents[1] / 'automation' / 'korea_auction'
        for module in candidate_builder.MODULES:
            self.assertEqual(files['korea_auction/%s.py' % module], (source / (module + '.py')).read_bytes())
        for name, value in files.items():
            compile(value, name, 'exec')
        self.assertFalse(any(candidate_builder.is_page(name) for name in files))

    def _tmp(self):
        import tempfile
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return directory.name


if __name__ == '__main__':
    unittest.main()
