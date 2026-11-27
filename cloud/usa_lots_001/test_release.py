"""The USA-LOTS candidate: the Korea collector and the new USA collector zipped flat and rebuilt on the server, the
launcher; only ticker.py and job.py of the installed Korea collector change; no page."""
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
    """The collector as JAPAN-LHD-FIX-INSTALL-R3 installed it (its package in this repository)."""
    live = HERE.parent / 'japan_lhd_fix_001' / 'korea_auction'
    return {name: (live / name.split('/')[1]).read_bytes() for name in candidate_builder.INSTALLED_SHA256}


class FakeAPI:
    def __init__(self):
        self.files = {}

    def upload(self, path, payload):
        self.files[path] = payload


class CandidateTests(unittest.TestCase):
    def bundle(self):
        api = FakeAPI()
        digest = deployment_transport.upload_package(api)
        return zipfile.ZipFile(io.BytesIO(api.files[deployment_transport.INBOX + '/ulots1-' + digest + '.zip']))

    def test_zip_carries_both_collectors_flat(self):
        names = self.bundle().namelist()
        for module in candidate_builder.MODULES:
            self.assertIn('kauc_%s.py' % module, names)
        for module in candidate_builder.USA_MODULES:
            self.assertIn('uauc_%s.py' % module, names)
        self.assertNotIn('uauc_test_usa_auction.py', names)
        self.assertTrue(all('/' not in name for name in names))

    def test_candidate(self):
        archive = self.bundle()
        unpacked = Path(self._tmp())
        for name in archive.namelist():
            (unpacked / name).write_bytes(archive.read(name))
        files = candidate_builder.build(installed(), {}, here=unpacked, sha=deployment_transport.sha)
        self.assertEqual(set(files), {'korea_auction/__init__.py', 'usa_auction/__init__.py', candidate_builder.LAUNCHER}
                         | {'korea_auction/%s.py' % m for m in candidate_builder.MODULES}
                         | {'usa_auction/%s.py' % m for m in candidate_builder.USA_MODULES})
        self.assertFalse(any(name.endswith('.html') or name.startswith('japan') for name in files))  # no page, no Japan
        for folder, modules in (('korea_auction', candidate_builder.MODULES), ('usa_auction', candidate_builder.USA_MODULES)):
            for module in modules:
                self.assertEqual(files['%s/%s.py' % (folder, module)], (HERE / folder / (module + '.py')).read_bytes())
        for name, value in files.items():
            compile(value, name, 'exec')
        self.assertEqual(files[candidate_builder.LAUNCHER],
                         b'"""Hourly PythonAnywhere task: the USA lots of IAAI\'s open pages (usa_auction.job)."""\n'
                         b'import sys\n\nfrom usa_auction import job\n\nsys.exit(job.main())\n')
        self.assertFalse(any(candidate_builder.is_page(name) for name in files))

    def test_installed_hashes_are_the_japan_lhd_fix_plan(self):
        """The live collector: the "after" of JAPAN-LHD-FIX-INSTALL-R3, unchanged by JAPAN-FRONT-PHOTO."""
        import json
        fix = json.loads((HERE.parent / 'japan_lhd_fix_001' / 'deployment_plan.json').read_bytes())['files']
        front = json.loads((HERE.parent / 'japan_front_photo_001' / 'deployment_plan.json').read_bytes())['files']
        for name, digest in candidate_builder.INSTALLED_SHA256.items():
            self.assertEqual((fix[name]['after'], front[name]['before'], front[name]['after']), (digest,) * 3, name)
        self.assertEqual(set(candidate_builder.INSTALLED_SHA256), {n for n in fix if n.startswith('korea_auction/')})

    def test_only_ticker_and_job_differ_from_the_installed_collector(self):
        """The package never rolls back another install: only korea_auction/ticker.py and job.py change."""
        live = installed()
        for module in candidate_builder.MODULES:
            name = 'korea_auction/%s.py' % module
            self.assertEqual((HERE / name).read_bytes() != live[name], module in ('ticker', 'job'), name)

    def test_other_installed_collector_is_refused(self):
        source = installed()
        source['korea_auction/job.py'] += b'# edited'
        with self.assertRaises(ValueError):
            candidate_builder.build(source, {}, sha=deployment_transport.sha)

    def test_module_names_and_server_prefix(self):
        for path in HERE.rglob('*.py'):
            self.assertRegex(path.name, r'^[a-z_]+\.py$')
        for name in ('deployment_transport.py', 'deployment_bootstrap.py', 'deployment_remote.py'):
            text = (HERE / name).read_text(encoding='utf-8')
            for old in ('jplhd1', 'jlfix1', 'jfront1', 'jauc_', 'japan lhd'):
                self.assertNotIn(old, text)
        self.assertIn("/ulots1-", (HERE / 'deployment_transport.py').read_text(encoding='utf-8'))
        self.assertIn("prefix='.ulots1-'", (HERE / 'deployment_remote.py').read_text(encoding='utf-8'))

    def test_pre_install_health_checks_only_existing_pages(self):
        """cloud/coordinator.md (27.11): health_checks only list pages that open before the install; none is new here."""
        source = (HERE / 'make_release.py').read_text(encoding='utf-8')
        checks = source[source.index("'health_checks':"):source.index("'production_required': True")]
        for page in ('index', 'korea', 'japan', 'usa', 'podbor'):
            self.assertIn('/video/%s.html' % page, checks)
        import deployment_controller
        self.assertEqual(set(deployment_controller.EXPECTED), {'/video/%s.html' % p for p in (
            'index', 'korea', 'japan', 'usa', 'katalog', 'podbor')})

    def test_rollback_outputs_are_only_the_usa_job_files(self):
        """video/usa/ also holds the USA page's calculator files: only the USA job's own outputs are removed."""
        import deployment_remote
        self.assertEqual(deployment_remote.OUTPUTS, ('video/usa/lots.json', 'video/usa/feed.json', 'video/usa/gallery',
                                                     'video/usa/lots', 'usa_auction_data', '.usa_auction_job.lock'))
        self.assertNotIn('video/usa', deployment_remote.OUTPUTS)
        self.assertNotIn('video/usa.html', deployment_remote.OUTPUTS)

    def _tmp(self):
        import tempfile
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return directory.name


if __name__ == '__main__':
    unittest.main()
