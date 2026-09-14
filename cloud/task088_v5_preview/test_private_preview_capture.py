"""Mandatory private Preview check; never counted by public software CI."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from build_preview import build
from common import sha


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
            self.assertEqual(result['preview_gate'],'NOT_PASSED')
            self.assertFalse(result['activated'])
            self.assertFalse(provenance['browser_run'])
            self.assertFalse(provenance['production_written'])
            self.assertTrue(all(page['outside_price_unchanged'] for page in provenance['pages']))
            self.assertTrue(all(check['status']=='NOT_RUN' for page in provenance['matrix'] for check in page['browser']))
            self.assertEqual((output/'public/video/index.html').read_bytes(),(snapshot/'video/index.html').read_bytes())
            self.assertNotIn('/site/index.html',manifest['files'])
            self.assertEqual(manifest['redirects']['/site/index.html']['location'],'/video/index.html')
            self.assertEqual(len(provenance['missing_linked_html']),40)
            self.assertEqual(provenance['linked_public_html'],[])
            self.assertEqual(manifest['provenance_sha256'],sha((output/'provenance.json').read_bytes()))
            self.assertFalse(any(path.suffix in ('.py','.db','.sqlite') for path in output.rglob('*')))
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


if __name__=='__main__': unittest.main()
