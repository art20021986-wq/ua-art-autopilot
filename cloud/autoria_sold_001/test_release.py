"""The AUTORIA-SOLD candidate: the job as new files, zipped flat and rebuilt on the server."""
import io
from pathlib import Path
import sys
import unittest
import zipfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import deployment_transport  # noqa: E402


class FakeAPI:
    def __init__(self):
        self.files = {}

    def upload(self, path, payload):
        self.files[path] = payload


class CandidateTests(unittest.TestCase):
    def bundle(self):
        api = FakeAPI()
        digest = deployment_transport.upload_package(api)
        return zipfile.ZipFile(io.BytesIO(api.files[deployment_transport.INBOX + '/autoriasold-' + digest + '.zip']))

    def test_zip_carries_the_job_flat(self):
        names = self.bundle().namelist()
        for module in candidate_builder.MODULES:
            self.assertIn('asold_%s.py' % module, names)
        self.assertTrue(all('/' not in name for name in names))

    def test_candidate_is_new_files_only(self):
        archive = self.bundle()
        unpacked = Path(self._tmp())
        for name in archive.namelist():
            (unpacked / name).write_bytes(archive.read(name))
        files = candidate_builder.build({}, {}, here=unpacked)
        self.assertEqual(set(files), {'autoria_sold/__init__.py', 'autoria_sold_job.py'}
                         | {'autoria_sold/%s.py' % m for m in candidate_builder.MODULES})
        source = HERE / 'autoria_sold'
        for module in candidate_builder.MODULES:
            self.assertEqual(files['autoria_sold/%s.py' % module], (source / (module + '.py')).read_bytes())
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
