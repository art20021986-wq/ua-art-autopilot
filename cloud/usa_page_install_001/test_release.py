"""The USA-PAGE candidate: video/usa.html rebuilt from the live usa.html and japan.html, usa_auction/pages.py, views.py
and korea_auction/ticker.py replaced, zipped flat and rebuilt on the server; refused unless every installed collector
file is as the USA-LOTS installs left it (USA-LOTS-INSTALL-20261127, then FIX, FIX2, FIX3, FIX4)."""
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
import zipfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import deployment_transport  # noqa: E402
import usa_page  # noqa: E402

CLOUD = HERE.parent
ROOT = HERE.parents[1]
INSTALL = CLOUD / 'usa_lots_001'  # USA-LOTS-INSTALL-20261127: korea_auction/*, usa_auction/* (fetch, views, __init__)
FIX1 = CLOUD / 'usa_lots_fix_001'  # USA-LOTS-FIX-INSTALL-20261127: pages.py (its job.py, selection.py replaced later)
FIX2 = CLOUD / 'usa_lots_fix_002'  # USA-LOTS-FIX2-INSTALL-20261127: selection.py
FIX4 = CLOUD / 'usa_lots_fix_004'  # USA-LOTS-FIX4-INSTALL-20261127: job.py
SOURCE = {'usa_auction/pages.py': FIX1, 'usa_auction/selection.py': FIX2, 'usa_auction/job.py': FIX4}
FIX5 = CLOUD / 'usa_lots_fix_005'  # the new pages.py, views.py, ticker.py (USA-LOTS-FIX-005, merged in #2467/#2468)
PAGE = CLOUD / 'usa_page_001'  # usa_page.py and the live page fixtures (USA-PAGE-001, #2466/#2468)
FIXED = {'usa_auction/pages.py', 'usa_auction/views.py', 'korea_auction/ticker.py'}
CHAIN = ('USA-LOTS-INSTALL-20261127', 'USA-LOTS-FIX-INSTALL-20261127', 'USA-LOTS-FIX2-INSTALL-20261127',
         'USA-LOTS-FIX3-INSTALL-20261127', 'USA-LOTS-FIX4-INSTALL-20261127')
USA_LAUNCHER = (b'"""Hourly PythonAnywhere task: the USA lots of IAAI\'s open pages (usa_auction.job)."""\n'
                b'import sys\n\nfrom usa_auction import job\n\nsys.exit(job.main())\n')
USA_HTML = (PAGE / 'fixtures' / 'usa_live.html').read_bytes()
JAPAN_HTML = (PAGE / 'fixtures' / 'japan_live.html').read_bytes()


def installed():
    """The installed files as the USA-LOTS chain left them (their packages in this repository)."""
    source = {name: (SOURCE.get(name, INSTALL) / name).read_bytes()
              for name in candidate_builder.INSTALLED_SHA256 if name != 'usa_ticker_job.py'}
    source['usa_ticker_job.py'] = USA_LAUNCHER
    return source


def live():
    return dict(installed(), **{candidate_builder.USA_PAGE: USA_HTML, candidate_builder.JAPAN_PAGE: JAPAN_HTML})


class FakeAPI:
    def __init__(self):
        self.files = {}

    def upload(self, path, payload):
        self.files[path] = payload


