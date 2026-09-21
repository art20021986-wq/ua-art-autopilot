"""Execute the candidate built from the actual reviewed WSGI with fake DB/integrations."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from build_route_patch import BASELINE, INCIDENT_PLAN_SHA256, OBSERVED_LEGACY_ROUTES, transform
from ua_crm_deleted_routes import DeletedRoutes, GONE, RouteStateUnavailable, _encoded


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class CandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Explicit external input: the production source is never copied into git.
        source = os.environ.get('UA_DELETE_WSGI_SOURCE')
        if not source:
            raise RuntimeError('Set UA_DELETE_WSGI_SOURCE to the captured authoritative WSGI file')
        cls.source = Path(source).read_bytes()
        if sha(cls.source) != BASELINE:
            raise RuntimeError('Captured WSGI changed; source must be reviewed again')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'crm.db'
        self.journal = self.root / 'private'
        self.journal.mkdir(mode=0o700)
        with sqlite3.connect(self.db) as conn:
            conn.execute('CREATE TABLE cars(id INTEGER PRIMARY KEY,auto_number TEXT)')
            conn.execute("INSERT INTO cars VALUES(3,'UA-0003')")
        self.files = {'index.html', 'katalog.html', 'info.html', 'podbor.html',
                      'UA-0002.html', 'UA-0003.html', 'UA-0004.html', 'UA-0020.html'}
        self.events = []

    def build(self, *, candidate=True, routes=OBSERVED_LEGACY_ROUTES):
        def integration(name, path):
            def wrapper(previous):
                def application(environ, start_response):
                    self.events.append(name)
                    if environ.get('PATH_INFO') == path:
                        payload = (name + '-unchanged').encode()
                        start_response('201 Created', [('Content-Length', str(len(payload)))])
                        return [payload]
                    return previous(environ, start_response)
                return application
            return types.SimpleNamespace(obolochka=wrapper)

        modules = {
            'analitika_wsgi': integration('analytics', '/analytics-ingress'),
            'uaart_bridge_wsgi': integration('bridge', '/bridge-ingress'),
            'ua_crm_deleted_routes': types.SimpleNamespace(
                DeletedRoutes=lambda **kwargs: DeletedRoutes(db=self.db, journal=self.journal, **kwargs))}
        namespace = {'__name__': '_candidate_wsgi'}
        raw = transform(self.source, legacy_routes=routes) if candidate else self.source
        with patch.dict(sys.modules, modules):
            exec(compile(raw, '<actual-reviewed-wsgi-candidate>', 'exec'), namespace)
        # Only the hardcoded production directory inspection is stubbed.
        namespace['_ua_seo068_wsgi_os'] = types.SimpleNamespace(
            listdir=lambda root: sorted(self.files),
            path=types.SimpleNamespace(join=os.path.join, isfile=lambda path: Path(path).name in self.files))
        return namespace['application']

    @staticmethod
    def request(app, path, method='GET', query=''):
        received = []
        body = app({'PATH_INFO': path, 'REQUEST_METHOD': method, 'QUERY_STRING': query},
                   lambda status, headers, exc_info=None: received.append((status, headers)))
        payload = b''.join(body)
        if hasattr(body, 'close'):
            body.close()
        assert len(received) == 1
        return received[0][0], dict(received[0][1]), payload

    def intent(self, *, code='UA-0003', state='REQUESTED', extra_routes=None, local_only=()):
        direct = ['video/' + code + '.html']
        if extra_routes:
            direct += list(extra_routes.values())
        direct = sorted(set(direct))
        routes = {'https://www.uaart.com.ua/video/' + code + '.html': 'video/' + code + '.html',
                  'https://www.uaart.com.ua/video/index.html': 'video/index.html'}
        routes.update(extra_routes or {})
        plan = {'mode': 'PUBLIC_OR_RESIDUAL', 'car_code': code,
                'direct': sorted(set(direct) | set(local_only)), 'lists': ['video/index.html'],
                'sitemaps': [], 'media': [], 'routes': routes, 'local_only': list(local_only)}
        core = {'mode': plan['mode'], 'car_code': code, 'public_targets': plan['direct'],
                'list_surfaces': plan['lists'], 'media_targets': []}
        encoded = _encoded(core).decode()
        manifest = {'version': 1, 'database_integrity': 'ok', 'snapshot_sha256': 'a' * 64, 'plan': plan}
        raw = _encoded(manifest)
        digest = sha(raw)
        path = self.journal / ('manifest-' + digest + '.json')
        path.write_bytes(raw)
        with sqlite3.connect(self.db) as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS ua_delete_intents(car_code TEXT,state TEXT,plan TEXT,'
                         'plan_sha256 TEXT,backup_sha256 TEXT,snapshot_sha256 TEXT)')
            conn.execute('INSERT INTO ua_delete_intents VALUES(?,?,?,?,?,?)',
                         (code, state, encoded, sha(encoded.encode()), digest, 'a' * 64))
        return path

    def test_builder_is_hash_bound_and_only_appends(self):
        candidate = transform(self.source)
        self.assertTrue(candidate.startswith(self.source.decode()))
        with self.assertRaisesRegex(ValueError, 'HASH_REQUIRED'):
            transform(self.source + b'\n')
        with self.assertRaises(RouteStateUnavailable):
            transform(self.source, legacy_routes=('/video/UA-0003.html',))

    def test_exact_legacy_get_head_all_methods_and_query(self):
        app = self.build()
        for path in OBSERVED_LEGACY_ROUTES:
            for method in ('GET', 'HEAD', 'POST', 'OPTIONS'):
                status, headers, body = self.request(app, path, method, 'lang=ua')
                self.assertEqual('410 Gone', status)
                self.assertNotIn('Location', headers)
                self.assertEqual('no-store', headers['Cache-Control'])
                self.assertEqual(str(len(GONE)), headers['Content-Length'])
                self.assertEqual(b'' if method == 'HEAD' else GONE, body)

    def test_exact_legacy_inventory_is_bound_to_incident_preimages_and_static_mapping(self):
        evidence = json.loads(Path(__file__).with_name('legacy_route_evidence.json').read_text())
        self.assertEqual(INCIDENT_PLAN_SHA256, evidence['incident_plan_sha256'])
        self.assertEqual({'url_prefix': '/video/', 'directory': '/home/Carix/video/'},
                         evidence['observed_static_mapping'])
        self.assertEqual(sorted(OBSERVED_LEGACY_ROUTES), sorted(evidence['routes']))
        for path, preimage in evidence['routes'].items():
            self.assertEqual(path[1:], preimage['relative_file'])
            self.assertIs(preimage['exists'], True)
            self.assertGreater(preimage['bytes'], 0)
            self.assertEqual(64, len(preimage['sha256']))

    def test_no_unverified_alias_is_guessed(self):
        app = self.build()
        for path in ('/UA-0002.html', '/site/UA-0002.html', '/site/UA-0002-diag.html',
                     '/site/UA-0002-a6f9d391.html', '/video/UA-0002-a6f9d392.html',
                     '/video/UA-0002-abcdef12.html', '/video/UA-0002.webp',
                     '/video/UA-00020.html', '/video/ua-0002.html', '/video/UA-0002.html/extra'):
            self.assertEqual('302 Found', self.request(app, path)[0], path)

    def test_only_explicit_additional_legacy_inventory_is_used(self):
        routes = ('/video/UA-0002.html', '/site/UA-0002.html', '/video/UA-0002-diag-abcdef12.html')
        app = self.build(routes=routes)
        for path in routes:
            self.assertEqual('410 Gone', self.request(app, path)[0])
        self.assertEqual('302 Found', self.request(app, '/video/UA-0002-diag-abcdef13.html')[0])

    def test_existing_wrappers_robots_and_unrelated_routes_are_identical(self):
        baseline, candidate = self.build(candidate=False), self.build()
        for path in ('/', '/anything', '/video/index.html', '/robots.txt',
                     '/bridge-ingress', '/analytics-ingress', '/video/UA-0004.html'):
            for method in ('GET', 'HEAD', 'POST'):
                self.events.clear()
                expected = self.request(baseline, path, method)
                expected_events = list(self.events)
                self.events.clear()
                self.assertEqual(expected, self.request(candidate, path, method), (path, method))
                self.assertEqual(expected_events, self.events)

    def test_all_intent_states_serve_exact_routes_and_no_guessed_aliases(self):
        for code, state in (('UA-0003', 'REQUESTED'), ('UA-0004', 'ROW_DELETED'), ('UA-0020', 'COMPLETE')):
            self.intent(code=code, state=state)
        app = self.build()
        for code in ('UA-0003', 'UA-0004', 'UA-0020'):
            self.assertEqual('410 Gone', self.request(app, '/video/' + code + '.html')[0])
            self.assertEqual('302 Found', self.request(app, '/site/' + code + '.html')[0])

    def test_manifest_verified_hash_alias_and_local_mirror(self):
        alias = '/video/UA-0003-diag-abcdef12.html'
        self.intent(extra_routes={'https://www.uaart.com.ua' + alias: alias[1:]},
                    local_only=('site/UA-0003.html',))
        app = self.build()
        self.assertEqual('410 Gone', self.request(app, alias)[0])
        self.assertEqual('302 Found', self.request(app, '/site/UA-0003.html')[0])
        self.assertEqual('302 Found', self.request(app, alias.replace('abcdef12', 'abcdef13'))[0])

    def test_dynamic_sitemap_removes_stale_tombstones_and_preserves_neighbor_bytes(self):
        self.intent()
        baseline, candidate = self.build(candidate=False), self.build()
        before = self.request(baseline, '/sitemap.xml')[2]
        expected = before.replace(b'  <url><loc>https://www.uaart.com.ua/video/UA-0002.html</loc></url>\n', b'')
        expected = expected.replace(b'  <url><loc>https://www.uaart.com.ua/video/UA-0003.html</loc></url>\n', b'')
        status, headers, body = self.request(candidate, '/sitemap.xml')
        self.assertEqual(('200 OK', expected), (status, body))
        self.assertEqual(str(len(expected)), headers['Content-Length'])
        self.assertIn(b'UA-0004.html', body)
        self.assertIn(b'index.html', body)
        head = self.request(candidate, '/sitemap.xml', 'HEAD')
        self.assertEqual(('200 OK', b''), (head[0], head[2]))
        self.assertEqual(headers, head[1])
        self.assertEqual(self.request(baseline, '/sitemap.xml', 'POST'),
                         self.request(candidate, '/sitemap.xml', 'POST'))

    def test_corrupt_manifest_does_not_hide_problem_or_break_unrelated_paths(self):
        manifest = self.intent()
        manifest.write_bytes(manifest.read_bytes() + b'\n')
        app = self.build()
        for path in ('/video/UA-0003.html', '/sitemap.xml'):
            status, headers, body = self.request(app, path)
            self.assertEqual('503 Service Unavailable', status)
            self.assertEqual('30', headers['Retry-After'])
            self.assertNotIn(str(self.root).encode(), body)
        self.assertEqual('410 Gone', self.request(app, '/video/UA-0002.html')[0])
        self.assertEqual('302 Found', self.request(app, '/')[0])
        self.assertEqual('201 Created', self.request(app, '/bridge-ingress')[0])
        self.assertEqual('200 OK', self.request(app, '/robots.txt')[0])

    def test_missing_db_never_created_and_legacy_route_still_gone(self):
        self.db.unlink()
        app = self.build()
        self.assertEqual('410 Gone', self.request(app, '/video/UA-0002.html')[0])
        self.assertEqual('503 Service Unavailable', self.request(app, '/video/UA-0003.html')[0])
        self.assertFalse(self.db.exists())

    def test_corrupt_other_intent_does_not_change_neighbor_card(self):
        manifest = self.intent()
        manifest.write_bytes(manifest.read_bytes() + b'\n')
        baseline, candidate = self.build(candidate=False), self.build()
        self.assertEqual('503 Service Unavailable', self.request(candidate, '/video/UA-0003.html')[0])
        for path in ('/video/UA-0004.html', '/site/UA-0004.html', '/video/UA-0004-diag.html'):
            self.assertEqual(self.request(baseline, path), self.request(candidate, path))
        self.assertEqual('503 Service Unavailable', self.request(candidate, '/sitemap.xml')[0])

    def test_null_or_binary_plan_and_null_hashes_return_bounded_503(self):
        self.intent()
        app = self.build()
        with sqlite3.connect(self.db) as conn:
            values = conn.execute('SELECT plan,plan_sha256,backup_sha256,snapshot_sha256 FROM ua_delete_intents').fetchone()
        for field, value in (('plan', None), ('plan', b'not text'), ('plan_sha256', None),
                             ('backup_sha256', None), ('snapshot_sha256', None)):
            with sqlite3.connect(self.db) as conn:
                conn.execute('UPDATE ua_delete_intents SET plan=?,plan_sha256=?,backup_sha256=?,snapshot_sha256=?', values)
                conn.execute('UPDATE ua_delete_intents SET ' + field + '=?', (value,))
            for path in ('/video/UA-0003.html', '/sitemap.xml'):
                self.assertEqual('503 Service Unavailable', self.request(app, path)[0], (field, path))
            self.assertEqual('302 Found', self.request(app, '/video/UA-0004.html')[0])

    def test_state_read_never_changes_database_or_schema(self):
        self.intent()
        before = self.db.read_bytes()
        app = self.build()
        for path in ('/sitemap.xml', '/video/UA-0003.html', '/video/UA-0004.html'):
            self.request(app, path)
        self.assertEqual(before, self.db.read_bytes())

    def test_unbound_or_foreign_url_rejected(self):
        manifest = self.intent(extra_routes={'https://evil.example/video/UA-0003-diag.html':
                                            'video/UA-0003-diag.html'})
        self.assertTrue(manifest.is_file())
        self.assertEqual('503 Service Unavailable', self.request(self.build(), '/video/UA-0003.html')[0])

    def test_invalid_intent_schema_or_state_fails_closed(self):
        self.intent(state='CANCELLED')
        app = self.build()
        self.assertEqual('503 Service Unavailable', self.request(app, '/sitemap.xml')[0])
        with sqlite3.connect(self.db) as conn:
            conn.execute('DROP TABLE ua_delete_intents')
            conn.execute('CREATE TABLE ua_delete_intents(car_code TEXT)')
        self.assertEqual('503 Service Unavailable', self.request(app, '/sitemap.xml')[0])


if __name__ == '__main__':
    unittest.main()
