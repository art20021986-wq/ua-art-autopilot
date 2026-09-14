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
            extension = Path(route_relative).suffix.lower()
            mime = item.get('content_type')
            if extension == '.html':
                if (not re.fullmatch(r'(video|site)/(UA-[0-9]{4,}|katalog)\.html',route_relative)
                        and route_relative != 'video/index.html'):
                    raise ValueError('ONLY_GENERATED_HTML_ROUTES_ALLOWED')
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
                  ('X-Robots-Tag','noindex, nofollow, noarchive'),('Referrer-Policy','no-referrer'),
                  ('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; "
                   "style-src 'self' 'unsafe-inline'; img-src 'self' data: " + self.public_origin +
                   "; media-src 'self' " + self.public_origin + "; font-src 'self' data:; connect-src 'none'; "
                   "object-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'")]
        def response(status,body=b'',extra=(),mime='text/plain; charset=utf-8'):
            start_response(status,common+[('Content-Type',mime),('Content-Length',str(len(body)))]+list(extra))
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
        item = self.files.get(path)
        if item is None:
            return response('404 Not Found',b'Not a preview resource.')
        try:
            root = self.root if item['storage']=='bundle' else self.asset_roots[item['root']]
            raw = read(root,item['path'])
            if len(raw) != item['bytes'] or not hmac.compare_digest(sha(raw),item['sha256']):
                raise ValueError('PREVIEW_RESOURCE_DRIFT')
            return response('200 OK',raw,mime=item['content_type'])
        except (OSError,ValueError):
            return response('503 Service Unavailable',b'Preview resource verification failed.')


def application_from_environment():
    # No host, path, password or production application is guessed here.
    return Preview(os.environ['UA_ART_PREVIEW_CONFIG'])
