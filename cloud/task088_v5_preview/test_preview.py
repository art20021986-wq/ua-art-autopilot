"""Preview boundary tests. Passing these is not browser or Production acceptance."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from common import CONTRACT, MAX_FILE_BYTES, encoded, read, relative, sha, write_new
from build_preview import References, build, css_references
from wsgi_preview import Preview


class PreviewBoundaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Fixed, isolated test verifier: never provisioned or deployed.
        cls.test_auth = {'username':'test-only','salt_hex':'01' * 16,'iterations':300000,
                        'password_hash_hex':hashlib.pbkdf2_hmac('sha256',b'fixture-only',bytes.fromhex('01'*16),300000).hex()}
        cls.header = 'Basic ' + base64.b64encode(b'test-only:fixture-only').decode()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.bundle = self.base / 'bundle'
        self.bundle.mkdir(mode=0o700)
        self.html = b'<html><body>Isolated fixture</body></html>'
        write_new(self.bundle,'public/video/index.html',self.html)
        self.manifest = {'contract':CONTRACT,'source_origin':'https://production.example',
                         'asset_roots':{},'preview_gate':'NOT_PASSED',
                         'files':{'/video/index.html':{'storage':'bundle','path':'public/video/index.html',
                                  'sha256':sha(self.html),'bytes':len(self.html),'content_type':'text/html; charset=utf-8'}}}
        self.config = {'contract':CONTRACT,'preview_origin':'https://preview.example',
                       'bundle_root':str(self.bundle),'basic_auth':copy.deepcopy(self.test_auth),
                       'manifest_sha256':''}
        self.config_path = self.base / 'private.json'

    def app(self):
        raw = encoded(self.manifest)
        (self.bundle / 'manifest.json').write_bytes(raw)
        self.config['manifest_sha256'] = sha(raw)
        self.config_path.write_bytes(encoded(self.config))
        self.config_path.chmod(0o600)
        return Preview(self.config_path)

    def call(self,app,path='/video/index.html',auth=True,**overrides):
        environ = {'wsgi.url_scheme':'https','HTTP_HOST':'preview.example',
                   'REQUEST_METHOD':'GET','PATH_INFO':path}
        if auth: environ['HTTP_AUTHORIZATION'] = self.header
        environ.update(overrides)
        response = {}
        def start(status,headers): response.update(status=status,headers=dict(headers))
        response['body'] = b''.join(app(environ,start))
        return response

    def test_all_routes_require_authentication(self):
        app = self.app()
        for path in ('/','/video/index.html','/private.json','/ua/a.js','/uaart-bridge'):
            self.assertEqual(self.call(app,path,auth=False)['status'],'401 Unauthorized')

    def test_unknown_credentials_and_malformed_headers_fail_closed(self):
        app = self.app()
        for header in ('Basic invalid','Bearer x','Basic '+base64.b64encode(b'test-only:wrong').decode(),
                       'Basic '+base64.b64encode(b'wrong:fixture-only').decode(),'Basic '+'A'*2049):
            self.assertEqual(self.call(app,HTTP_AUTHORIZATION=header)['status'],'401 Unauthorized')

    def test_https_exact_host_and_separate_origin_required(self):
        app = self.app()
        for override in ({'wsgi.url_scheme':'http'},{'HTTP_HOST':'production.example'},{'HTTP_HOST':'preview.example.evil'}):
            self.assertEqual(self.call(app,**override)['status'],'421 Misdirected Request')
        self.config['preview_origin'] = self.manifest['source_origin']
        with self.assertRaisesRegex(ValueError,'DEDICATED_PREVIEW_ORIGIN_REQUIRED'): self.app()

    def test_reads_exact_manifest_bytes_and_head_has_no_body(self):
        app = self.app()
        get = self.call(app)
        self.assertEqual((get['status'],get['body']),('200 OK',self.html))
        head = self.call(app,REQUEST_METHOD='HEAD')
        self.assertEqual(head['body'],b'')
        self.assertEqual(head['headers']['Content-Length'],str(len(self.html)))
        self.assertEqual(self.call(app,'/')['headers']['Location'],'/video/index.html')

    def test_no_cache_indexing_framing_or_network_writes(self):
        headers = self.call(self.app())['headers']
        self.assertEqual(headers['Cache-Control'],'private, no-store')
        self.assertIn('noindex',headers['X-Robots-Tag'])
        for directive in ("connect-src 'none'","form-action 'none'","frame-ancestors 'none'","object-src 'none'"):
            self.assertIn(directive,headers['Content-Security-Policy'])

    def test_write_methods_are_unavailable_even_when_authenticated(self):
        app = self.app()
        for method in ('POST','PUT','DELETE','PATCH','OPTIONS','CONNECT','TRACE'):
            self.assertEqual(self.call(app,REQUEST_METHOD=method)['status'],'405 Method Not Allowed')

    def test_no_source_db_config_directory_or_traversal_fallback(self):
        app = self.app()
        for path in ('/db.py','/cars.db','/private.json','/manifest.json','/public/',
                     '/video/../private.json','/video/%2e%2e/private.json','//video/index.html',
                     '/ua/a.js','/ua/a/e','/uaart-bridge','/site/index.html'):
            self.assertEqual(self.call(app,path)['status'],'404 Not Found')

    def test_file_drift_fails_without_returning_new_bytes(self):
        app = self.app()
        (self.bundle/'public/video/index.html').write_bytes(b'SECRET CHANGED BY OTHER WRITER')
        response = self.call(app)
        self.assertEqual(response['status'],'503 Service Unavailable')
        self.assertNotIn(b'SECRET',response['body'])

    def test_deleted_and_symlinked_resources_fail(self):
        app = self.app()
        path = self.bundle/'public/video/index.html'
        path.unlink()
        self.assertEqual(self.call(app)['status'],'503 Service Unavailable')
        target = self.base/'private_source.py'
        target.write_bytes(self.html)
        path.symlink_to(target)
        self.assertEqual(self.call(app)['status'],'503 Service Unavailable')

    def test_manifest_pin_and_private_config_mode_are_enforced(self):
        self.app()
        (self.bundle/'manifest.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError,'PINNED_PREVIEW_MANIFEST_REQUIRED'): Preview(self.config_path)
        self.app()
        self.config_path.chmod(0o644)
        with self.assertRaisesRegex(ValueError,'PRIVATE_CONFIG_MODE_REQUIRED'): Preview(self.config_path)

    def test_manifest_cannot_expose_private_or_unknown_html(self):
        original = copy.deepcopy(self.manifest['files'])
        for route in ('/db.py','/config.json','/video/private.html','/site/index.html'):
            item = copy.deepcopy(original['/video/index.html'])
            item['path'] = 'public'+route
            self.manifest['files'] = {route:item}
            with self.assertRaises(ValueError): self.app()

    def test_explicit_asset_roots_are_separate_and_hash_bound(self):
        for prefix in ('video','site'):
            root = self.base/prefix
            root.mkdir()
            raw = (prefix+' media').encode()
            (root/'photo.jpg').write_bytes(raw)
            self.manifest['asset_roots'][prefix] = str(root)
            self.manifest['files']['/'+prefix+'/photo.jpg'] = {'storage':'asset','root':prefix,'path':'photo.jpg',
                'sha256':sha(raw),'bytes':len(raw),'content_type':'image/jpeg'}
        app = self.app()
        self.assertEqual(self.call(app,'/video/photo.jpg')['body'],b'video media')
        self.assertEqual(self.call(app,'/site/photo.jpg')['body'],b'site media')
        (self.base/'site/photo.jpg').write_bytes(b'changed')
        self.assertEqual(self.call(app,'/site/photo.jpg')['status'],'503 Service Unavailable')
        self.assertEqual(self.call(app,'/video/photo.jpg')['status'],'200 OK')

    def test_arbitrary_asset_root_and_mapping_are_rejected(self):
        self.manifest['asset_roots'] = {'home':str(self.base)}
        with self.assertRaisesRegex(ValueError,'EXPLICIT_PUBLIC_ASSET_ROOTS_REQUIRED'): self.app()
        self.manifest['asset_roots'] = {'video':str(self.base)}
        self.manifest['files']['/video/photo.jpg'] = {'storage':'asset','root':'video','path':'private/photo.jpg',
            'sha256':'0'*64,'bytes':1,'content_type':'image/jpeg'}
        with self.assertRaisesRegex(ValueError,'EXACT_PUBLIC_ASSET_MAPPING_REQUIRED'): self.app()

    def test_resource_limits_and_invalid_verifier_are_rejected(self):
        self.manifest['files']['/video/index.html']['bytes'] = MAX_FILE_BYTES+1
        with self.assertRaisesRegex(ValueError,'PINNED_PUBLIC_BYTES_REQUIRED'): self.app()
        self.manifest['files']['/video/index.html']['bytes'] = len(self.html)
        self.config['basic_auth']['salt_hex'] = '1'*33
        with self.assertRaisesRegex(ValueError,'PROVISIONED_AUTH_VERIFIER_REQUIRED'): self.app()


class BuilderBoundaryTest(unittest.TestCase):
    def test_exact_relative_paths(self):
        for value in ('../x','/x','a//b','a/./b','a\\b','a/%2e%2e/x','a\0b',''):
            with self.assertRaises(ValueError): relative(value)
        self.assertEqual(relative('video/foto/picture.jpg'),'video/foto/picture.jpg')

    def test_nested_symlink_read_and_existing_file_write_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            write_new(root,'safe/file.css',b'one')
            with self.assertRaises(FileExistsError): write_new(root,'safe/file.css',b'two')
            (root/'alias').symlink_to(root/'safe',target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'SYMLINK'): read(root,'alias/file.css')
            with self.assertRaisesRegex(ValueError,'SYMLINK'): write_new(root,'alias/other.css',b'no')
            self.assertFalse((root/'safe/other.css').exists())

    def test_output_alias_cannot_write_inside_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            snapshot=root/'capture'
            snapshot.mkdir()
            (root/'alias').symlink_to(snapshot,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'OUTPUT_MUST_BE_SEPARATE_FROM_INPUTS'):
                build(snapshot,root/'alias/new','https://production.example',root/'unused.json')
            self.assertFalse((snapshot/'new').exists())

    def test_static_dependency_scanner_covers_css_and_srcset(self):
        source='''<style>@import "theme.css";body{background:url('hero.jpg')}</style>
        <div style="background:url(tile.webp)"></div><img src="photo.jpg" srcset="small.jpg 1x, large.jpg 2x">
        <link rel="alternate stylesheet" href="screen.css"><script src="lang.js"></script>'''
        self.assertEqual(References(source).references,{'theme.css','hero.jpg','tile.webp','photo.jpg',
            'small.jpg','large.jpg','screen.css','lang.js'})



if __name__=='__main__': unittest.main()
