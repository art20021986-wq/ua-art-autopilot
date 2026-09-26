"""Mandatory private Preview check; never counted by public software CI."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from build_preview import build
from common import sha
from viewport_harness import HARNESS_ROUTE


class PrivatePreviewCaptureTest(unittest.TestCase):
    def test_current_capture_generates_only_public_candidate_and_honest_gate(self):
        snapshot = Path(os.environ['UA088_LIVE_SOURCE_DIR'])
        route = Path(__file__).resolve().parents[1]/'task088_v5_acceptance/route_observations.json'
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'new'
            result=build(snapshot,output,'https://www.uaart.com.ua',route)
            provenance=json.loads((output/'provenance.json').read_text())
            manifest=json.loads((output/'manifest.json').read_text())
            captured=json.loads((snapshot/'capture_manifest.json').read_text())
            self.assertEqual(result['pages'],captured['published_count']*2+3)
            self.assertEqual(result['served_pages'],captured['published_count']+2)
            self.assertEqual(result['offline_protected_pages'],captured['published_count']+1)
            self.assertEqual(result['browser_checks'],(captured['published_count']+2)*6)
            self.assertEqual(result['preview_gate'],'NOT_PASSED')
            self.assertFalse(result['activated'])
            self.assertFalse(provenance['browser_run'])
            self.assertFalse(provenance['production_written'])
            self.assertTrue(all(page['outside_price_unchanged'] for page in provenance['pages']))
            self.assertTrue(all(check['status']=='NOT_RUN' for page in provenance['matrix'] for check in page['browser']))
            rows=json.loads((snapshot/'published_price_rows.json').read_text())
            served={'/video/index.html','/video/katalog.html',*('/video/'+row['auto_number']+'.html' for row in rows)}
            self.assertEqual({page['path'] for page in provenance['matrix']},served)
            for page in provenance['matrix']:
                self.assertEqual({(check['language'],check['viewport']) for check in page['browser']},
                    {(lang,size) for lang in ('RU','UA','GE') for size in ('desktop','mobile')})
            self.assertEqual(len(provenance['pages']),captured['published_count']*2+3)
            offline=[page for page in provenance['pages'] if page['classification']=='OFFLINE_PROTECTED_ARTIFACT']
            self.assertEqual(len(offline),captured['published_count']+1)
            for page in offline:
                self.assertTrue(page['candidate_path'].startswith('offline/site/'))
                self.assertEqual(sha((output/page['candidate_path']).read_bytes()),page['after_sha256'])
                self.assertEqual(sha((snapshot/page['path'][1:]).read_bytes()),page['before_sha256'])
                self.assertNotIn(page['path'],manifest['files'])
                self.assertNotIn(page['path'],manifest['viewport_harness']['document_routes'])
                self.assertTrue(page['outside_price_unchanged'])
            self.assertEqual((output/'public/video/index.html').read_bytes(),(snapshot/'video/index.html').read_bytes())
            self.assertNotIn('/site/index.html',manifest['files'])
            self.assertEqual(manifest['redirects']['/site/index.html']['location'],'/video/index.html')
            self.assertEqual(len(provenance['missing_linked_html']),20)
            self.assertEqual(provenance['linked_public_html'],[])
            self.assertEqual(manifest['provenance_sha256'],sha((output/'provenance.json').read_bytes()))
            self.assertFalse(any(path.suffix in ('.py','.db','.sqlite') for path in output.rglob('*')))
            self.assertIn(HARNESS_ROUTE,manifest['files'])
            self.assertEqual(set(manifest['viewport_harness']['document_routes']),served)
            self.assertEqual(manifest['viewport_harness']['acceptance'],'NOT_RUN')
            self.assertEqual(manifest['unserved_site_prefix_proof']['unserved_prefix'],'/site/')
            self.assertFalse((output/'public/site').exists())
            self.assertEqual(output.stat().st_mode & 0o777,0o700)
            with self.assertRaisesRegex(ValueError,'NEW_PRIVATE_OUTPUT_DIRECTORY_REQUIRED'):
                build(snapshot,output,'https://www.uaart.com.ua',route)

    def test_explicit_public_roots_copy_only_reviewed_linked_html_and_pin_new_assets(self):
        snapshot=Path(os.environ['UA088_LIVE_SOURCE_DIR'])
        route=Path(__file__).resolve().parents[1]/'task088_v5_acceptance/route_observations.json'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            public=root/'video'
            public.mkdir()
            # Isolated fixtures exercise dependency handling. They do not claim
            # these are the real, not-yet-captured Production auxiliary pages.
            info=b'<html><body><a href="private.html">Denied</a><a href="podbor.html">Selection</a><img src="aux-photo.jpg"></body></html>'
            diagnostic=b'<html><body>Diagnostic fixture</body></html>'
            (public/'info.html').write_bytes(info)
            (public/'podbor.html').write_bytes(b'<html>Selection fixture</html>')
            (public/'UA-0017-diag.html').write_bytes(diagnostic)
            (public/'private.html').write_bytes(b'PRIVATE SOURCE MUST NOT BE COPIED')
            (public/'aux-photo.jpg').write_bytes(b'fixture-media')
            result=build(snapshot,root/'output','https://www.uaart.com.ua',route,public)
            output=root/'output'
            manifest=json.loads((output/'manifest.json').read_text())
            provenance=json.loads((output/'provenance.json').read_text())
            self.assertEqual(result['unchanged_linked_pages'],3)
            self.assertEqual((output/'public/video/info.html').read_bytes(),info)
            self.assertEqual((output/'public/video/UA-0017-diag.html').read_bytes(),diagnostic)
            self.assertEqual(manifest['files']['/video/info.html']['source_binding'],{
                'type':'EXPLICIT_PUBLIC_ROOT','root':'video','path':'info.html','sha256':sha(info)})
            self.assertEqual(manifest['files']['/video/aux-photo.jpg']['sha256'],sha(b'fixture-media'))
            self.assertNotIn('/video/private.html',manifest['files'])
            self.assertFalse((output/'public/video/private.html').exists())
            self.assertTrue(any(item['path']=='/video/private.html' and item['reason']=='UNREVIEWED_LINKED_HTML_ROUTE'
                                for item in provenance['missing_linked_html']))
            self.assertEqual(result['preview_gate'],'NOT_PASSED')

    def test_live_linked_page_drift_before_output_prevents_build(self):
        from unittest.mock import patch
        import build_preview
        snapshot=Path(os.environ['UA088_LIVE_SOURCE_DIR'])
        route=Path(__file__).resolve().parents[1]/'task088_v5_acceptance/route_observations.json'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            public=root/'video'
            public.mkdir()
            target=public/'info.html'
            target.write_bytes(b'<html>original</html>')
            real_read=build_preview.read
            reads=0
            def drifting_read(read_root,name,**kwargs):
                nonlocal reads
                if Path(read_root)==public and name=='info.html':
                    reads+=1
                    if reads==2: target.write_bytes(b'<html>changed during build</html>')
                return real_read(read_root,name,**kwargs)
            with patch.object(build_preview,'read',drifting_read):
                with self.assertRaisesRegex(ValueError,'UNCHANGED_PUBLIC_HTML_SOURCE_CHANGED_DURING_BUILD'):
                    build(snapshot,root/'output','https://www.uaart.com.ua',route,public)
            self.assertFalse((root/'output').exists())

    def test_offline_dependencies_are_excluded_but_served_site_reference_remains_a_failure(self):
        snapshot=Path(os.environ['UA088_LIVE_SOURCE_DIR'])
        route=Path(__file__).resolve().parents[1]/'task088_v5_acceptance/route_observations.json'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            capture=root/'capture'
            shutil.copytree(snapshot,capture)
            manifest=json.loads((capture/'capture_manifest.json').read_text())
            for name,ref in (('site/katalog.html','offline-only-absent.jpg'),
                             ('video/katalog.html','/site/served-page-absent.jpg')):
                path=capture/name
                path.write_bytes(path.read_bytes()+('<img src="'+ref+'">').encode())
                manifest['sha256'][name]=sha(path.read_bytes())
            (capture/'capture_manifest.json').write_text(json.dumps(manifest))
            build(capture,root/'output','https://www.uaart.com.ua',route)
            provenance=json.loads((root/'output/provenance.json').read_text())
            paths={item['path'] for item in provenance['missing_assets']}
            self.assertNotIn('/site/offline-only-absent.jpg',paths)
            self.assertIn('/site/served-page-absent.jpg',paths)
            self.assertTrue(any(item=={'path':'/site/served-page-absent.jpg',
                'reason':'UNSERVED_PRODUCTION_ASSET_ROUTE'} for item in provenance['missing_assets']))
            self.assertEqual(provenance['preview_gate'],'NOT_PASSED')

    def test_site_source_drift_still_blocks_before_any_output(self):
        snapshot=Path(os.environ['UA088_LIVE_SOURCE_DIR'])
        route=Path(__file__).resolve().parents[1]/'task088_v5_acceptance/route_observations.json'
        rows=json.loads((snapshot/'published_price_rows.json').read_text())
        name='site/'+rows[0]['auto_number']+'.html'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            capture=root/'capture'
            shutil.copytree(snapshot,capture)
            original=(capture/name).read_bytes()
            for change in (b' VIN drift ',b'<img src="unrelated-photo.jpg">'):
                (capture/name).write_bytes(original+change)
                with self.assertRaisesRegex(ValueError,'CAPTURE_HASH_MISMATCH:site/'):
                    build(capture,root/'output','https://www.uaart.com.ua',route)
                self.assertFalse((root/'output').exists())

    def test_site_static_mapping_or_wrapper_change_prevents_offline_classification(self):
        snapshot=Path(os.environ['UA088_LIVE_SOURCE_DIR'])
        route=Path(__file__).resolve().parents[1]/'task088_v5_acceptance/route_observations.json'
        original=json.loads(route.read_text())
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for field,value,error in (
                ('static_mappings',original['static_mappings']+[{'url':'/site/','directory':'/home/Carix/site/'}],
                 'LEGACY_HOME_REDIRECT_STATIC_MAPPING_DRIFT'),
                ('wrapper_routes',{**original['wrapper_routes'],'unexpected':['/site/']},
                 'UNSERVED_SITE_WRAPPER_ROUTE_OBSERVATION_REQUIRED'),
                ('source_sha256',{**original['source_sha256'],'analitika_wsgi.py':'0'*64},
                 'ROUTING_EVIDENCE_CAPTURE_MISMATCH')):
                changed={**original,field:value}
                evidence=root/'routes.json'
                evidence.write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError,error):
                    build(snapshot,root/'output','https://www.uaart.com.ua',evidence)
                self.assertFalse((root/'output').exists())


if __name__=='__main__': unittest.main()
