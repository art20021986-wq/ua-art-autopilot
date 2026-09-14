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
from routing_proof import (SOURCE_BINDINGS, STATIC_MAPPING, PRODUCTION_LOCATION, WRAPPER_ROUTES,
                           validate_legacy_home_redirect, validate_unserved_site_prefix)
from viewport_harness import (FRAME_QUERY, HARNESS_ROUTE, VIEWPORTS, render as render_viewport,
                              specification as viewport_specification)


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

    def test_public_video_assets_are_independently_hash_bound(self):
        root = self.base/'video'
        root.mkdir()
        self.manifest['asset_roots']['video'] = str(root)
        for name in ('first.jpg','second.jpg'):
            raw=name.encode()
            (root/name).write_bytes(raw)
            self.manifest['files']['/video/'+name] = {'storage':'asset','root':'video','path':name,
                'sha256':sha(raw),'bytes':len(raw),'content_type':'image/jpeg'}
        app = self.app()
        self.assertEqual(self.call(app,'/video/first.jpg')['body'],b'first.jpg')
        self.assertEqual(self.call(app,'/video/second.jpg')['body'],b'second.jpg')
        (root/'second.jpg').write_bytes(b'changed')
        self.assertEqual(self.call(app,'/video/second.jpg')['status'],'503 Service Unavailable')
        self.assertEqual(self.call(app,'/video/first.jpg')['status'],'200 OK')

    def test_unserved_site_html_and_assets_cannot_be_injected_into_public_manifest(self):
        for route,mime in (('/site/UA-0017.html','text/html; charset=utf-8'),
                           ('/site/katalog.html','text/html; charset=utf-8'),
                           ('/site/info.html','text/html; charset=utf-8'),
                           ('/site/photo.jpg','image/jpeg')):
            item={'storage':'bundle','path':'public'+route,'sha256':sha(self.html),
                  'bytes':len(self.html),'content_type':mime}
            self.manifest['files'][route]=item
            with self.assertRaisesRegex(ValueError,'UNSERVED_SITE_RESOURCES_CANNOT_BE_PUBLIC'): self.app()
            self.manifest['files'].pop(route)
        self.assertEqual(self.call(self.app(),'/offline/site/UA-0017.html')['status'],'404 Not Found')

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

    def add_auxiliary(self, route='/video/info.html'):
        raw=b'<html><body>Unchanged public information</body></html>'
        write_new(self.bundle,'public'+route,raw)
        self.manifest['files'][route]={'storage':'bundle','path':'public'+route,'sha256':sha(raw),
            'bytes':len(raw),'content_type':'text/html; charset=utf-8','protection':'UNCHANGED_LINKED_PUBLIC_HTML',
            'source_binding':{'type':'CAPTURE','path':route[1:],'sha256':sha(raw)}}
        return raw

    def test_unchanged_navigation_page_requires_auth_and_retains_exact_bytes(self):
        raw=self.add_auxiliary()
        app=self.app()
        self.assertEqual(self.call(app,'/video/info.html',auth=False)['status'],'401 Unauthorized')
        response=self.call(app,'/video/info.html')
        self.assertEqual((response['status'],response['body']),('200 OK',raw))
        (self.bundle/'public/video/info.html').write_bytes(b'changed public information')
        self.assertEqual(self.call(app,'/video/info.html')['status'],'503 Service Unavailable')

    def test_unchanged_html_needs_exact_source_binding_and_reviewed_name(self):
        self.add_auxiliary()
        item=self.manifest['files']['/video/info.html']
        item['source_binding']['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'UNCHANGED_PUBLIC_HTML_SOURCE_PIN_REQUIRED'): self.app()
        item['source_binding']['sha256']=item['sha256']
        item['source_binding']['path']='video/private.html'
        with self.assertRaisesRegex(ValueError,'EXACT_UNCHANGED_PUBLIC_HTML_BINDING_REQUIRED'): self.app()
        self.manifest['files'].pop('/video/info.html')
        self.add_auxiliary('/video/private.html')
        with self.assertRaisesRegex(ValueError,'ONLY_REVIEWED_HTML_ROUTES_ALLOWED'): self.app()

    def test_diagnostic_requires_its_published_car(self):
        raw=self.add_auxiliary('/video/UA-0017-diag.html')
        with self.assertRaisesRegex(ValueError,'DIAGNOSTIC_REQUIRES_PUBLISHED_CARD'): self.app()
        write_new(self.bundle,'public/video/UA-0017.html',self.html)
        item=copy.deepcopy(self.manifest['files']['/video/index.html'])
        item['path']='public/video/UA-0017.html'
        self.manifest['files']['/video/UA-0017.html']=item
        self.assertEqual(self.call(self.app(),'/video/UA-0017-diag.html')['body'],raw)

    def legacy_redirect(self):
        return {'status':'302 Found','location':'/video/index.html','proof':{
            'source_sha256':dict(SOURCE_BINDINGS),'static_mappings':copy.deepcopy(STATIC_MAPPING),
            'production_location':PRODUCTION_LOCATION,'routing_evidence_sha256':'0'*64,
            'route':'/site/index.html','classification':'UNSERVED_LEGACY_USES_BASE_WSGI_REDIRECT'}}

    def site_prefix_proof(self):
        return {'contract':'UA-ART-OBSERVED-UNSERVED-SITE-PREFIX-1',
            'source_sha256':dict(SOURCE_BINDINGS),'static_mappings':copy.deepcopy(STATIC_MAPPING),
            'wrapper_routes':copy.deepcopy(WRAPPER_ROUTES),'production_location':PRODUCTION_LOCATION,
            'routing_evidence_sha256':'0'*64,'unserved_prefix':'/site/','served_prefix':'/video/',
            'classification':'OFFLINE_PROTECTED_SOURCE_ONLY'}

    def test_whole_site_prefix_exclusion_needs_its_own_exact_routing_proof(self):
        proof=self.site_prefix_proof()
        validate_unserved_site_prefix(proof)
        self.manifest['unserved_site_prefix_proof']=proof
        self.app()
        for field,value in (('unserved_prefix','/'),('served_prefix','/site/'),
                            ('static_mappings',STATIC_MAPPING+[{'url':'/site/','directory':'/home/Carix/site/'}]),
                            ('wrapper_routes',{'seo':['/site/']}),
                            ('source_sha256',{**SOURCE_BINDINGS,'observed_wsgi_config.py':'0'*64})):
            self.manifest['unserved_site_prefix_proof']={**self.site_prefix_proof(),field:value}
            with self.assertRaisesRegex(ValueError,'EXACT_UNSERVED_SITE_PREFIX_PROOF_REQUIRED'): self.app()
        self.manifest['unserved_site_prefix_proof']=self.legacy_redirect()['proof']
        with self.assertRaisesRegex(ValueError,'EXACT_UNSERVED_SITE_PREFIX_PROOF_REQUIRED'): self.app()

    def test_proven_legacy_home_redirect_is_authenticated_and_exact(self):
        self.manifest['redirects']={'/site/index.html':self.legacy_redirect()}
        app=self.app()
        self.assertEqual(self.call(app,'/site/index.html',auth=False)['status'],'401 Unauthorized')
        response=self.call(app,'/site/index.html')
        self.assertEqual((response['status'],response['headers']['Location']),('302 Found','/video/index.html'))
        self.assertEqual(self.call(app,'/site/unknown.html')['status'],'404 Not Found')
        self.assertEqual(self.call(app,'/site/index.html',REQUEST_METHOD='POST')['status'],'405 Method Not Allowed')

    def test_redirect_source_drift_open_redirect_and_broad_fallback_are_rejected(self):
        redirect=self.legacy_redirect()
        self.manifest['redirects']={'/site/index.html':redirect}
        redirect['proof']['source_sha256']['observed_wsgi_config.py']='0'*64
        with self.assertRaisesRegex(ValueError,'EXACT_LEGACY_HOME_REDIRECT_PROOF_REQUIRED'):self.app()
        redirect=self.legacy_redirect()
        self.manifest['redirects']={'/site/index.html':redirect}
        redirect['location']='https://other.example'
        with self.assertRaisesRegex(ValueError,'EXACT_LEGACY_HOME_REDIRECT_REQUIRED'):self.app()
        self.manifest['redirects']={'/site/*':self.legacy_redirect()}
        with self.assertRaisesRegex(ValueError,'ONLY_OBSERVED_LEGACY_HOME_REDIRECT_ALLOWED'):self.app()

    def add_viewport(self):
        raw = render_viewport(self.manifest['files'])
        write_new(self.bundle,'public'+HARNESS_ROUTE,raw)
        self.manifest['viewport_harness'] = viewport_specification(self.manifest['files'])
        self.manifest['files'][HARNESS_ROUTE] = {'storage':'bundle','path':'public'+HARNESS_ROUTE,
            'sha256':sha(raw),'bytes':len(raw),'content_type':'text/html; charset=utf-8',
            'protection':'AUTHENTICATED_VIEWPORT_HARNESS'}
        return raw

    def test_viewport_authentication_host_and_read_only_boundaries_apply_to_every_request(self):
        self.add_viewport()
        app=self.app()
        for route in (HARNESS_ROUTE,'/video/index.html','/private.json'):
            self.assertEqual(self.call(app,route,auth=False,QUERY_STRING=FRAME_QUERY)['status'],'401 Unauthorized')
            self.assertEqual(self.call(app,route,QUERY_STRING=FRAME_QUERY,REQUEST_METHOD='POST')['status'],'405 Method Not Allowed')
            self.assertEqual(self.call(app,route,QUERY_STRING=FRAME_QUERY,HTTP_HOST='production.example')['status'],'421 Misdirected Request')
        self.assertEqual(self.call(app,'/private.json',QUERY_STRING=FRAME_QUERY)['status'],'404 Not Found')

    def test_viewport_changes_only_opted_in_headers_and_preserves_candidate_bytes(self):
        self.add_viewport()
        app=self.app()
        for query in ('',FRAME_QUERY,FRAME_QUERY+'&other=1','__uaart_viewport=2','other=1'):
            result=self.call(app,QUERY_STRING=query)
            self.assertEqual((result['status'],result['body']),('200 OK',self.html))
            policy=result['headers']['Content-Security-Policy']
            if query==FRAME_QUERY:
                self.assertIn("frame-ancestors 'self'",policy)
                self.assertIn('sandbox allow-scripts allow-same-origin',policy)
                self.assertIn("frame-src 'none'",policy)
                for forbidden in ('allow-top-navigation','allow-popups','allow-forms','allow-downloads'):
                    self.assertNotIn(forbidden,policy)
            else:
                self.assertIn("frame-ancestors 'none'",policy)
                self.assertNotIn('sandbox',policy)
        head=self.call(app,QUERY_STRING=FRAME_QUERY,REQUEST_METHOD='HEAD')
        self.assertEqual(head['body'],b'')
        self.assertIn("frame-ancestors 'self'",head['headers']['Content-Security-Policy'])

    def test_viewport_parent_can_frame_only_manifest_document_paths(self):
        self.add_auxiliary()
        raw=self.add_viewport()
        app=self.app()
        result=self.call(app,HARNESS_ROUTE)
        self.assertEqual(result['body'],raw)
        directives={item.strip().split(' ',1)[0]:item.strip().split(' ',1)[1]
                    for item in result['headers']['Content-Security-Policy'].split(';')}
        self.assertEqual(directives['frame-src'],'https://preview.example/video/index.html https://preview.example/video/info.html')
        self.assertEqual(directives['frame-ancestors'],"'none'")
        self.assertEqual(directives['connect-src'],"'none'")
        self.assertEqual(directives['form-action'],"'none'")
        self.assertNotIn('fixture-only',raw.decode())
        self.assertNotIn(str(self.config_path),raw.decode())
        self.assertNotIn('password_hash_hex',raw.decode())
        self.assertEqual(self.manifest['viewport_harness']['acceptance'],'NOT_RUN')

    def test_viewport_query_cannot_frame_harness_assets_errors_or_unreviewed_documents(self):
        self.add_viewport()
        raw=b'body{color:black}'
        write_new(self.bundle,'public/video/test.css',raw)
        self.manifest['files']['/video/test.css']={'storage':'bundle','path':'public/video/test.css',
            'sha256':sha(raw),'bytes':len(raw),'content_type':'text/css; charset=utf-8'}
        app=self.app()
        for route in (HARNESS_ROUTE,'/video/test.css','/unknown.html','//video/index.html'):
            result=self.call(app,route,QUERY_STRING=FRAME_QUERY)
            self.assertIn("frame-ancestors 'none'",result['headers']['Content-Security-Policy'])
        (self.bundle/'public/video/index.html').write_bytes(b'CHANGED')
        result=self.call(app,QUERY_STRING=FRAME_QUERY)
        self.assertEqual(result['status'],'503 Service Unavailable')
        self.assertIn("frame-ancestors 'none'",result['headers']['Content-Security-Policy'])

    def test_viewport_canonical_template_and_exact_manifest_list_are_required(self):
        self.add_viewport()
        self.manifest['viewport_harness']['document_routes'].append('/private.html')
        with self.assertRaisesRegex(ValueError,'EXACT_VIEWPORT_MANIFEST_REQUIRED'): self.app()
        self.manifest['viewport_harness']=viewport_specification(self.manifest['files'])
        item=self.manifest['files'][HARNESS_ROUTE]
        changed=b'<html><script>fetch("/private.json")</script></html>'
        (self.bundle/item['path']).write_bytes(changed)
        item.update(sha256=sha(changed),bytes=len(changed))
        with self.assertRaisesRegex(ValueError,'CANONICAL_PINNED_VIEWPORT_HARNESS_REQUIRED'): self.app()

    def test_viewport_optional_compatibility_never_accepts_half_registered_harness(self):
        self.add_viewport()
        descriptor=self.manifest.pop('viewport_harness')
        with self.assertRaisesRegex(ValueError,'EXACT_VIEWPORT_MANIFEST_REQUIRED'): self.app()
        self.manifest['viewport_harness']=descriptor
        self.manifest['files'].pop(HARNESS_ROUTE)
        with self.assertRaisesRegex(ValueError,'EXACT_VIEWPORT_MANIFEST_REQUIRED'): self.app()

    def test_viewport_file_drift_and_symlink_do_not_serve_tampered_wrapper(self):
        self.add_viewport()
        app=self.app()
        path=self.bundle/('public'+HARNESS_ROUTE)
        path.write_bytes(b'UNREVIEWED SCRIPT')
        self.assertEqual(self.call(app,HARNESS_ROUTE)['status'],'503 Service Unavailable')
        path.unlink()
        target=self.base/'private.js'
        target.write_bytes(b'PRIVATE')
        path.symlink_to(target)
        self.assertEqual(self.call(app,HARNESS_ROUTE)['status'],'503 Service Unavailable')


class BuilderBoundaryTest(unittest.TestCase):
    def test_viewport_builder_rejects_noncanonical_or_nonpublic_sources(self):
        home={'storage':'bundle','sha256':'0'*64,'content_type':'text/html; charset=utf-8'}
        for route in ('https://other.example/video/index.html','//other.example/video/index.html',
                      '/video/index.html?target=evil','/video/../private.html','/private.html','/site/index.html'):
            with self.assertRaisesRegex(ValueError,'VIEWPORT_REQUIRES_EXACT_PINNED_PUBLIC_DOCUMENTS'):
                render_viewport({'/video/index.html':home,route:home})
        with self.assertRaisesRegex(ValueError,'VIEWPORT_REQUIRES_PINNED_HOME'):
            render_viewport({})

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

    def test_link_discovery_does_not_mix_navigation_with_asset_dependencies(self):
        refs=References('<a href="info.html">Info</a><a href="UA-0017-diag.html">Diagnostic</a><img src="photo.jpg">')
        self.assertEqual(refs.links,{'info.html','UA-0017-diag.html'})
        self.assertEqual(refs.references,{'photo.jpg'})



if __name__=='__main__': unittest.main()
