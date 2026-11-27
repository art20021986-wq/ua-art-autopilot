"""The USA-LOTS-FIX candidate: only usa_auction/pages.py, selection.py and job.py of the installed USA collector change,
zipped flat and rebuilt on the server; refused unless every installed file is as USA-LOTS-INSTALL-20261127 left it."""
import io
import json
from pathlib import Path
import sys
import unittest
import zipfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import deployment_transport  # noqa: E402

INSTALL = HERE.parent / 'usa_lots_001'
FIX1 = HERE.parent / 'usa_lots_fix_001'  # USA-LOTS-FIX-INSTALL-20261127 replaced job, pages, selection
FIXED = {'usa_auction/%s.py' % m for m in ('job', 'selection')}
FIX1_FILES = {'usa_auction/%s.py' % m for m in ('job', 'pages', 'selection')}
USA_LAUNCHER = (b'"""Hourly PythonAnywhere task: the USA lots of IAAI\'s open pages (usa_auction.job)."""\n'
                b'import sys\n\nfrom usa_auction import job\n\nsys.exit(job.main())\n')


def installed():
    """The files as USA-LOTS-INSTALL then USA-LOTS-FIX-INSTALL left them (their packages in this repository)."""
    source = {name: ((FIX1 if name in FIX1_FILES else INSTALL) / name).read_bytes()
              for name in candidate_builder.INSTALLED_SHA256 if name != 'usa_ticker_job.py'}
    source['usa_ticker_job.py'] = USA_LAUNCHER
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
        return zipfile.ZipFile(io.BytesIO(api.files[deployment_transport.INBOX + '/ulfix2-' + digest + '.zip']))

    def test_zip_carries_only_the_fixed_modules_flat(self):
        names = self.bundle().namelist()
        self.assertEqual(sorted(n for n in names if n.startswith('uauc_')), ['uauc_job.py', 'uauc_selection.py'])
        self.assertFalse(any(n.startswith('kauc_') for n in names))
        self.assertTrue(all('/' not in name for name in names))

    def test_candidate_is_the_three_fixed_files(self):
        archive = self.bundle()
        unpacked = Path(self._tmp())
        for name in archive.namelist():
            (unpacked / name).write_bytes(archive.read(name))
        files = candidate_builder.build(installed(), {}, here=unpacked, sha=deployment_transport.sha)
        self.assertEqual(set(files), FIXED)
        self.assertEqual(set(files) - set(candidate_builder.SOURCE_FILES), set())  # nothing new on the server
        for name, value in files.items():
            self.assertEqual(value, (HERE / name).read_bytes())
            compile(value, name, 'exec')
        self.assertFalse(any(candidate_builder.is_page(name) for name in files))

    def test_installed_hashes_are_the_usa_fix_install(self):
        """The USA fix install's receipt code_sha256 (state/receipts/USA-LOTS-FIX-INSTALL-20261127.json)."""
        receipt = HERE.parents[1] / 'state' / 'receipts' / 'USA-LOTS-FIX-INSTALL-20261127.json'
        if receipt.exists():
            fixed = json.loads(receipt.read_bytes())['code_sha256']
            self.assertEqual({n: candidate_builder.INSTALLED_SHA256[n] for n in fixed}, fixed)
        self.assertEqual({name: deployment_transport.sha(value) for name, value in installed().items()},
                         candidate_builder.INSTALLED_SHA256)

    def test_only_pages_selection_and_job_differ_from_the_install(self):
        live = installed()
        for name in sorted(n for n in live if n.startswith('usa_auction/')):
            self.assertEqual((HERE / name).read_bytes() != live[name], name in FIXED, name)

    def test_other_installed_file_is_refused(self):
        for name in ('usa_auction/fetch.py', 'usa_ticker_job.py', 'korea_auction/ticker.py', 'usa_auction/pages.py'):
            source = installed()
            source[name] += b'# edited'
            with self.assertRaisesRegex(ValueError, 'USA_INSTALLED_COLLECTOR_UNEXPECTED'):
                candidate_builder.build(source, {}, sha=deployment_transport.sha)

    def test_module_names_and_server_prefix(self):
        for path in HERE.rglob('*.py'):
            self.assertRegex(path.name, r'^[a-z_]+\.py$')
        for name in ('deployment_transport.py', 'deployment_bootstrap.py', 'deployment_remote.py'):
            text = (HERE / name).read_text(encoding='utf-8')
            for old in ('ulots1', 'jlfix1', 'jplhd1', 'kauc_', "'usa lots '"):
                self.assertNotIn(old, text)
        self.assertIn("/ulfix2-", (HERE / 'deployment_transport.py').read_text(encoding='utf-8'))
        self.assertIn("prefix='.ulfix2-'", (HERE / 'deployment_remote.py').read_text(encoding='utf-8'))

    def test_pre_install_health_checks_only_existing_pages(self):
        """cloud/coordinator.md (27.11): health_checks only list pages that open before the install; none is new here."""
        source = (HERE / 'make_release.py').read_text(encoding='utf-8')
        checks = source[source.index("'health_checks':"):source.index("'production_required': True")]
        self.assertEqual(sorted(checks.count('/video/%s.html' % p) for p in ('index', 'korea', 'japan', 'usa', 'podbor')),
                         [1] * 5)
        self.assertEqual(checks.count('https://'), 5)
        import deployment_controller
        self.assertEqual(set(deployment_controller.EXPECTED), {'/video/%s.html' % p for p in (
            'index', 'korea', 'japan', 'usa', 'katalog', 'podbor')})

    def test_no_task_is_created_or_removed_and_outputs_stay(self):
        """Only the USA hourly task's minute moves (run_soon); a rollback removes no USA output."""
        transport = (HERE / 'deployment_transport.py').read_text(encoding='utf-8')
        remote = (HERE / 'deployment_remote.py').read_text(encoding='utf-8')
        for text in (transport, remote):
            self.assertNotIn("'POST', 'schedule/'", text)
            self.assertNotIn("'DELETE', 'schedule/", text)
            self.assertNotIn('korea_ticker_job.py', text)
            self.assertNotIn('rmtree(generated', text)
        self.assertEqual(deployment_transport.USA_JOB_COMMAND, 'python3.10 /home/Carix/usa_ticker_job.py')

    def test_release_constants(self):
        import release_constants
        self.assertEqual((release_constants.PREVIEW_TASK, release_constants.INSTALL_TASK, release_constants.PACKAGE),
                         ('USA-LOTS-FIX2-PREVIEW-20261127', 'USA-LOTS-FIX2-INSTALL-20261127', 'cloud/usa_lots_fix_002'))

    def _tmp(self):
        import tempfile
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return directory.name


if __name__ == '__main__':
    unittest.main()
