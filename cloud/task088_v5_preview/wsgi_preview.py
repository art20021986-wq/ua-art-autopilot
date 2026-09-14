"""Dedicated authenticated, read-only HTTPS Preview app. No production app imports.

No credentials are generated, selected or activated. The deployer must supply a
private configuration, a separately approved origin and an externally provisioned
Basic-auth verifier. Every response is manifest-bound; there is no directory or
filesystem fallback, API, upload, analytics endpoint or write method.
"""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from common import ASSET_TYPES, CONTRACT, MAX_FILE_BYTES, read, relative, sha
from routing_proof import validate_legacy_home_redirect, validate_unserved_site_prefix
from viewport_harness import (FRAME_QUERY, HARNESS_ROUTE, HTML_MIME,
                              render as render_viewport, specification as viewport_specification)


def origin(value):
    if type(value) is not str or not re.fullmatch(r'https://[A-Za-z0-9][A-Za-z0-9.-]*(?::[0-9]{1,5})?',value):
        raise ValueError('EXPLICIT_HTTPS_ORIGIN_REQUIRED')
    return urlsplit(value)


class Preview:
    def __init__(self, config_path):
        config_path = Path(config_path).absolute()
        config = json.loads(read(config_path.parent, config_path.name, private=True))
        if set(config) != {'contract','preview_origin','bundle_root','manifest_sha256','basic_auth'} or config['contract'] != CONTRACT:
            raise ValueError('EXACT_PRIVATE_PREVIEW_CONFIG_REQUIRED')
        self.origin = origin(config['preview_origin'])
        self.root = Path(config['bundle_root'])
        if not self.root.is_absolute() or self.root.is_symlink():
            raise ValueError('ABSOLUTE_PRIVATE_BUNDLE_REQUIRED')
        raw = read(self.root,'manifest.json')
        if not hmac.compare_digest(sha(raw),config['manifest_sha256']):
            raise ValueError('PINNED_PREVIEW_MANIFEST_REQUIRED')
        manifest = json.loads(raw)
        if manifest.get('contract') != CONTRACT or manifest.get('preview_gate') != 'NOT_PASSED':
            raise ValueError('UNACCEPTED_PREVIEW_BUILD_REQUIRED')
        public_origin = origin(manifest['source_origin'])
        if self.origin.geturl() == public_origin.geturl():
            raise ValueError('DEDICATED_PREVIEW_ORIGIN_REQUIRED')
        self.public_origin = public_origin.geturl()
        asset_roots = manifest.get('asset_roots')
        if type(asset_roots) is not dict or set(asset_roots) - {'video','site'}:
            raise ValueError('EXPLICIT_PUBLIC_ASSET_ROOTS_REQUIRED')
        self.asset_roots = {}
        for prefix, value in asset_roots.items():
            root = Path(value)
            if not root.is_absolute() or root.is_symlink():
                raise ValueError('EXPLICIT_PUBLIC_ASSET_ROOT_REQUIRED')
            self.asset_roots[prefix] = root
        self.files = manifest['files']
        if type(self.files) is not dict or not self.files:
            raise ValueError('EXPLICIT_FILE_MANIFEST_REQUIRED')
        for route,item in self.files.items():
            if type(route) is not str or not route.startswith('/'):
                raise ValueError('EXACT_ROUTE_REQUIRED')
            route_relative = relative(route[1:])
            if route_relative.startswith('site/'):
                raise ValueError('UNSERVED_SITE_RESOURCES_CANNOT_BE_PUBLIC')
            extension = Path(route_relative).suffix.lower()
            mime = item.get('content_type')
            if extension == '.html':
                if route == HARNESS_ROUTE:
                    if (set(item) != {'storage','path','sha256','bytes','content_type','protection'}
                            or item.get('protection') != 'AUTHENTICATED_VIEWPORT_HARNESS'):
                        raise ValueError('EXACT_VIEWPORT_HARNESS_ITEM_REQUIRED')
                elif (not re.fullmatch(r'video/(UA-[0-9]{4,}|katalog)\.html',route_relative)
                        and route_relative != 'video/index.html'):
                    auxiliary = re.fullmatch(r'(video)/(info|podbor|UA-[0-9]{4,}-diag)\.html',route_relative)
                    if not auxiliary or item.get('protection') != 'UNCHANGED_LINKED_PUBLIC_HTML':
                        raise ValueError('ONLY_REVIEWED_HTML_ROUTES_ALLOWED')
                    if auxiliary[2].endswith('-diag') and '/'+auxiliary[1]+'/'+auxiliary[2][:-5]+'.html' not in self.files:
                        raise ValueError('DIAGNOSTIC_REQUIRES_PUBLISHED_CARD')
                    binding = item.get('source_binding',{})
                    if type(binding) is not dict or binding.get('sha256') != item.get('sha256'):
                        raise ValueError('UNCHANGED_PUBLIC_HTML_SOURCE_PIN_REQUIRED')
                    if binding.get('type') == 'CAPTURE':
                        valid_binding = set(binding)=={'type','path','sha256'} and binding.get('path')==route_relative
                    elif binding.get('type') == 'EXPLICIT_PUBLIC_ROOT':
                        valid_binding = (set(binding)=={'type','root','path','sha256'}
                            and binding.get('root')==auxiliary[1] and auxiliary[1] in self.asset_roots
                            and binding.get('path')==route_relative.split('/',1)[1])
                    else: valid_binding = False
                    if not valid_binding: raise ValueError('EXACT_UNCHANGED_PUBLIC_HTML_BINDING_REQUIRED')
                if mime != 'text/html; charset=utf-8' or item.get('storage') != 'bundle':
                    raise ValueError('GENERATED_HTML_MANIFEST_REQUIRED')
            elif ASSET_TYPES.get(extension) != mime:
                raise ValueError('PUBLIC_ASSET_TYPE_REQUIRED')
            relative(item['path'])
            if item.get('storage') == 'bundle':
                if item['path'] != 'public/' + route_relative:
                    raise ValueError('EXACT_BUNDLE_ROUTE_MAPPING_REQUIRED')
            elif item.get('storage') == 'asset':
                prefix = item.get('root')
                if prefix not in self.asset_roots or route_relative != prefix + '/' + item['path'] or extension == '.html':
                    raise ValueError('EXACT_PUBLIC_ASSET_MAPPING_REQUIRED')
            else:
                raise ValueError('UNKNOWN_PREVIEW_STORAGE')
            if (not re.fullmatch(r'[0-9a-f]{64}',item.get('sha256','')) or type(item.get('bytes')) is not int
                    or not 0 <= item['bytes'] <= MAX_FILE_BYTES):
                raise ValueError('PINNED_PUBLIC_BYTES_REQUIRED')
        self.viewport_documents = set()
        viewport = manifest.get('viewport_harness')
        if viewport is not None or HARNESS_ROUTE in self.files:
            expected = viewport_specification(self.files)
            item = self.files.get(HARNESS_ROUTE)
            if viewport != expected or item is None:
                raise ValueError('EXACT_VIEWPORT_MANIFEST_REQUIRED')
            expected_html = render_viewport(self.files)
            if (item['sha256'] != sha(expected_html) or item['bytes'] != len(expected_html)
                    or read(self.root,item['path']) != expected_html):
                raise ValueError('CANONICAL_PINNED_VIEWPORT_HARNESS_REQUIRED')
            self.viewport_documents = set(expected['document_routes'])
        if 'unserved_site_prefix_proof' in manifest:
            validate_unserved_site_prefix(manifest['unserved_site_prefix_proof'])
        self.redirects = manifest.get('redirects',{})
        if type(self.redirects) is not dict or set(self.redirects)-{'/site/index.html'}:
            raise ValueError('ONLY_OBSERVED_LEGACY_HOME_REDIRECT_ALLOWED')
        for route,redirect in self.redirects.items():
            if (type(redirect) is not dict or set(redirect)!={'status','location','proof'}
                    or redirect['status']!='302 Found' or redirect['location']!='/video/index.html'
                    or redirect['location'] not in self.files or route in self.files):
                raise ValueError('EXACT_LEGACY_HOME_REDIRECT_REQUIRED')
            validate_legacy_home_redirect(redirect['proof'])
        auth = config['basic_auth']
        if set(auth) != {'username','salt_hex','iterations','password_hash_hex'}:
            raise ValueError('PROVISIONED_AUTH_VERIFIER_REQUIRED')
        if type(auth['username']) is not str or not auth['username'] or ':' in auth['username']:
            raise ValueError('EXPLICIT_AUTH_PRINCIPAL_REQUIRED')
        if type(auth['iterations']) is not int or not 300000 <= auth['iterations'] <= 2000000:
            raise ValueError('STRONG_AUTH_VERIFIER_REQUIRED')
        if not re.fullmatch(r'[0-9a-f]{32,128}',auth['salt_hex']) or not re.fullmatch(r'[0-9a-f]{64}',auth['password_hash_hex']):
            raise ValueError('PROVISIONED_AUTH_VERIFIER_REQUIRED')
        if len(auth['salt_hex']) % 2:
            raise ValueError('PROVISIONED_AUTH_VERIFIER_REQUIRED')
        self.auth = auth
        self.cached_valid_header = None

    def authenticated(self, header):
        if type(header) is not str or not header.startswith('Basic ') or len(header) > 2048:
            return False
        header_hash = hashlib.sha256(header.encode()).digest()
        if self.cached_valid_header is not None and hmac.compare_digest(header_hash,self.cached_valid_header):
            return True
        try:
            decoded = base64.b64decode(header[6:],validate=True).decode('utf-8')
            username,password = decoded.split(':',1)
            if not hmac.compare_digest(username.encode(),self.auth['username'].encode()):
                return False
            derived = hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(self.auth['salt_hex']),self.auth['iterations']).hex()
            valid = hmac.compare_digest(derived,self.auth['password_hash_hex'])
            if valid: self.cached_valid_header = header_hash
            return valid
        except (ValueError,UnicodeError):
            return False

    def __call__(self,environ,start_response):
        common = [('Cache-Control','private, no-store'),('X-Content-Type-Options','nosniff'),
                  ('X-Robots-Tag','noindex, nofollow, noarchive'),('Referrer-Policy','no-referrer')]
        normal_policy = ("default-src 'self'; script-src 'self' 'unsafe-inline'; "
                   "style-src 'self' 'unsafe-inline'; img-src 'self' data: " + self.public_origin +
                   "; media-src 'self' " + self.public_origin + "; font-src 'self' data:; connect-src 'none'; "
                   "object-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'")
        def response(status,body=b'',extra=(),mime='text/plain; charset=utf-8',policy=None):
            start_response(status,common+[('Content-Security-Policy',policy or normal_policy),
                ('Content-Type',mime),('Content-Length',str(len(body)))]+list(extra))
            return [] if environ.get('REQUEST_METHOD') == 'HEAD' else [body]
        if environ.get('wsgi.url_scheme') != 'https' or environ.get('HTTP_HOST') != self.origin.netloc:
            return response('421 Misdirected Request',b'Protected HTTPS preview required.')
        if not self.authenticated(environ.get('HTTP_AUTHORIZATION','')):
            return response('401 Unauthorized',b'Authentication required.',
                            [('WWW-Authenticate','Basic realm="UA ART protected preview", charset="UTF-8"')])
        if environ.get('REQUEST_METHOD') not in ('GET','HEAD'):
            return response('405 Method Not Allowed',b'Read-only preview.',[('Allow','GET, HEAD')])
        path = environ.get('PATH_INFO','')
        if path == '/':
            return response('302 Found',extra=[('Location','/video/index.html')])
        if path in self.redirects:
            redirect = self.redirects[path]
            return response(redirect['status'],extra=[('Location',redirect['location'])])
        item = self.files.get(path)
        if item is None:
            return response('404 Not Found',b'Not a preview resource.')
        try:
            root = self.root if item['storage']=='bundle' else self.asset_roots[item['root']]
            raw = read(root,item['path'])
            if len(raw) != item['bytes'] or not hmac.compare_digest(sha(raw),item['sha256']):
                raise ValueError('PREVIEW_RESOURCE_DRIFT')
            policy = None
            if path == HARNESS_ROUTE:
                # Explicit paths only. No wildcard, external frame, query-driven
                # source, arbitrary URL proxy, credential or new write endpoint.
                frame_sources = ' '.join(self.origin.geturl()+route for route in sorted(self.viewport_documents))
                policy = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                          "frame-src " + frame_sources + "; connect-src 'none'; object-src 'none'; "
                          "form-action 'none'; base-uri 'none'; frame-ancestors 'none'")
            elif path in self.viewport_documents and environ.get('QUERY_STRING','') == FRAME_QUERY:
                # HTTP sandbox cannot be removed by a same-origin child script.
                # Ordinary top-level candidate URLs keep their existing policy.
                # Relative navigation loses the opt-in query and cannot frame;
                # link/native-action acceptance therefore uses top-level pages.
                policy = normal_policy.replace("frame-ancestors 'none'","frame-ancestors 'self'")
                policy += "; frame-src 'none'; sandbox allow-scripts allow-same-origin"
            return response('200 OK',raw,mime=item['content_type'],policy=policy)
        except (OSError,ValueError):
            return response('503 Service Unavailable',b'Preview resource verification failed.')


def application_from_environment():
    # No host, path, password or production application is guessed here.
    return Preview(os.environ['UA_ART_PREVIEW_CONFIG'])
