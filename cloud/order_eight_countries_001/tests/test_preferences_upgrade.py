from pathlib import Path
import tempfile
import unittest
from upgrade_preferences import prepare,install,rollback,FILES,NEW,BACKEND,FRONTEND


class UpgradeTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.baseline=self.root/'baseline';self.baseline.mkdir()
        for name in FILES:
            if name in NEW:continue
            path=self.baseline/name;path.parent.mkdir(parents=True,exist_ok=True)
            if name=='video/podbor.html':path.write_text('<html><head><meta name="description" content="KEEP SEO"><link href="order/order.css?v=old"><script src="order/order.js?v=old"></script></head><body><header>KEEP HEADER</header><main id="ua-order">old</main><footer>KEEP FOOTER</footer></body></html>')
            else:path.write_text('old:'+name)
        self.before={name:(self.baseline/name).read_bytes() if (self.baseline/name).exists() else None for name in FILES}
        self.bundle=self.root/'bundle';self.report=prepare(self.baseline,self.bundle);self.digest=self.report['manifest_sha256'];self.backup=self.root/'backup'

    def test_two_stage_install_frontend_rollback_keeps_accepted_v2_requests_readable(self):
        extra=self.baseline/'unrelated.txt';extra.write_text('untouched')
        install(self.baseline,self.bundle,self.backup,self.digest,'backend')
        self.assertEqual((self.baseline/'video/podbor.html').read_bytes(),self.before['video/podbor.html'])
        install(self.baseline,self.bundle,self.backup,self.digest,'frontend')
        page=(self.baseline/'video/podbor.html').read_text()
        for value in ['KEEP SEO','KEEP HEADER','KEEP FOOTER','main-fields','optional-preferences']:self.assertIn(value,page)
        result=rollback(self.baseline,self.backup,self.digest)
        self.assertTrue(result['compatible_backend_retained'])
        for name in BACKEND:self.assertEqual((self.baseline/name).read_bytes(),(self.bundle/'files'/name).read_bytes())
        for name in FRONTEND:
            value=self.before[name]
            if value is None:self.assertFalse((self.baseline/name).exists())
            else:self.assertEqual((self.baseline/name).read_bytes(),value)
        self.assertEqual(extra.read_text(),'untouched')

    def test_prepublication_backend_can_be_rolled_back_exactly(self):
        install(self.baseline,self.bundle,self.backup,self.digest,'backend')
        result=rollback(self.baseline,self.backup,self.digest)
        self.assertFalse(result['compatible_backend_retained'])
        for name,value in self.before.items():
            if value is None:self.assertFalse((self.baseline/name).exists())
            else:self.assertEqual((self.baseline/name).read_bytes(),value)

    def test_changed_live_source_blocks_before_any_write(self):
        (self.baseline/'ua_order/crm.py').write_text('new external edit')
        with self.assertRaisesRegex(ValueError,'Live source changed'):install(self.baseline,self.bundle,self.backup,self.digest,'backend')
        self.assertFalse(self.backup.exists())
        self.assertEqual((self.baseline/'ua_order/contract.py').read_bytes(),self.before['ua_order/contract.py'])

    def test_rollback_refuses_later_edits_without_restoring_other_files(self):
        install(self.baseline,self.bundle,self.backup,self.digest,'backend')
        path=self.baseline/'ua_order/crm.py';path.write_text('new owner change');before=(self.baseline/'ua_order/contract.py').read_bytes()
        with self.assertRaisesRegex(ValueError,'Later change'):rollback(self.baseline,self.backup,self.digest)
        self.assertEqual(path.read_text(),'new owner change');self.assertEqual((self.baseline/'ua_order/contract.py').read_bytes(),before)

    def test_unreviewed_or_tampered_bundle_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unreviewed'):install(self.baseline,self.bundle,self.backup,'0'*64,'backend')
        (self.bundle/'files/ua_order/preferences.py').write_text('changed')
        with self.assertRaisesRegex(ValueError,'Bundle changed'):install(self.baseline,self.bundle,self.backup,self.digest,'backend')


if __name__=='__main__':unittest.main()
