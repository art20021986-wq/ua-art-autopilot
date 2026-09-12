import gzip
import hashlib
import json
import pathlib
import tempfile
import unittest

from test_counters import catalog,home,ROWS


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name)
        self.roots=[self.root/'video',self.root/'site']
        for root in self.roots:
            root.mkdir();(root/'index.html').write_text(home());(root/'katalog.html').write_text(catalog(ROWS))
        roots=self.roots;root=self.root
        def atomic(path,data,mode=0o644):
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        def digest(data):return hashlib.sha256(data).hexdigest()
        class ExistingSnapshot:
            def __init__(self,codes):
                self.codes=set(codes)
                self.root=pathlib.Path(tempfile.mkdtemp(dir=root))
                self.before_paths={r/'katalog.html' for r in roots}
                self.present=set(self.before_paths)
                manifest={}
                for p in self.present:
                    rel=pathlib.Path('files')/(str(p.relative_to(root))+'.gz')
                    atomic(self.root/rel,gzip.compress(p.read_bytes()))
                    manifest[str(p)]={'exists':True,'stored_relative':str(rel),'sha256':digest(p.read_bytes()),'mode':0o644}
                (self.root/'manifest.json').write_text(json.dumps(manifest))
            def restore(self):
                manifest=json.loads((self.root/'manifest.json').read_text())
                for p in self.present: atomic(p,gzip.decompress((self.root/manifest[str(p)]['stored_relative']).read_bytes()))
        self.ExistingSnapshot=ExistingSnapshot
        def install(source,target):
            for r in roots: (r/'katalog.html').write_text(source)
            return {'installed':{str(r/'katalog.html'):{} for r in roots}}
        self.ns={'Snapshot':ExistingSnapshot,'_install_catalog':install,'ROOT':root,'ROOTS':roots,
                 '_atomic':atomic,'_read':lambda p:p.read_bytes(),'_sha':digest,'_ua099_gzip':gzip,
                 'json':json,'pathlib':pathlib,'PublishError':RuntimeError,'_row_map':lambda:({},'digest'),
                 '_validate_catalog':lambda source,rows:{'status':'PASS'}}
        source=(pathlib.Path(__file__).parent/'publisher_fragment.py').read_text()
        exec(compile(source,'publisher_fragment.py','exec'),self.ns)

    def test_publish_nineteenth_updates_home_and_is_rollback_safe(self):
        before={p:p.read_bytes() for r in self.roots for p in r.glob('*.html')}
        snapshot=self.ns['Snapshot']([])
        result=self.ns['_install_catalog'](catalog(ROWS+[('UA-0019','korea')]),'UA-0019')
        self.assertEqual(result['site_counters']['all'],19)
        for root in self.roots:
            self.assertIn('Открыть все автомобили · 19',(root/'index.html').read_text())
            self.assertEqual(result['installed'][str(root/'katalog.html')]['sha256'],hashlib.sha256((root/'katalog.html').read_bytes()).hexdigest())
        snapshot.restore()
        for p,data in before.items():self.assertEqual(p.read_bytes(),data)

    def test_rebuild_after_unpublish_or_stage_change_updates_both(self):
        self.ns['_install_catalog'](catalog(ROWS+[('UA-0019','korea')]),'UA-0019')
        result=self.ns['_install_catalog'](catalog(ROWS),None)
        self.assertEqual(result['site_counters']['all'],18)
        result=self.ns['_install_catalog'](catalog([('UA-0001','more')]+ROWS[1:]),None)
        self.assertEqual(result['site_counters'],dict(all=18,kiev=4,georgia=1,sea=9,korea=4))

    def test_old_snapshot_without_home_does_not_remove_or_restore_home(self):
        old=self.ExistingSnapshot([])
        for root in self.roots:(root/'index.html').write_text('newer owner homepage')
        instance=self.ns['Snapshot'].__new__(self.ns['Snapshot'])
        instance.__dict__.update(old.__dict__)
        instance.restore()
        for root in self.roots:self.assertEqual((root/'index.html').read_text(),'newer owner homepage')


if __name__=='__main__':unittest.main()
