"""Real isolated SQLite/filesystem/HTTP integration; no production imports."""
from contextlib import contextmanager, closing
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

from coordinator import Coordinator, CoordinatorError, sha
from deletion_state import (DeletionError, ImmediateTransaction,
                            application_schema_sha256, install_additive_schema)
from public_write_guard import advertised_codes
from retirement import retire_html, retire_sitemap, RetirementError


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class Binding:
    def __init__(self, root, port):
        self.public_root = root
        self.journal_root = root / 'private'
        self.journal_root.mkdir(mode=0o700)
        self.db_path = root / 'crm.db'
        self.depth = 0
        self.lock = threading.RLock()
        self.base = 'http://127.0.0.1:%d/' % port
        self.http_mode = None
        self.http_calls = 0

    @contextmanager
    def fence(self):
        with self.lock:
            self.depth += 1
            try:
                yield
            finally:
                self.depth -= 1

    def require_fence(self):
        if not self.depth:
            raise RuntimeError('FENCE_REQUIRED')

    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute('PRAGMA foreign_keys=ON')
        return conn

    def authorize(self, actor):
        return actor == 101

    def resolve_plan(self, row):
        direct = ['video/UA-0002-diag.html', 'video/UA-0002.html'] if row['published'] else []
        lists = ['video/index.html', 'video/katalog.html']
        sitemaps = ['video/sitemap.xml']
        return {'car_code': row['auto_number'], 'mode': 'PUBLIC_OR_RESIDUAL' if direct else 'NEVER_PUBLISHED',
                'direct': direct, 'lists': lists, 'sitemaps': sitemaps,
                'local_only': [],
                'media': ['video/car-photo.webp'],
                'routes': {self.base + name: name for name in direct + lists + sitemaps}}

    def transform_lists(self, code, before):
        self.require_fence()
        result = {}
        for name, data in before.items():
            data = retire_html(data, code)
            count = len(advertised_codes(data.decode()))
            result[name] = re.sub(rb'<b id="count">[0-9]+</b>', b'<b id="count">' + str(count).encode() + b'</b>', data)
        return result

    def verify_local(self, plan, current):
        self.require_fence()
        for name in plan['lists']:
            text = current[name].decode()
            if plan['car_code'] in advertised_codes(text):
                return False
            match = re.search(r'<b id="count">([0-9]+)</b>', text)
            if not match or int(match[1]) != len(advertised_codes(text)):
                return False
        return True

    def observe_http(self, plan):
        assert self.depth == 0, 'network called with publication fence held'
        self.http_calls += 1
        result = {}
        opener = urllib.request.build_opener(NoRedirect())
        for url, name in plan['routes'].items():
            try:
                response = opener.open(url, timeout=2)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                status, data = response.code, response.read()
            result[url] = {'url': url, 'status': status, 'body_sha256': sha(data),
                           'observed_at': time.time(), 'redirected': False}
            if self.http_mode == 'redirect' and name in plan['direct']:
                result[url].update(status=302, redirected=True)
            if self.http_mode == 'stale':
                result[url]['observed_at'] -= 120
        return result


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'video').mkdir()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(self.root)))
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
        self.thread.start()
        self.binding = Binding(self.root, self.server.server_port)
        with closing(self.binding.connect()) as conn:
            conn.execute('CREATE TABLE cars (id INTEGER PRIMARY KEY, auto_number TEXT, vin TEXT, published INTEGER, price INTEGER, photos TEXT)')
            conn.execute("INSERT INTO cars VALUES(8,'UA-0002','SYNTHETICVIN000001',1,8600,'original-media')")
            conn.execute("INSERT INTO cars VALUES(9,'UA-0003','NEIGHBORVIN',1,9900,'neighbor-media')")
            conn.commit()
            self.schema = application_schema_sha256(conn)
            with self.binding.fence(), ImmediateTransaction(conn, self.binding.require_fence) as tx:
                install_additive_schema(tx, approved_application_schema_sha256=self.schema)
                tx.commit()
        self.neighbor = b'<article><a href="UA-0003.html">Neighbor 9900</a></article>'
        target = b'<article data-car-code="UA-0002"><a href="UA-0002.html">Sold 8600</a></article>'
        self.original_html = b'<html><b id="count">2</b>' + target + self.neighbor + b'<script>const keep = 1;</script></html>'
        for name in ('index.html', 'katalog.html'):
            (self.root / 'video' / name).write_bytes(self.original_html)
        for name in ('UA-0002.html', 'UA-0002-diag.html'):
            (self.root / 'video' / name).write_bytes(b'<html>SYNTHETICVIN000001</html>')
        (self.root / 'video/car-photo.webp').write_bytes(b'original-media-bytes')
        self.neighbor_sitemap = '<url><loc>https://example.test/UA-0003.html</loc><lastmod>yesterday</lastmod></url>'
        (self.root / 'video/sitemap.xml').write_text('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.test/UA-0002.html</loc></url>' + self.neighbor_sitemap + '</urlset>')
        self.worker = Coordinator(self.binding, schema_sha256=self.schema)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)
        self.temp.cleanup()

    def scalar(self, sql, params=()):
        with closing(self.binding.connect()) as conn:
            return conn.execute(sql, params).fetchone()[0]

    def admitted(self):
        token = self.worker.confirm(car_id=8, actor_id=101)
        return token, self.worker.admit(token=token, actor_id=101)

    def test_complete_real_http_and_duplicate_callback(self):
        token, intent = self.admitted()
        result = self.worker.resume(operation_id=intent['operation_id'])
        self.assertEqual('COMPLETE', result['status'])
        self.assertEqual(0, result['media_writes'])
        self.assertEqual(0, self.scalar('SELECT count(*) FROM cars WHERE id=8'))
        self.assertEqual(9900, self.scalar('SELECT price FROM cars WHERE id=9'))
        self.assertEqual(b'original-media-bytes', (self.root / 'video/car-photo.webp').read_bytes())
        self.assertEqual([], self.worker.pending())
        for name in ('index.html', 'katalog.html'):
            data = (self.root / 'video' / name).read_bytes()
            self.assertIn(self.neighbor, data)
            self.assertIn(b'<b id="count">1</b>', data)
            self.assertNotIn(b'UA-0002', data)
        self.assertIn(self.neighbor_sitemap, (self.root / 'video/sitemap.xml').read_text())
        self.assertEqual(intent['operation_id'], self.worker.admit(token=token, actor_id=101)['operation_id'])
        self.assertEqual(result, self.worker.resume(operation_id=intent['operation_id']))

    def test_interrupt_after_effect_resumes_without_replaying_other_changes(self):
        _, intent = self.admitted()
        def fault(event, name):
            if event == 'public_effect':
                raise KeyboardInterrupt()
        self.worker.fault = fault
        with self.assertRaises(KeyboardInterrupt):
            self.worker.resume(operation_id=intent['operation_id'])
        self.assertEqual([intent['operation_id']], self.worker.pending())
        restarted = Coordinator(self.binding, schema_sha256=self.schema)
        self.assertEqual('COMPLETE', restarted.resume(operation_id=intent['operation_id'])['status'])

    def test_terminal_duplicate_preserves_later_catalog_changes(self):
        _, intent = self.admitted()
        receipt = self.worker.resume(operation_id=intent['operation_id'])
        path = self.root / 'video/katalog.html'
        changed = path.read_bytes().replace(b'Neighbor 9900', b'Neighbor 12000')
        path.write_bytes(changed)
        calls = self.binding.http_calls
        self.assertEqual(receipt, self.worker.resume(operation_id=intent['operation_id']))
        self.assertEqual(changed, path.read_bytes())
        self.assertEqual(calls, self.binding.http_calls)

    def test_interrupt_after_row_commit_resumes_original_job(self):
        _, intent = self.admitted()
        self.worker.fault = lambda event, path: (_ for _ in ()).throw(KeyboardInterrupt()) if event == 'row_deleted' else None
        with self.assertRaises(KeyboardInterrupt):
            self.worker.resume(operation_id=intent['operation_id'])
        self.assertEqual(0, self.scalar('SELECT count(*) FROM cars WHERE id=8'))
        self.assertEqual('ROW_DELETED', self.scalar('SELECT state FROM ua_delete_jobs'))
        restarted = Coordinator(self.binding, schema_sha256=self.schema)
        self.assertEqual('COMPLETE', restarted.resume(operation_id=intent['operation_id'])['status'])

    def test_newer_unrelated_shared_edit_is_preserved(self):
        _, intent = self.admitted()
        path = self.root / 'video/katalog.html'
        changed = path.read_bytes().replace(b'Neighbor 9900', b'Neighbor 10500')
        path.write_bytes(changed)
        self.worker.resume(operation_id=intent['operation_id'])
        self.assertIn(b'Neighbor 10500', path.read_bytes())
        self.assertNotIn(b'UA-0002', path.read_bytes())
        self.assertFalse((self.root / 'video/UA-0002.html').exists())
        self.assertEqual(0, self.scalar('SELECT count(*) FROM cars WHERE id=8'))
        self.assertTrue((self.root / 'private' / ('rebase-' + intent['operation_id'] + '.json')).exists())

    def test_unrelated_edit_during_http_is_rebased_without_manual_retry(self):
        _, intent = self.admitted()
        path = self.root / 'video/katalog.html'
        def change(event, name):
            if event == 'http_observed':
                path.write_bytes(path.read_bytes().replace(b'Neighbor 9900', b'Neighbor 11500'))
        self.worker.fault = change
        self.assertEqual('COMPLETE', self.worker.resume(operation_id=intent['operation_id'])['status'])
        self.assertIn(b'Neighbor 11500', path.read_bytes())

    def test_interrupted_rebase_resumes_current_after_images(self):
        _, intent = self.admitted()
        path = self.root / 'video/katalog.html'
        path.write_bytes(path.read_bytes().replace(b'Neighbor 9900', b'Neighbor 11500'))
        self.worker.fault = lambda event, name: (_ for _ in ()).throw(KeyboardInterrupt()) if event == 'rebase_committed' else None
        with self.assertRaises(KeyboardInterrupt):
            self.worker.resume(operation_id=intent['operation_id'])
        restarted = Coordinator(self.binding, schema_sha256=self.schema)
        restarted.resume(operation_id=intent['operation_id'])
        self.assertIn(b'Neighbor 11500', path.read_bytes())

    def test_row_deleted_rebase_preserves_new_catalog_edit(self):
        _, intent = self.admitted()
        self.worker.fault = lambda event, name: (_ for _ in ()).throw(KeyboardInterrupt()) if event == 'row_deleted' else None
        with self.assertRaises(KeyboardInterrupt):
            self.worker.resume(operation_id=intent['operation_id'])
        path = self.root / 'video/katalog.html'
        path.write_bytes(path.read_bytes().replace(b'Neighbor 9900', b'Neighbor 11500'))
        restarted = Coordinator(self.binding, schema_sha256=self.schema)
        restarted.resume(operation_id=intent['operation_id'])
        self.assertIn(b'Neighbor 11500', path.read_bytes())

    def test_changed_direct_target_never_rebased(self):
        _, intent = self.admitted()
        path = self.root / 'video/UA-0002.html'
        changed = b'<html>newer replacement vehicle</html>'
        path.write_bytes(changed)
        with self.assertRaisesRegex(CoordinatorError, 'NEWER_DIRECT_PAGE_PRESERVED'):
            self.worker.resume(operation_id=intent['operation_id'])
        self.assertEqual(changed, path.read_bytes())

    def test_original_pending_intent_rebases_after_legacy_row_loss(self):
        _, intent = self.admitted()
        with closing(self.binding.connect()) as conn:
            conn.execute('DELETE FROM cars WHERE id=8')
            conn.commit()
        path = self.root / 'video/katalog.html'
        path.write_bytes(path.read_bytes().replace(b'Neighbor 9900', b'Neighbor 11500'))
        self.worker.resume(operation_id=intent['operation_id'])
        self.assertIn(b'Neighbor 11500', path.read_bytes())
        self.assertEqual('COMPLETE', self.scalar('SELECT state FROM ua_delete_jobs'))

    def test_target_row_edit_after_http_prevents_delete(self):
        _, intent = self.admitted()
        def edit(event, name):
            if event == 'http_observed':
                with closing(self.binding.connect()) as conn:
                    conn.execute('UPDATE cars SET price=8700 WHERE id=8')
                    conn.commit()
        self.worker.fault = edit
        with self.assertRaisesRegex(DeletionError, 'NEWER_CAR_IDENTITY'):
            self.worker.resume(operation_id=intent['operation_id'])
        self.assertEqual(8700, self.scalar('SELECT price FROM cars WHERE id=8'))

    def test_other_database_edits_survive_full_completion(self):
        _, intent = self.admitted()
        with closing(self.binding.connect()) as conn:
            conn.execute('UPDATE cars SET price=12000 WHERE id=9')
            conn.commit()
        self.worker.resume(operation_id=intent['operation_id'])
        self.assertEqual(12000, self.scalar('SELECT price FROM cars WHERE id=9'))

    def test_corrupt_backup_refuses_any_public_effect(self):
        _, intent = self.admitted()
        path = self.root / 'private' / ('manifest-' + intent['backup_sha256'] + '.json')
        manifest = json.loads(path.read_bytes())
        (self.root / 'private' / manifest['database_file']).write_bytes(b'corrupt')
        with self.assertRaisesRegex(CoordinatorError, 'BACKUP_DATABASE_CORRUPTED'):
            self.worker.resume(operation_id=intent['operation_id'])
        self.assertEqual(self.original_html, (self.root / 'video/katalog.html').read_bytes())

    def test_redirect_does_not_complete_and_retry_can_finish(self):
        _, intent = self.admitted()
        self.binding.http_mode = 'redirect'
        with self.assertRaisesRegex(CoordinatorError, 'HTTP_REDIRECT'):
            self.worker.resume(operation_id=intent['operation_id'])
        self.assertEqual(1, self.scalar('SELECT count(*) FROM cars WHERE id=8'))
        self.binding.http_mode = None
        self.worker.resume(operation_id=intent['operation_id'])

    def test_stale_http_evidence_cannot_delete_row(self):
        _, intent = self.admitted()
        self.binding.http_mode = 'stale'
        with self.assertRaisesRegex(CoordinatorError, 'HTTP_EVIDENCE_STALE'):
            self.worker.resume(operation_id=intent['operation_id'])
        self.assertEqual(1, self.scalar('SELECT count(*) FROM cars WHERE id=8'))

    def test_newer_media_is_preserved(self):
        _, intent = self.admitted()
        photo = self.root / 'video/car-photo.webp'
        photo.write_bytes(b'operator-new-photo')
        with self.assertRaisesRegex(CoordinatorError, 'NEWER_MEDIA_PRESERVED'):
            self.worker.resume(operation_id=intent['operation_id'])
        self.assertEqual(b'operator-new-photo', photo.read_bytes())

    def test_draft_no_public_writes(self):
        with closing(self.binding.connect()) as conn:
            conn.execute('UPDATE cars SET published=0 WHERE id=8')
            conn.commit()
        for name in ('index.html', 'katalog.html'):
            path = self.root / 'video' / name
            with self.binding.fence():
                path.write_bytes(self.binding.transform_lists('UA-0002', {name: path.read_bytes()})[name])
        path = self.root / 'video/sitemap.xml'
        path.write_bytes(retire_sitemap(path.read_bytes(), 'UA-0002'))
        (self.root / 'video/UA-0002.html').unlink()
        (self.root / 'video/UA-0002-diag.html').unlink()
        stamps = {path: (path.stat().st_mtime_ns, path.read_bytes()) for path in (self.root / 'video').iterdir()}
        _, intent = self.admitted()
        self.worker.resume(operation_id=intent['operation_id'])
        self.assertEqual(stamps, {path: (path.stat().st_mtime_ns, path.read_bytes()) for path in (self.root / 'video').iterdir()})

    def test_draft_with_residual_listing_refused_before_intent(self):
        with closing(self.binding.connect()) as conn:
            conn.execute('UPDATE cars SET published=0 WHERE id=8')
            conn.commit()
        with self.assertRaisesRegex(CoordinatorError, 'DRAFT_HAS_PUBLIC_RESIDUAL'):
            self.admitted()
        self.assertEqual(0, self.scalar('SELECT count(*) FROM ua_delete_intents'))

    def test_unauthorized_or_stale_confirmation_cannot_admit(self):
        with self.assertRaisesRegex(CoordinatorError, 'STAFF_AUTHORIZATION'):
            self.worker.confirm(car_id=8, actor_id=999)
        token = self.worker.confirm(car_id=8, actor_id=101)
        with closing(self.binding.connect()) as conn:
            conn.execute('UPDATE cars SET price=8700 WHERE id=8')
            conn.commit()
        with self.assertRaisesRegex(CoordinatorError, 'STALE_CONFIRMATION'):
            self.worker.admit(token=token, actor_id=101)

    def test_public_target_cannot_be_declared_entirely_local_only(self):
        original = self.binding.resolve_plan
        def invalid(row):
            plan = original(row)
            plan['routes'] = {url: name for url, name in plan['routes'].items() if name not in plan['direct']}
            plan['local_only'] = plan['direct']
            return plan
        self.binding.resolve_plan = invalid
        with self.assertRaisesRegex(CoordinatorError, 'PUBLIC_TARGET_HTTP_EVIDENCE_REQUIRED'):
            self.admitted()


