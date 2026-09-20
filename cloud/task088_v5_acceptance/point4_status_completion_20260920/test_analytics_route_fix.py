import copy
import io
import json
from pathlib import Path
import sys
import unittest
import zipfile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))

import stage_exact_preview as stage
import upgrade_preview_package_analytics as upgrade


SOURCE=HERE/'exact_preview_current_53544a27_20260920_v2.zip'


class AnalyticsRouteFixTests(unittest.TestCase):
    def setUp(self):
        self.source=SOURCE.read_bytes()
        self.raw=b'(()=>{"use strict"})();\n'
        self.receipt={'schema_version':upgrade.CAPTURE_CONTRACT,'url':upgrade.ANALYTICS_URL,
            'final_url':upgrade.ANALYTICS_URL,'method':'GET','status':200,'content_type':'application/javascript',
            'bytes':len(self.raw),'sha256':stage.sha(self.raw),
            'source_wrapper_sha256':stage.SOURCE_ROUTING['analitika_wsgi.py'],'redirect_followed':False,
            'event_endpoint_called':False,'captured_at_utc':'2026-09-20T12:03:13Z'}

    def encoded(self, value=None): return stage.encoded(self.receipt if value is None else value)

    def test_exact_upgrade_is_deterministic_and_closed(self):
        first,manifest=upgrade.upgrade(self.source,self.raw,self.encoded())
        second,_=upgrade.upgrade(self.source,self.raw,self.encoded())
        self.assertEqual(first,second)
        self.assertEqual(manifest['contract'],upgrade.TARGET_CONTRACT)
        with zipfile.ZipFile(io.BytesIO(first)) as packed:
            names=set(packed.namelist())
            self.assertIn('public/ua/a.js',names);self.assertIn('evidence/ua-a-js.json',names)
            self.assertNotIn('public/ua/a/e',names)
            self.assertEqual(packed.read('public/ua/a.js'),self.raw)
            self.assertEqual(json.loads(packed.read('package_manifest.json'))['public_wrapper_asset']['sha256'],stage.sha(self.raw))

    def test_redirect_fails(self):
        item=copy.deepcopy(self.receipt);item['final_url']='https://evil.example/a.js';item['redirect_followed']=True
        with self.assertRaisesRegex(ValueError,'PINNED_SAFE_ANALYTICS_CAPTURE_REQUIRED'):
            upgrade.upgrade(self.source,self.raw,self.encoded(item))

    def test_event_endpoint_claim_fails(self):
        item=copy.deepcopy(self.receipt);item['event_endpoint_called']=True
        with self.assertRaisesRegex(ValueError,'PINNED_SAFE_ANALYTICS_CAPTURE_REQUIRED'):
            upgrade.upgrade(self.source,self.raw,self.encoded(item))

    def test_mime_fails(self):
        item=copy.deepcopy(self.receipt);item['content_type']='text/html'
        with self.assertRaisesRegex(ValueError,'PINNED_SAFE_ANALYTICS_CAPTURE_REQUIRED'):
            upgrade.upgrade(self.source,self.raw,self.encoded(item))

    def test_capture_bytes_drift_fails(self):
        with self.assertRaisesRegex(ValueError,'PINNED_SAFE_ANALYTICS_CAPTURE_REQUIRED'):
            upgrade.upgrade(self.source,self.raw+b'drift',self.encoded())

    def test_wrapper_source_drift_fails(self):
        item=copy.deepcopy(self.receipt);item['source_wrapper_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'PINNED_SAFE_ANALYTICS_CAPTURE_REQUIRED'):
            upgrade.upgrade(self.source,self.raw,self.encoded(item))

    def test_source_package_extra_member_fails(self):
        src=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(self.source)) as old,zipfile.ZipFile(src,'w') as new:
            for name in old.namelist():new.writestr(name,old.read(name))
            new.writestr('public/ua/evil.js',b'evil')
        with self.assertRaisesRegex(ValueError,'EXACT_SOURCE_PACKAGE_CLOSURE_REQUIRED'):
            upgrade.upgrade(src.getvalue(),self.raw,self.encoded())


if __name__=='__main__':unittest.main()
