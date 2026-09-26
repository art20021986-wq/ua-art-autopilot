"""Exact deleted-card routing; read-only journal access and no import effects.

Static files remain owned by the web server. This wrapper handles requests
which reach WSGI, including missing static files, and filters the existing
dynamic sitemap. The installer must separately retire the exact static files.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote, urlsplit


DB = '/home/Carix/crm.db'
JOURNAL = '/home/Carix/ua_crm_deletion_state'
HOSTS = frozenset(('www.uaart.com.ua', 'uaart.com.ua'))
CARD_PATH = re.compile(r'^/(?:video/|site/)?(UA-[0-9]{4})(?:-diag)?(?:-[0-9a-f]{6,10})?\.html$')
HASH = re.compile(r'^[0-9a-f]{64}$')
GONE = b'This vehicle is no longer available.\n'
UNAVAILABLE = b'Temporarily unavailable.\n'


class RouteStateUnavailable(RuntimeError):
    pass


def _require(condition, message):
    if not condition:
        raise RouteStateUnavailable(message)


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _encoded(data):
    return json.dumps(data, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('utf-8')


def _url_path(url):
    parsed = urlsplit(url)
    _require(parsed.scheme in ('http', 'https') and parsed.netloc in HOSTS and
             not parsed.query and not parsed.fragment and not parsed.username and
             parsed.path.startswith('/'), 'EXACT_LOCAL_PUBLIC_URL_REQUIRED')
    return parsed.path


def validate_legacy_routes(paths):
    """Historical incident routes are explicit, independently verified inputs."""
    _require(isinstance(paths, (tuple, list)) and len(paths) == len(set(paths)),
             'UNIQUE_LEGACY_ROUTE_LIST_REQUIRED')
    for path in paths:
        match = CARD_PATH.fullmatch(path) if isinstance(path, str) else None
        _require(match is not None and match[1] == 'UA-0002',
                 'EXACT_INCIDENT_ROUTE_REQUIRED')
    return frozenset(paths)


def _manifest_routes(intent, journal):
    _require(isinstance(intent['plan'], str), 'TEXT_INTENT_PLAN_REQUIRED')
    for name in ('backup_sha256', 'plan_sha256', 'snapshot_sha256'):
        _require(isinstance(intent[name], str) and HASH.fullmatch(intent[name]),
                 'EXACT_INTENT_HASH_REQUIRED')
    digest = intent['backup_sha256']
    root = Path(journal)
    _require(root.is_absolute() and root.resolve(strict=True) == root and
             root.is_dir() and root.stat().st_mode & 0o077 == 0,
             'PRIVATE_CANONICAL_JOURNAL_REQUIRED')
    path = root / ('manifest-' + digest + '.json')
    _require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 2 * 1024 * 1024,
             'BOUNDED_MANIFEST_REQUIRED')
    raw = path.read_bytes()
    _require(_digest(raw) == digest, 'MANIFEST_HASH_MISMATCH')
    manifest = json.loads(raw)
    _require(isinstance(manifest, dict) and manifest['version'] == 1 and manifest['database_integrity'] == 'ok' and
             manifest['snapshot_sha256'] == intent['snapshot_sha256'],
             'MANIFEST_IDENTITY_MISMATCH')
    plan = manifest['plan']
    _require(isinstance(plan, dict) and set(plan) in ({'mode', 'car_code', 'direct', 'lists', 'sitemaps', 'media', 'routes'},
                          {'mode', 'car_code', 'direct', 'lists', 'sitemaps', 'media', 'routes', 'local_only'}) and
             plan['car_code'] == intent['car_code'], 'EXACT_MANIFEST_PLAN_REQUIRED')
    for key in ('direct', 'lists', 'sitemaps', 'media'):
        values = plan[key]
        _require(isinstance(values, list) and all(isinstance(v, str) for v in values) and
                 values == sorted(set(values)), 'EXACT_MANIFEST_INVENTORY_REQUIRED')
    core = {'mode': plan['mode'], 'car_code': plan['car_code'],
            'public_targets': plan['direct'], 'list_surfaces': sorted(plan['lists'] + plan['sitemaps']),
            'media_targets': []}
    _require(_digest(intent['plan'].encode('utf-8')) == intent['plan_sha256'] and
             _encoded(core).decode('utf-8') == intent['plan'], 'MANIFEST_INTENT_BINDING_FAILED')
    _require(isinstance(plan['routes'], dict), 'EXACT_ROUTE_MAP_REQUIRED')
    direct = set(plan['direct'])
    covered, paths = set(), set()
    surfaces = direct | set(plan['lists']) | set(plan['sitemaps'])
    for url, target in plan['routes'].items():
        _require(isinstance(url, str) and isinstance(target, str) and target in surfaces,
                 'UNBOUND_MANIFEST_ROUTE')
        path = _url_path(url)
        covered.add(target)
        if target in direct:
            match = CARD_PATH.fullmatch(path)
            target_match = CARD_PATH.fullmatch('/' + target)
            _require(match is not None and target_match is not None and
                     match[1] == intent['car_code'] == target_match[1] and
                     path.rsplit('/', 1)[-1] == target.rsplit('/', 1)[-1],
                     'EXACT_DIRECT_ROUTE_IDENTITY_REQUIRED')
            paths.add(path)
    local_only = plan.get('local_only', [])
    _require(isinstance(local_only, list) and all(isinstance(v, str) for v in local_only) and
             local_only == sorted(set(local_only)) and not covered.intersection(local_only) and
             covered | set(local_only) == surfaces, 'INCOMPLETE_ROUTE_COVERAGE')
    return paths


class DeletedRoutes:
    def __init__(self, *, db=DB, journal=JOURNAL, legacy_routes=()):
        self.db, self.journal = str(db), str(journal)
        self.legacy = validate_legacy_routes(legacy_routes)

    def snapshot(self, *, car_code=None):
        """Read a consistent snapshot, isolating card requests to that identity."""
        try:
            path = Path(self.db)
            _require(path.is_absolute() and path.is_file() and not path.is_symlink() and
                     path.resolve(strict=True) == path, 'CANONICAL_DATABASE_REQUIRED')
            with closing(sqlite3.connect('file:' + quote(str(path), safe='/') + '?mode=ro',
                                         uri=True, timeout=0.25)) as conn:
                conn.execute('PRAGMA query_only=ON')
                conn.execute('BEGIN')
                schema = conn.execute("SELECT type FROM sqlite_master WHERE name='ua_delete_intents'").fetchone()
                if schema is None:
                    return self.legacy  # Explicit staged-install compatibility.
                _require(schema == ('table',), 'INTENT_TABLE_REQUIRED')
                fields = ('car_code', 'state', 'plan', 'plan_sha256', 'backup_sha256', 'snapshot_sha256')
                columns = {row[1] for row in conn.execute('PRAGMA table_info(ua_delete_intents)')}
                _require(set(fields) <= columns, 'INTENT_SCHEMA_MISMATCH')
                sql = 'SELECT ' + ','.join(fields) + ' FROM ua_delete_intents'
                params = ()
                if car_code is not None:
                    _require(isinstance(car_code, str) and re.fullmatch(r'UA-[0-9]{4}', car_code),
                             'EXACT_LOOKUP_CODE_REQUIRED')
                    sql += ' WHERE car_code=?'
                    params = (car_code,)
                rows = conn.execute(sql, params).fetchall()
            paths = set(self.legacy)
            for row in rows:
                intent = dict(zip(fields, row))
                _require(intent['state'] in ('REQUESTED', 'ROW_DELETED', 'COMPLETE'), 'UNKNOWN_INTENT_STATE')
                _require(isinstance(intent['car_code'], str) and
                         re.fullmatch(r'UA-[0-9]{4}', intent['car_code']), 'INTENT_CODE_REQUIRED')
                paths.update(_manifest_routes(intent, self.journal))
            return frozenset(paths)
        except RouteStateUnavailable:
            raise
        except (OSError, sqlite3.Error, ValueError, TypeError, KeyError) as exc:
            raise RouteStateUnavailable('DELETION_STATE_UNAVAILABLE') from exc

    def filter_sitemap(self, payload):
        """Preserve every byte except exact retired URL lines in the reviewed SEO output."""
        retired = self.snapshot()
        lines = payload.splitlines(keepends=True)
        retained = []
        for line in lines:
            match = re.fullmatch(rb'  <url><loc>(https?://[^<>]+)</loc></url>\r?\n?', line)
            if match and _url_path(match[1].decode('utf-8')) in retired:
                continue
            retained.append(line)
        return b''.join(retained)

    @staticmethod
    def _response(environ, start_response, status, payload):
        headers = [('Content-Type', 'text/plain; charset=utf-8'),
                   ('Content-Length', str(len(payload))), ('Cache-Control', 'no-store'),
                   ('X-Content-Type-Options', 'nosniff'), ('X-Robots-Tag', 'noindex')]
        if status == '503 Service Unavailable':
            headers.append(('Retry-After', '30'))
        start_response(status, headers)
        return [] if str(environ.get('REQUEST_METHOD', 'GET')).upper() == 'HEAD' else [payload]

    def wrap(self, previous):
        def application(environ, start_response):
            path = str(environ.get('PATH_INFO', ''))
            if path in self.legacy:
                return self._response(environ, start_response, '410 Gone', GONE)
            try:
                match = CARD_PATH.fullmatch(path)
                if match and path in self.snapshot(car_code=match[1]):
                    return self._response(environ, start_response, '410 Gone', GONE)
                return previous(environ, start_response)
            except RouteStateUnavailable:
                return self._response(environ, start_response, '503 Service Unavailable', UNAVAILABLE)
        return application