class ParserTests(unittest.TestCase):
    def test_html_line_offsets_preserve_non_lf_separators(self):
        for separator in ('\r', '\f', '\u2028'):
            prefix = ('KEEP' + separator + 'UNRELATED-TEXT\n').encode()
            with self.subTest(separator=repr(separator)):
                source = prefix + b'<a href="UA-0002.html">target-text-long-enough</a>TAIL'
                self.assertEqual(prefix + b'TAIL', retire_html(source, 'UA-0002'))

    def test_sitemap_comments_and_unicode_preserved(self):
        comment = '<!-- <url><loc>https://example.test/UA-0002.html</loc></url> оставить -->'
        other = '<url><loc>https://example.test/UA-0003.html</loc><lastmod>дата</lastmod></url>'
        removed = '<url><loc>https://example.test/UA-0002.html</loc></url>'
        source = ('<urlset>' + comment + removed + other + '</urlset>').encode()
        self.assertEqual(('<urlset>' + comment + other + '</urlset>').encode(), retire_sitemap(source, 'UA-0002'))

    def test_ambiguous_multi_car_article_refused(self):
        with self.assertRaisesRegex(RetirementError, 'MULTIPLE_CARS'):
            retire_html(b'<article><a href="UA-0002.html">A</a><a href="UA-0003.html">B</a></article>', 'UA-0002')

    def test_encoded_alias_removed_and_decorative_media_retained(self):
        source = b'<a href="UA%2D0002-diag-abcdef.html">gone</a><img src="UA-0002.webp"><a href="UA-0003.html">stay</a>'
        self.assertEqual(b'<img src="UA-0002.webp"><a href="UA-0003.html">stay</a>', retire_html(source, 'UA-0002'))


if __name__ == '__main__':
    unittest.main()
