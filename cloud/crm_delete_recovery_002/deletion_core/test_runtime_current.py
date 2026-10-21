"""Optional source-bound fixture: no production imports, connections or data.

Run with UA_DELETE_CURRENT_SOURCES pointing at private read-only source
capture and UA_DELETE_PUBLIC_FIXTURES at the reviewed public HTML fixtures.
Only SQLite DDL and reviewed db connection definitions are executed in a
temporary folder. Production source bytes are never checked into this package.
"""
import ast
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import threading
import time
import types
import unittest

from coordinator import Coordinator, sha
from deletion_state import application_schema_sha256
from runtime import LegacyBinding, install_reviewed_schema, OBSERVED_APPLICATION_SCHEMA_SHA256


@unittest.skipUnless(os.getenv('UA_DELETE_CURRENT_SOURCES') and os.getenv('UA_DELETE_PUBLIC_FIXTURES'),
                     'requires private current-source capture and public fixtures')
class CurrentSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sources = Path(os.environ['UA_DELETE_CURRENT_SOURCES'])
        self.fixtures = Path(os.environ['UA_DELETE_PUBLIC_FIXTURES'])
        self.private = self.root / 'ua_crm_deletion_state'
        self.private.mkdir(mode=0o700)
        catalog_text = (self.fixtures / 'video/katalog.html').read_text(encoding='utf-8')
        codes = sorted(set(re.findall(r'data-ua-card=["\'](UA-[0-9]{4})["\']', catalog_text)))
        self.assertTrue(codes)
        self.code = 'UA-0002' if 'UA-0002' in codes else codes[0]
        for name in ('db.py', 'publication_fence.py', 'ua_site_counters.py'):
            shutil.copyfile(self.sources / name, self.root / name)
        for folder in ('site', 'video'):
            (self.root / folder).mkdir()
            for name in ('index.html', 'katalog.html'):
                shutil.copyfile(self.fixtures / folder / name, self.root / folder / name)
            if (self.fixtures / folder / 'sitemap.xml').exists():
                shutil.copyfile(self.fixtures / folder / 'sitemap.xml', self.root / folder / 'sitemap.xml')
            (self.root / folder / (self.code + '.html')).write_bytes(b'<html>SYNTHETIC_TARGET_VIN</html>')
        schema = json.loads((self.sources / 'schema.json').read_bytes())
        with closing(sqlite3.connect(self.root / 'crm.db')) as conn:
            for kind in ('table', 'index', 'trigger', 'view'):
                for row in schema:
                    if row[0] == kind and row[3] and not row[1].startswith('sqlite_'):
                        conn.execute(row[3])
            conn.execute("INSERT INTO staff(user_id,role,active,added_at) VALUES(101,'owner',1,'2026-09-21')")
            conn.execute("INSERT INTO cars(id,auto_number,vin,published,review_status,created_at,price_uah,price_georgia) "
                         "VALUES(8,?,'SYNTHETIC_TARGET_VIN',1,'approved','2026-09-21',8600,7000)", (self.code,))
            conn.execute("INSERT INTO cars(id,auto_number,vin,published,review_status,created_at,price_uah,price_georgia) "
                         "VALUES(9,'UA-0003','NEIGHBORVIN',1,'approved','2026-09-21',9900,8000)")
            conn.commit()
            self.assertEqual(OBSERVED_APPLICATION_SCHEMA_SHA256, application_schema_sha256(conn))
        selected = {'_ua_sql_pishet', '_ua_fayl_zahvatit', '_ua_fayl_otpustit', '_UaKursor', 'Soedinenie', 'connect', 'get_staff'}
        tree = ast.parse((self.sources / 'db.py').read_bytes())
        nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in selected]
        self.assertEqual(selected, {node.name for node in nodes})
        self.db = types.ModuleType('reviewed_db_fixture')
        self.db.__file__ = str(self.root / 'db.py')
        self.db.__dict__.update(sqlite3=sqlite3, os=os, BASE_DIR=str(self.root), DB_FILE=str(self.root / 'crm.db'),
                                ZAMOK=threading.RLock(), ZAMOK_OZHIDANIE=1, _UA_FAYL_SOSTOYANIE=threading.local())
        exec(compile(ast.Module(body=nodes, type_ignores=[]), self.db.__file__, 'exec'), self.db.__dict__)
        self.depth = 0
        from contextlib import contextmanager
        @contextmanager
        def fence(timeout=90):
            self.depth += 1
            try:
                yield
            finally:
                self.depth -= 1
        def require_fence():
            if not self.depth:
                raise RuntimeError('FENCE_REQUIRED')
        self.fence_module = types.SimpleNamespace(__file__=str(self.root / 'publication_fence.py'),
                                                  publication_fence=fence, require_publication_fence=require_fence)
        spec = importlib.util.spec_from_file_location('reviewed_counters_fixture', self.root / 'ua_site_counters.py')
        counters = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(counters)
        shared = {'site/index.html': 'LEGACY_HOME', 'site/katalog.html': 'CATALOG',
                  'video/index.html': 'MODERN_HOME', 'video/katalog.html': 'CATALOG'}
        for folder in ('site', 'video'):
            if (self.root / folder / 'sitemap.xml').exists():
                shared[folder + '/sitemap.xml'] = 'SITEMAP'
        config = {'version': 1, 'application_schema_sha256': OBSERVED_APPLICATION_SCHEMA_SHA256,
                  'source_sha256': {name: sha((self.root / name).read_bytes()) for name in ('db.py', 'publication_fence.py', 'ua_site_counters.py')},
                  'shared': shared,
                  'shared_routes': {name: ['https://www.uaart.com.ua/' + name] if name.startswith('video/') else [] for name in shared},
                  'direct_route_prefixes': {'video': ['https://www.uaart.com.ua/video/'], 'site': []},
                  'writers_receipt_sha256': 'a' * 64}
        self.binding = LegacyBinding(db=self.db, counters=counters, fence_module=self.fence_module,
                                     config=config, root=self.root, journal=self.private)
        install_reviewed_schema(binding=self.binding, backup_manifest_sha256='b' * 64)

    def observe(self, plan):
        self.assertEqual(0, self.depth)
        observations = {}
        for url, name in plan['routes'].items():
            path = self.root / name
            observations[url] = {'url': url, 'status': 200 if path.exists() else 404,
                                 'body_sha256': sha(path.read_bytes()) if path.exists() else None,
                                 'redirected': False, 'observed_at': time.time()}
        return observations

    def test_current_schema_and_real_db_wrapper_complete(self):
        self.binding.observe_http = self.observe
        original_records, original_counts = self.binding.counters.catalog_snapshot((self.root / 'video/katalog.html').read_text())
        worker = Coordinator(self.binding, schema_sha256=OBSERVED_APPLICATION_SCHEMA_SHA256)
        token = worker.confirm(car_id=8, actor_id=101)
        intent = worker.admit(token=token, actor_id=101)
        self.assertEqual('COMPLETE', worker.resume(operation_id=intent['operation_id'])['status'])
        with closing(self.db.connect()) as conn:
            self.assertEqual(0, conn.execute('SELECT count(*) FROM cars WHERE id=8').fetchone()[0])
            self.assertEqual((9900, 8000), tuple(conn.execute('SELECT price_uah,price_georgia FROM cars WHERE id=9').fetchone()))
            self.assertEqual('ok', conn.execute('PRAGMA integrity_check').fetchone()[0])
        self.assertFalse(self.db.ZAMOK._is_owned())
        self.assertEqual(0, getattr(self.db._UA_FAYL_SOSTOYANIE, 'depth', 0))
        records, counts = self.binding.counters.catalog_snapshot((self.root / 'video/katalog.html').read_text())
        self.assertEqual({key: value for key, value in original_records.items() if key != self.code}, records)
        expected_counts = dict(original_counts, all=original_counts['all'] - 1)
        if original_records[self.code]:
            expected_counts[original_records[self.code]] -= 1
        self.assertEqual(expected_counts, counts)

    def test_current_counter_helpers_preserve_all_script_blocks(self):
        import re
        before = {name: (self.root / name).read_bytes() for name, kind in self.binding.shared.items() if kind != 'SITEMAP'}
        with self.binding.fence():
            after = self.binding.transform_lists(self.code, before)
        for name in before:
            self.assertEqual(re.findall(rb'<script\b[^>]*>.*?</script\s*>', before[name], re.S | re.I),
                             re.findall(rb'<script\b[^>]*>.*?</script\s*>', after[name], re.S | re.I))
        # The installed function itself still has its original JS injection;
        # the binding modified only an isolated function's global namespace.
        self.assertIsNot(self.binding.patch_home.__globals__, self.binding.counters.__dict__)


if __name__ == '__main__':
    unittest.main()
