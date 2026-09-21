"""Concrete legacy binding. Activation requires an installer-owned config.

No migration, configuration write or process restart occurs on import or
factory invocation. Missing reviewed configuration/schema refuses activation.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import importlib
import json
from pathlib import Path
import re
import time
import types
from urllib.parse import quote, urlsplit
import urllib.error
import urllib.request

try:
    from .coordinator import Coordinator, require, sha
    from .deletion_state import ImmediateTransaction, application_schema_sha256, install_additive_schema
    from .public_write_guard import advertised_codes
    from .retirement import retire_html, retire_sitemap, url_code
except ImportError:
    from coordinator import Coordinator, require, sha
    from deletion_state import ImmediateTransaction, application_schema_sha256, install_additive_schema
    from public_write_guard import advertised_codes
    from retirement import retire_html, retire_sitemap, url_code


ROOT = Path('/home/Carix')
JOURNAL = ROOT / 'ua_crm_deletion_state'
COUNTERS_SHA256 = '500ca67145faa38ca9f72ac6da85e2a7d1c351f8f2fcca4a2edeb34c22734c23'
OBSERVED_APPLICATION_SCHEMA_SHA256 = '1d5aacc240cc0e330ae059bf56e32a3ce50200ee1bfe08da8834ae4f98c0480a'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class LegacyBinding:
    def __init__(self, *, db, counters, fence_module, config, root=ROOT, journal=JOURNAL):
        self.db, self.counters, self.fence_module = db, counters, fence_module
        self.public_root, self.journal_root = Path(root), Path(journal)
        self.config = json.loads(json.dumps(config))
        require(set(config) == {'version', 'application_schema_sha256', 'source_sha256',
                                'shared', 'shared_routes', 'direct_route_prefixes', 'writers_receipt_sha256'},
                'EXACT_RUNTIME_CONFIG_REQUIRED')
        require(config['version'] == 1, 'RUNTIME_CONFIG_VERSION')
        for key in ('application_schema_sha256', 'writers_receipt_sha256'):
            require(re.fullmatch(r'[0-9a-f]{64}', str(config[key])), 'RELEASE_DIGEST_REQUIRED')
        require(config['source_sha256'].get('ua_site_counters.py') == COUNTERS_SHA256, 'REVIEWED_COUNTER_SOURCE_REQUIRED')
        for name, digest in config['source_sha256'].items():
            require(re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*\.py', name) and
                    re.fullmatch(r'[0-9a-f]{64}', digest), 'EXACT_SOURCE_PIN_REQUIRED')
            path = self.public_root / name
            require(path.resolve(strict=True) == path and sha(path.read_bytes()) == digest, 'RUNTIME_SOURCE_CHANGED:' + name)
        for module, name in ((db, 'db.py'), (counters, 'ua_site_counters.py'), (fence_module, 'publication_fence.py')):
            require(name in config['source_sha256'] and Path(module.__file__).resolve() == self.public_root / name,
                    'RUNTIME_MODULE_IDENTITY_CHANGED:' + name)
        self.shared = config['shared']
        require(isinstance(self.shared, dict) and self.shared and
                set(self.shared.values()) <= {'CATALOG', 'MODERN_HOME', 'LEGACY_HOME', 'SITEMAP'} and
                list(self.shared.values()).count('CATALOG') >= 1, 'SHARED_SURFACE_CONFIG_REQUIRED')
        require(set(config['shared_routes']) == set(self.shared), 'SHARED_ROUTE_CONFIG_REQUIRED')
        require(set(config['direct_route_prefixes']) == {'video', 'site'}, 'BOTH_MIRRORS_MUST_BE_CLASSIFIED')
        require(bool(config['direct_route_prefixes']['video']), 'SERVED_VIDEO_TARGET_ROUTES_REQUIRED')
        for name, kind in self.shared.items():
            require(name in {folder + '/' + file for folder in ('video', 'site')
                            for file in ('index.html', 'katalog.html', 'sitemap.xml')}, 'EXACT_SHARED_SURFACE_REQUIRED')
            require((kind == 'CATALOG') == name.endswith('/katalog.html') and
                    (kind == 'SITEMAP') == name.endswith('/sitemap.xml'), 'SHARED_KIND_MISMATCH')
        for urls in list(config['shared_routes'].values()) + list(config['direct_route_prefixes'].values()):
            require(isinstance(urls, list) and urls == sorted(set(urls)), 'SORTED_EXACT_HTTP_ENDPOINTS_REQUIRED')
            for url in urls:
                parsed = urlsplit(url)
                require(parsed.scheme == 'https' and parsed.hostname in ('uaart.com.ua', 'www.uaart.com.ua') and
                        parsed.port in (None, 443) and not parsed.query and not parsed.fragment and
                        not parsed.username, 'APPROVED_SITE_ORIGIN_REQUIRED')
        # The installed home helper ends by injecting JS. Clone ONLY its
        # globals to preserve current served scripts; never mutate the module.
        scope = dict(counters.__dict__, inject_script=lambda source: source)
        self.patch_home = types.FunctionType(counters.patch_home.__code__, scope,
                                             counters.patch_home.__name__, counters.patch_home.__defaults__)
        with closing(self.connect()) as conn:
            require(application_schema_sha256(conn) == config['application_schema_sha256'], 'LIVE_APPLICATION_SCHEMA_CHANGED')

    def connect(self):
        return self.db.connect()

    def fence(self):
        return self.fence_module.publication_fence(timeout=90.0)

    def require_fence(self):
        return self.fence_module.require_publication_fence()

    def authorize(self, actor_id):
        staff = self.db.get_staff(actor_id)
        return bool(staff and staff.get('active') == 1)

    def _path(self, relative):
        path = self.public_root / relative
        require(path.resolve(strict=False) == path and not path.is_symlink(), 'RUNTIME_PATH_CHANGED')
        return path

    def resolve_plan(self, row):
        self.require_fence()
        code = row.get('auto_number')
        require(isinstance(code, str) and re.fullmatch(r'UA-[0-9]{4}', code), 'EXACT_CODE_REQUIRED')
        aliases = set()
        any_direct = False
        for folder in ('video', 'site'):
            root = self._path(folder)
            require(root.is_dir(), 'KNOWN_MIRROR_MISSING')
            names = {code + '.html', code + '-diag.html'}
            for path in root.iterdir():
                if not (path.suffix.lower() == '.html' and path.name.upper().startswith(code)):
                    continue
                require(url_code(path.name) == code, 'UNKNOWN_TARGET_HTML_ALIAS')
                names.add(path.name)
            for name in names:
                relative = folder + '/' + name
                path = self._path(relative)
                require(not path.exists() or path.is_file(), 'REGULAR_ALIAS_REQUIRED')
                any_direct |= path.exists()
                aliases.add(relative)
        lists = sorted(name for name, kind in self.shared.items() if kind != 'SITEMAP')
        sitemaps = sorted(name for name, kind in self.shared.items() if kind == 'SITEMAP')
        residual = any_direct
        for name in lists:
            residual |= code in advertised_codes(self._path(name).read_text(encoding='utf-8'))
        for name in sitemaps:
            data = self._path(name).read_bytes()
            residual |= retire_sitemap(data, code) != data
        require(row.get('published') in (0, 1), 'PUBLICATION_FLAG_REQUIRED')
        public = bool(row['published'] or residual)
        direct = sorted(aliases) if public else []
        routes = {}
        for name in lists + sitemaps:
            for url in self.config['shared_routes'][name]:
                require(url not in routes, 'DUPLICATE_HTTP_ROUTE')
                routes[url] = name
        for name in direct:
            folder, basename = name.split('/', 1)
            for prefix in self.config['direct_route_prefixes'][folder]:
                require(prefix.endswith('/'), 'DIRECT_ROUTE_PREFIX_REQUIRED')
                url = prefix + quote(basename)
                require(url not in routes, 'DUPLICATE_HTTP_ROUTE')
                routes[url] = name
        return {'mode': 'PUBLIC_OR_RESIDUAL' if public else 'NEVER_PUBLISHED', 'car_code': code,
                'direct': direct, 'lists': lists, 'sitemaps': sitemaps, 'media': [], 'routes': routes,
                'local_only': sorted(set(direct + lists + sitemaps) - set(routes.values()))}

    def transform_lists(self, code, before):
        self.require_fence()
        stripped, reference, counts = {}, None, None
        for name, data in before.items():
            transformed = retire_html(data, code)
            if self.shared[name] == 'CATALOG':
                original, _ = self.counters.catalog_snapshot(data.decode('utf-8'))
                current, current_counts = self.counters.catalog_snapshot(transformed.decode('utf-8'))
                require(current == {key: value for key, value in original.items() if key != code}, 'OTHER_CATALOG_MEMBERSHIP_CHANGED')
                require(reference is None or reference == current, 'CATALOG_MIRRORS_DIFFER')
                reference, counts = current, current_counts
            stripped[name] = transformed
        require(counts is not None, 'CANONICAL_CATALOG_REQUIRED')
        result = {}
        for name, data in stripped.items():
            text, kind = data.decode('utf-8'), self.shared[name]
            if kind == 'CATALOG':
                text = self.counters.patch_catalog(text, counts)
            elif kind == 'MODERN_HOME':
                text = self.patch_home(text, counts)
            elif kind == 'LEGACY_HOME':
                require('stage-card' not in text and 'outline-cta' not in text, 'LEGACY_HOME_SHAPE_CHANGED')
            else:
                raise RuntimeError('UNSUPPORTED_LIST_KIND')
            result[name] = text.encode('utf-8')
        return result

    def verify_local(self, plan, current):
        self.require_fence()
        lists = {name: current[name] for name in plan['lists']}
        if self.transform_lists(plan['car_code'], lists) != lists:
            return False
        for name in plan['sitemaps']:
            if retire_sitemap(current[name], plan['car_code']) != current[name]:
                return False
        # Unknown target aliases must not silently escape an admitted inventory.
        for folder in ('video', 'site'):
            for path in self._path(folder).iterdir():
                if not (path.suffix.lower() == '.html' and path.name.upper().startswith(plan['car_code'])):
                    continue
                if str(path.relative_to(self.public_root)) not in plan['direct']:
                    return False
        return True

    def observe_http(self, plan):
        def get(url):
            request = urllib.request.Request(url, headers={'Cache-Control': 'no-cache', 'User-Agent': 'UA-ART-deletion-verifier/1'})
            opener = urllib.request.build_opener(NoRedirect())
            try:
                response = opener.open(request, timeout=10)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                status, body, final = response.code, response.read(), response.geturl()
            return url, {'url': url, 'status': status, 'body_sha256': sha(body),
                         'redirected': final != url or 300 <= status < 400, 'observed_at': time.time()}
        with ThreadPoolExecutor(max_workers=6) as executor:
            return dict(executor.map(get, plan['routes']))


def create_coordinator(*, db, config_path=JOURNAL / 'runtime.json'):
    path = Path(config_path)
    require(path == JOURNAL / 'runtime.json' and path.resolve(strict=True) == path,
            'INSTALLED_RUNTIME_CONFIG_REQUIRED')
    config = json.loads(path.read_bytes())
    binding = LegacyBinding(db=db, counters=importlib.import_module('ua_site_counters'),
                            fence_module=importlib.import_module('publication_fence'), config=config)
    coordinator = Coordinator(binding, schema_sha256=config['application_schema_sha256'])
    # Readiness check only. Schema creation is a separate reviewed installer step.
    with binding.fence(), closing(binding.connect()) as conn, ImmediateTransaction(conn, binding.require_fence) as tx:
        coordinator.store._check(tx)
    return coordinator


def install_reviewed_schema(*, binding, backup_manifest_sha256):
    """Explicit installer-only entry; caller already verified its full backup.

    Never called by factory, import, Telegram or resume. This helper does not
    manufacture a backup receipt or approve the supplied schema digest.
    """
    require(re.fullmatch(r'[0-9a-f]{64}', str(backup_manifest_sha256)), 'VERIFIED_BACKUP_REFERENCE_REQUIRED')
    with binding.fence(), closing(binding.connect()) as conn, ImmediateTransaction(conn, binding.require_fence) as tx:
        install_additive_schema(tx, approved_application_schema_sha256=binding.config['application_schema_sha256'])
        tx.commit()