class CandidateTests(unittest.TestCase):
    def bundle(self):
        api = FakeAPI()
        digest = deployment_transport.upload_package(api)
        return zipfile.ZipFile(io.BytesIO(api.files[deployment_transport.INBOX + '/uspage1-' + digest + '.zip']))

    def test_zip_carries_only_the_new_modules_flat(self):
        names = self.bundle().namelist()
        self.assertEqual(sorted(n for n in names if n.startswith(('uauc_', 'kauc_'))),
                         ['kauc_ticker.py', 'uauc_pages.py', 'uauc_views.py'])
        self.assertIn('usa_page.py', names)
        self.assertTrue(all('/' not in name for name in names))

    def test_candidate_is_the_page_and_the_three_files(self):
        archive = self.bundle()
        unpacked = Path(self._tmp())
        for name in archive.namelist():
            (unpacked / name).write_bytes(archive.read(name))
        files = candidate_builder.build(live(), {}, here=unpacked, sha=deployment_transport.sha)
        self.assertEqual(set(files), FIXED | {'video/usa.html'})
        self.assertNotIn('video/japan.html', files)  # only read
        self.assertEqual(set(files) - set(candidate_builder.SOURCE_FILES), set())  # nothing new on the server
        for name in FIXED:
            self.assertEqual(files[name], (HERE / name).read_bytes())
            compile(files[name], name, 'exec')
        self.assertEqual(files['video/usa.html'], usa_page.build(USA_HTML, JAPAN_HTML))
        self.assertEqual(usa_page.build(files['video/usa.html'], JAPAN_HTML), files['video/usa.html'])  # idempotent
        page = files['video/usa.html'].decode('utf-8')
        self.assertEqual((page.count(usa_page.START), page.count('id="usa-calc"')), (1, 1))
        self.assertFalse(any(candidate_builder.is_page(name) for name in files))

    def test_shipped_files_are_the_merged_ones(self):
        """The package's copies are byte for byte the reviewed USA-LOTS-FIX-005 and USA-PAGE-001 files."""
        for name in FIXED:
            self.assertEqual((HERE / name).read_bytes(), (FIX5 / name).read_bytes(), name)
        self.assertEqual((HERE / 'usa_page.py').read_bytes(), (PAGE / 'usa_page.py').read_bytes())

    def test_installed_hashes_are_the_receipts_chain(self):
        """INSTALLED_SHA256 = USA-LOTS-INSTALL's code_sha256 with each later fix's code_sha256 over the files it replaced,
        and the repository's packages give exactly those bytes."""
        expected = {}
        for task in CHAIN:
            receipt = json.loads((ROOT / 'state' / 'receipts' / (task + '.json')).read_bytes())
            self.assertEqual(receipt['status'], 'FINISHED', task)
            expected.update(receipt['code_sha256'])
        self.assertEqual(expected, candidate_builder.INSTALLED_SHA256)
        self.assertEqual({name: deployment_transport.sha(value) for name, value in installed().items()},
                         candidate_builder.INSTALLED_SHA256)

    def test_no_later_install_touched_the_korea_ticker(self):
        """No install after USA-LOTS-INSTALL-20261127 replaced a korea_auction or usa_auction file (git history of the
        receipts): the base of the new ticker.py is the installed one."""
        try:
            log = subprocess.run(['git', 'log', '--since=2026-11-27T11:00:00Z', '--name-only', '--format=',
                                  '--', 'state/receipts'], cwd=ROOT, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            self.skipTest('no git')
        if log.returncode != 0 or not log.stdout.strip():
            self.skipTest('no git history')
        receipts = {Path(n).stem for n in log.stdout.split() if n.endswith('.json')}
        for task in sorted(r for r in receipts if 'INSTALL' in r and not r.endswith(('-BACKUP', '-ROLLBACK'))):
            path = ROOT / 'state' / 'receipts' / (task + '.json')
            if task in CHAIN or not path.exists():
                continue
            code = json.loads(path.read_bytes()).get('code_sha256') or {}
            self.assertFalse([n for n in code if n.startswith(('korea_auction/', 'usa_auction/'))], task)

    def test_only_the_three_modules_differ_from_the_install(self):
        current = installed()
        self.assertEqual({n for n in FIXED if (HERE / n).read_bytes() != current[n]}, FIXED)
        self.assertEqual(sorted(p.relative_to(HERE).as_posix() for p in HERE.rglob('*.py')
                                if p.parent != HERE), sorted(FIXED))

    def test_other_installed_file_is_refused(self):
        for name in ('usa_auction/fetch.py', 'usa_auction/job.py', 'usa_ticker_job.py', 'korea_auction/ticker.py',
                     'korea_auction/job.py', 'usa_auction/views.py'):
            source = live()
            source[name] += b'# edited'
            with self.assertRaisesRegex(ValueError, 'USA_INSTALLED_COLLECTOR_UNEXPECTED'):
                candidate_builder.build(source, {}, sha=deployment_transport.sha)

    def test_page_without_its_anchors_is_refused(self):
        source = live()
        source['video/usa.html'] = source['video/usa.html'].replace(b'id="usa-result"', b'id="x"')
        with self.assertRaisesRegex(ValueError, 'USA_PAGE'):
            candidate_builder.build(source, {}, here=self._bundle_dir())

    def test_module_names_and_server_prefix(self):
        for path in HERE.rglob('*.py'):
            self.assertRegex(path.name, r'^[a-z_]+\.py$')
        for name in ('deployment_transport.py', 'deployment_bootstrap.py', 'deployment_remote.py'):
            text = (HERE / name).read_text(encoding='utf-8')
            for old in ('ulots1', 'ulfix4', 'jlfix1', 'jplhd1', "'usa lots "):
                self.assertNotIn(old, text)
        self.assertIn("/uspage1-", (HERE / 'deployment_transport.py').read_text(encoding='utf-8'))
        self.assertIn("'uspage1-'", (HERE / 'deployment_bootstrap.py').read_text(encoding='utf-8'))
        self.assertIn("prefix='.uspage1-'", (HERE / 'deployment_remote.py').read_text(encoding='utf-8'))

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
        self.assertEqual(deployment_controller.EXPECTED['/video/usa.html'], ('<!--UA-USA-LOTS-V1-->', 'id="usa-calc"'))

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

    def test_japan_page_is_read_and_protected(self):
        import deployment_remote
        self.assertIn('video/japan.html', candidate_builder.SOURCE_FILES)
        self.assertIn('video/japan.html', deployment_remote.UNTOUCHED)
        self.assertIn('video/korea.html', deployment_remote.UNTOUCHED)
        self.assertNotIn('video/usa.html', deployment_remote.UNTOUCHED)

    def test_release_constants(self):
        import release_constants
        self.assertEqual((release_constants.PREVIEW_TASK, release_constants.INSTALL_TASK, release_constants.PACKAGE),
                         ('USA-PAGE-PREVIEW-20261128-R3', 'USA-PAGE-INSTALL-20261128-R2', 'cloud/usa_page_install_001'))

    def _bundle_dir(self):
        archive = self.bundle()
        unpacked = Path(self._tmp())
        for name in archive.namelist():
            (unpacked / name).write_bytes(archive.read(name))
        return unpacked

    def _tmp(self):
        import tempfile
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return directory.name


if __name__ == '__main__':
    unittest.main()
