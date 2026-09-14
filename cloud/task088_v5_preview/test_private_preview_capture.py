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
            self.assertEqual(manifest['provenance_sha256'],sha((output/'provenance.json').read_bytes()))
            self.assertFalse(any(path.suffix in ('.py','.db','.sqlite') for path in output.rglob('*')))
            self.assertEqual(output.stat().st_mode & 0o777,0o700)
            with self.assertRaisesRegex(ValueError,'NEW_PRIVATE_OUTPUT_DIRECTORY_REQUIRED'):
                build(snapshot,output,'https://www.uaart.com.ua',route)


if __name__=='__main__': unittest.main()
