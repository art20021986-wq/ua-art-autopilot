import contextlib
import importlib.util
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest

from ua_delete_public_guard import (PublicDeletionGuard, DeletedPublicationRefused, advertised_codes,
                                    HISTORICAL_RESERVATIONS, verify_historical_evidence)
from build_writer_patch import _atomic_wrapper, _append, _replace_function, transform, SPEC_RUNTIME_GUARD, URGENT


class WriterGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = os.environ.get('UA_TEST_FENCE_SOURCE')
        if not source:
            raise RuntimeError('UA_TEST_FENCE_SOURCE must point to reviewed publication_fence.py')
        spec = importlib.util.spec_from_file_location('ua_test_real_publication_fence', source)
        cls.fence_module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.fence_module
        spec.loader.exec_module(cls.fence_module)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in ('video', 'site', 'backups'):
            (self.root / folder).mkdir()
        self.db = self.root / 'crm.db'
        with sqlite3.connect(self.db) as c:
            c.execute('CREATE TABLE cars(id INTEGER PRIMARY KEY,auto_number TEXT,vin TEXT,published INTEGER)')
            c.execute('CREATE TABLE ua_delete_intents(car_id INTEGER,car_code TEXT,vin TEXT,state TEXT)')
            c.executemany('INSERT INTO cars VALUES(?,?,?,?)', [(2,'UA-0002','VIN2',1),(3,'UA-0003','VIN3',1)])
        self.lock = self.root / 'publish.lock'
        self.guard = PublicDeletionGuard(self.root, self.db, self.fence, self.require,
                                         historical_reservations=())

    def fence(self):
        return self.fence_module.PublicationFence(lock_path=self.lock, _test_only_path=True, timeout=2)

    def require(self):
        self.fence_module.require_publication_fence(lock_path=self.lock)

    def tombstone(self, code='UA-0002', car_id=2, vin='VIN2'):
        with self.fence(), sqlite3.connect(self.db) as c:
            c.execute('INSERT INTO ua_delete_intents VALUES(?,?,?,?)', (car_id,code,vin,'REQUESTED'))

    def test_delayed_precomputed_card_cannot_reappear(self):
        path = self.root / 'video' / 'UA-0002.html'
        payload = '<html>old prepared card</html>'
        self.tombstone()
        with self.assertRaisesRegex(DeletedPublicationRefused, 'DELETED_CAR'):
            with self.guard.write(path, payload):
                path.write_text(payload)
        self.assertFalse(path.exists())

    def test_historical_emergency_identity_reserved_without_routine_intent(self):
        guard = PublicDeletionGuard(self.root, self.db, self.fence, self.require)
        with sqlite3.connect(self.db) as c:
            c.execute('DELETE FROM cars WHERE auto_number=?', ('UA-0002',))
        for name in ('UA-0002.html', 'UA-0002-diag.html', 'UA-0002-a6f9d391.html'):
            with self.assertRaisesRegex(DeletedPublicationRefused, 'DELETED_CAR'):
                with guard.write(self.root/'video'/name, '<html>old emergency backup</html>'):
                    self.fail('historical path admitted')
        for car_id, vin in [(8, 'other-vin'), (18, 'wdd-2452322j561014')]:
            with sqlite3.connect(self.db) as c:
                c.execute('INSERT INTO cars VALUES(?,?,?,1)', (car_id,'UA-0018',vin))
            with self.fence(), self.assertRaisesRegex(DeletedPublicationRefused, 'HISTORICAL'):
                guard.require_active('UA-0018')
            with sqlite3.connect(self.db) as c:
                c.execute('DELETE FROM cars WHERE id=?', (car_id,))
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM ua_delete_intents').fetchone()[0],0)

    def test_historical_binding_requires_exact_completed_emergency_evidence(self):
        evidence_root = os.environ.get('UA_TEST_PRIVATE_ROOT')
        if not evidence_root:
            raise RuntimeError('UA_TEST_PRIVATE_ROOT must contain verified emergency plan and receipt')
        root=Path(evidence_root)
        plan=(root/'emergency-plan.json').read_bytes()
        receipt=(root/'public_fixture_tree/uploads/ua0002_job/console-result.json').read_bytes()
        proof=verify_historical_evidence(plan,receipt)
        self.assertEqual((proof['code'],proof['car_id'],proof['vin_sha256']),HISTORICAL_RESERVATIONS[0])
        with self.assertRaisesRegex(ValueError,'EXACT_HISTORICAL'):
            verify_historical_evidence(plan,receipt+b' ')

    def test_sitemap_xml_rejects_delayed_retired_and_encoded_urls(self):
        self.tombstone()
        path=self.root/'video'/'sitemap.xml'
        for url in ('https://www.uaart.com.ua/video/UA-0002.html',
                    'https://www.uaart.com.ua/video/UA%2D0002-diag.html'):
            with self.assertRaises(DeletedPublicationRefused):
                with self.guard.write(path, '<urlset><url><loc>'+url+'</loc></url></urlset>'):
                    self.fail('retired sitemap admitted')
        current='<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://www.uaart.com.ua/video/UA-0003.html</loc></url></urlset>'
        with self.guard.write(path,current):
            path.write_text(current)
        with self.assertRaisesRegex(DeletedPublicationRefused,'SITEMAP'):
            with self.guard.write(path,'<malformed'):
                self.fail('malformed sitemap admitted')
        self.assertEqual(path.read_text(),current)

    def test_stale_catalog_and_hashed_alias_rejected(self):
        self.tombstone()
        for path,payload in [
            (self.root/'site'/'katalog.html','<a href="UA-0002.html">old</a>'),
            (self.root/'video'/'UA-0002-abcdef12.html','old alias'),
            (self.root/'video'/'UA-0002-diag.html','old diagnostic')]:
            with self.subTest(path=path):
                with self.assertRaises(DeletedPublicationRefused):
                    with self.guard.write(path,payload):
                        path.write_text(payload)
                self.assertFalse(path.exists())

    def test_current_other_car_and_retained_media_remain_usable(self):
        self.tombstone()
        payload = '<a href="UA-0003.html">current</a><img src="UA-0002.webp">'
        path = self.root/'video'/'katalog.html'
        with self.guard.write(path,payload):
            path.write_text(payload)
        self.assertEqual(path.read_text(),payload)

    def test_hide_rollback_accepts_nonretired_unpublished_preimage(self):
        with sqlite3.connect(self.db) as c:
            c.execute('UPDATE cars SET published=0 WHERE id=3')
        path = self.root/'video'/'katalog.html'
        with self.guard.write(path,'<a href="UA-0003.html">rollback</a>'):
            pass
        with self.fence():
            with self.assertRaisesRegex(DeletedPublicationRefused,'CURRENT_PUBLISHED'):
                self.guard.require_active('UA-0003')

    def test_identity_reuse_is_blocked_even_after_code_changes(self):
        self.tombstone(car_id=88,code='UA-0088',vin='v-i n 3')
        with self.fence():
            with self.assertRaisesRegex(DeletedPublicationRefused,'IDENTITY_RESERVED'):
                self.guard.require_active('UA-0003')

    def test_missing_schema_fails_closed_without_creating_it(self):
        with sqlite3.connect(self.db) as c:
            c.execute('DROP TABLE ua_delete_intents')
        with self.assertRaisesRegex(DeletedPublicationRefused,'SCHEMA_REQUIRED'):
            with self.guard.write(self.root/'video'/'UA-0003.html','payload'):
                pass
        with sqlite3.connect(self.db) as c:
            self.assertFalse(c.execute("SELECT 1 FROM sqlite_master WHERE name='ua_delete_intents'").fetchall())

    def test_cross_thread_retirement_waits_for_actual_write(self):
        started, admitted, errors = threading.Event(), threading.Event(), []
        path = self.root/'video'/'UA-0002.html'
        def retire():
            try:
                started.set()
                self.tombstone()
                admitted.set()
            except BaseException as exc:
                errors.append(exc)
        with self.guard.write(path,'new page'):
            thread = threading.Thread(target=retire)
            thread.start()
            self.assertTrue(started.wait(1))
            self.assertFalse(admitted.wait(.05))
            path.write_text('new page')
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors,[])
        self.assertTrue(admitted.is_set())
        with self.assertRaises(DeletedPublicationRefused):
            with self.guard.write(path,'stale continuation'):
                path.write_text('stale continuation')
        self.assertEqual(path.read_text(),'new page')

    def test_same_thread_nested_fence_is_reentrant(self):
        with self.fence(), self.guard.write(self.root/'site'/'UA-0003.html','current'):
            self.guard.require_active('UA-0003', car_id=3,vin='v i-n3')

    def test_symlink_and_unknown_alias_rejected(self):
        (self.root/'video'/'UA-0003.html').symlink_to(self.root/'outside')
        for path in [self.root/'video'/'UA-0003.html',self.root/'site'/'UA-0003-weird.html']:
            with self.assertRaises(DeletedPublicationRefused):
                with self.guard.write(path,'data'):
                    pass

    def test_extracted_literal_and_encoded_links(self):
        self.assertEqual(advertised_codes('<a href="UA%2D0002.html">x</a><i data-ua-card="UA-0003"></i>'),{'UA-0002','UA-0003'})

    def test_atomic_wrapper_guards_actual_replacement(self):
        ns = {'_delete_guarded_write':self.guard.write}
        calls=[]
        def atomic(path,payload):
            calls.append(path)
            path.write_bytes(payload)
        ns['atomic']=atomic
        exec(_atomic_wrapper('atomic'),ns)
        path = self.root/'site'/'UA-0003.html'
        ns['atomic'](path,b'current')
        self.tombstone(code='UA-0003',car_id=3,vin='VIN3')
        with self.assertRaises(DeletedPublicationRefused):
            ns['atomic'](path,b'stale')
        self.assertEqual(len(calls),1)
        self.assertEqual(path.read_bytes(),b'current')

    def test_spec_runtime_reuses_registry_instead_of_raw_double_flock(self):
        import fcntl
        import time
        from types import SimpleNamespace
        from unittest.mock import patch
        # Exercise replacement with real flock for remaining legacy lock and
        # real publication registry. Spec write lock nests the same registry.
        raw_public = self.root/'.ua_art_publish_transaction.lock'
        self.lock = raw_public
        raw_public.touch()
        (self.root/'.legacy.lock').touch()
        class Deferred(RuntimeError):
            pass
        import ast
        runtime_path = os.environ.get('UA_TEST_SPEC_SOURCE')
        if runtime_path:
            raw = Path(runtime_path).read_bytes()
            tree = ast.parse(raw)
            assignment = next(n for n in tree.body if isinstance(n, ast.Assign)
                              and any(isinstance(t, ast.Name) and t.id == 'WRITER_LOCKS'
                                      for t in n.targets))
            lock_names = ast.literal_eval(assignment.value)
            self.assertEqual(lock_names, ('.task082_catalog_stage_repair.lock',
                '.task082_catalog_stage_guard.lock', '.task083_catalog_dedup.lock',
                '.ua_art_publish_transaction.lock', '.crm_db.lock'))
            patched = ast.parse(transform('ua_spec84_runtime.py', raw))
            node = next(n for n in patched.body if isinstance(n, ast.FunctionDef)
                        and n.name == '_writer_guard')
            guard_code = compile(ast.Module(body=[node],type_ignores=[]),'<actual-spec-guard>','exec')
        else:
            lock_names = ('.ua_art_publish_transaction.lock','.legacy.lock')
            guard_code = SPEC_RUNTIME_GUARD
        for name in lock_names:
            (self.root/name).touch(exist_ok=True)
        ns = {'contextlib':contextlib, 'time':time, 'os':os, 'fcntl':fcntl,
              'ROOT':self.root, 'WRITER_LOCKS':lock_names,
              'RuntimeDeferred':Deferred, '_stop':threading.Event()}
        exec(guard_code,ns)
        events = []
        original_open = os.open
        def observed_open(path, *args, **kwargs):
            name = Path(path).name
            if name in lock_names and name != '.ua_art_publish_transaction.lock':
                events.append(name)
            return original_open(path, *args, **kwargs)
        def publication_factory(**kwargs):
            events.append('.ua_art_publish_transaction.lock')
            return self.fence()
        fake_public = SimpleNamespace(publication_fence=publication_factory,
                                      FenceTimeout=self.fence_module.FenceTimeout)
        fake_guard = SimpleNamespace(require_active=self.guard.require_active,
                                     DeletedPublicationRefused=DeletedPublicationRefused)
        fake_spec = SimpleNamespace(write_lock=lambda *a,**kw:self.fence())
        with patch.dict(sys.modules, {'publication_fence':fake_public,
                                     'ua_delete_public_guard':fake_guard,
                                     'ua_spec_permanent':fake_spec}):
            with patch('os.open', side_effect=observed_open):
                with ns['_writer_guard']('UA-0002'):
                    self.require()
            self.assertEqual(events, list(lock_names))
            self.tombstone()
            with self.assertRaises(Deferred):
                with ns['_writer_guard']('UA-0002'):
                    self.fail('retired spec writer entered')

    def _urgent_namespace(self):
        import shutil
        ns = {'ua0009_urgent_publish': lambda: self.require(),
              '_delete_publication_fence': lambda **kw: self.fence(),
              '_delete_require_active': self.guard.require_active,
              '_delete_guarded_write': self.guard.write,
              'shutil': shutil}
        exec(URGENT, ns)
        return ns

    def test_urgent_restore_rejects_deleted_catalog_preimage(self):
        ns = self._urgent_namespace()
        target = self.root/'video'/'katalog.html'
        stored = self.root/'backups'/'katalog.html'
        stored.write_bytes(b'<a href="UA-0002.html">old</a>')
        target.write_bytes(b'new current catalog')
        self.tombstone()
        with self.assertRaises(DeletedPublicationRefused):
            ns['_delete_restore_urgent_backup'](str(target), str(stored),
                                                {str(target): target.read_bytes()})
        self.assertEqual(target.read_bytes(), b'new current catalog')

    def test_urgent_restore_preserves_unrelated_newer_catalog(self):
        ns = self._urgent_namespace()
        target = self.root/'video'/'katalog.html'
        stored = self.root/'backups'/'katalog.html'
        stored.write_bytes(b'<a href="UA-0003.html">old</a>')
        target.write_bytes(b'<a href="UA-0003.html">operator newer price</a>')
        with self.assertRaisesRegex(RuntimeError, 'CURRENT_BYTES_CHANGED'):
            ns['_delete_restore_urgent_backup'](str(target), str(stored),
                                                {str(target): b'our failed generation'})
        self.assertIn(b'operator newer price', target.read_bytes())

    def test_urgent_restore_accepts_own_current_write(self):
        ns = self._urgent_namespace()
        target = self.root/'video'/'katalog.html'
        stored = self.root/'backups'/'katalog.html'
        stored.write_bytes(b'<a href="UA-0003.html">previous</a>')
        target.write_bytes(b'our generation')
        ns['_delete_restore_urgent_backup'](str(target), str(stored),
                                            {str(target): b'our generation'})
        self.assertEqual(target.read_bytes(), stored.read_bytes())

    def test_actual_urgent_exception_path_cannot_restore_retired_entry(self):
        import ast
        import shutil
        import time
        import json
        import re
        source_path = os.environ.get('UA_TEST_PUBLISH_SOURCE')
        if not source_path:
            self.skipTest('UA_TEST_PUBLISH_SOURCE required for full-source regression')
        candidate = transform('publikaciya.py', Path(source_path).read_bytes())
        tree = ast.parse(candidate)
        defs = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                and n.name == 'ua0009_urgent_publish']
        self.assertEqual(len(defs), 2)
        ns = self._urgent_namespace()
        ns.update({'os':os, 'shutil':shutil, 'time':time, 'json':json, 're':re,
                   'VIDEO':str(self.root/'video'), 'SITE':str(self.root/'site'),
                   'REZERV_KORE':str(self.root/'backups'),
                   'ua0009_urgent_probe':lambda:{'pass':True},
                   '_UA9_BASE_PUBLISH':lambda *a,**k:(True,'ok'),
                   '_ua9_sobrat_katalog':lambda:('prepared stale',[]),
                   '_chitat':lambda p:Path(p).read_text()})
        before = '<a href="UA-0002.html">old retired</a>'
        for folder in ('video','site'):
            (self.root/folder/'katalog.html').write_text(before)
        with sqlite3.connect(self.db) as c:
            c.execute('INSERT INTO cars VALUES(9,?,?,1)',('UA-0009','VIN9'))
        def rejected(path, payload):
            self.tombstone()
            Path(path).write_text('new catalog without retired identity')
            raise DeletedPublicationRefused('DELETED_CAR_PUBLIC_WRITE_REFUSED')
        ns['_zapisat_atomarno'] = rejected
        exec(compile(ast.Module(body=[defs[0]],type_ignores=[]),'<actual-urgent-body>','exec'),ns)
        exec(URGENT,ns)
        result = ns['ua0009_urgent_publish']()
        self.assertFalse(result[0])
        self.assertIn('отклонено', result[1])
        self.assertNotIn('UA-0002', (self.root/'video'/'katalog.html').read_text())

    def test_full_runtime_atomic_guard_keeps_existing_compare_and_swap(self):
        import ast
        import pathlib
        source_path = os.environ.get('UA_TEST_SPEC_SOURCE')
        if not source_path:
            self.skipTest('UA_TEST_SPEC_SOURCE required for full-source regression')
        candidate = transform('ua_spec84_runtime.py', Path(source_path).read_bytes())
        tree = ast.parse(candidate)
        definitions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                       and n.name == '_atomic_existing']
        self.assertEqual(len(definitions),2)
        class Deferred(RuntimeError):
            pass
        ns={'os':os,'tempfile':tempfile,'pathlib':pathlib,'RuntimeDeferred':Deferred,
            '_delete_guarded_write':self.guard.write}
        exec(compile(ast.Module(body=[definitions[0]],type_ignores=[]),'<original-spec-atomic>','exec'),ns)
        ns['_delete_original_spec_atomic']=ns['_atomic_existing']
        exec(compile(ast.Module(body=[definitions[1]],type_ignores=[]),'<guarded-spec-atomic>','exec'),ns)
        path=self.root/'video'/'UA-0003.html'
        path.write_bytes(b'newer operator content')
        with self.assertRaises(Deferred):
            ns['_atomic_existing'](path,b'old preimage',b'spec render')
        self.assertEqual(path.read_bytes(),b'newer operator content')
        ns['_atomic_existing'](path,b'newer operator content',b'spec render')
        self.assertEqual(path.read_bytes(),b'spec render')
        self.tombstone(code='UA-0003',car_id=3,vin='VIN3')
        with self.assertRaises(DeletedPublicationRefused):
            ns['_atomic_existing'](path,b'spec render',b'late rollback')
        self.assertEqual(path.read_bytes(),b'spec render')

    def test_actual_stage_reconcile_cannot_restore_deleted_listing(self):
        import hashlib
        import re
        from types import SimpleNamespace
        from unittest.mock import patch
        source_path=os.environ.get('UA_TEST_STAGE_SOURCE')
        if not source_path:
            self.skipTest('UA_TEST_STAGE_SOURCE required for full-source regression')
        raw=Path(source_path).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
            'c349d44821f92950234705d41507587c3ca2780dd750abda0028c060569a5beb')
        module={'__name__':'ua_stage_test'}
        exec(compile(raw,'<actual-stage-sync>','exec'),module)
        source=(b'<article class="catalog-card" data-stage="korea" data-ua-stage="1">'
            b'<div class="ua-cat-vin-v1" data-ua-card="UA-0002" data-ua-stage-tile="1" data-category="korea"></div>'
            + '<div class="status-pill" data-ru="В Корее" data-uk="У Кореї">В Корее</div>'.encode()
            + b'</article>')
        roots=(self.root/'video',self.root/'site')
        for root in roots:
            (root/'katalog.html').write_bytes(source)
            (root/'index.html').write_text('<section class="stage-card"></section>')
            (root/'UA-0002.html').write_text('<div data-ua-stage-current="2"></div>')
        def snapshot(text):
            stage=re.search(r'data-stage="([a-z]+)"',text)[1]
            records={'UA-0002':stage}
            counts={'all':1,'kiev':0,'georgia':0,'sea':0,'korea':0}
            counts[stage]=1
            return records,counts
        atomic_ns={'_atomic':lambda path,payload,mode=None:Path(path).write_bytes(payload),
                   '_delete_guarded_write':self.guard.write}
        exec(_atomic_wrapper('_atomic'),atomic_ns)
        pub=SimpleNamespace(_exclusive_lock=self.fence,ROOTS=roots,ROOT=self.root,
            _row_map=lambda:({'UA-0002':{'auto_number':'UA-0002','status':'sea_transport'}},'digest'),
            _stage=lambda row:2,_validate_catalog=lambda source,rows:None,
            _atomic=atomic_ns['_atomic'])
        counter=SimpleNamespace(catalog_snapshot=snapshot,
            patch_catalog=lambda text,counts:text,
            patch_home=lambda text,counts:text+'<!--counter updated-->')
        self.tombstone()
        with patch.dict(sys.modules, {'publish_transaction_guard':pub,'ua_site_counters':counter}):
            with self.assertRaises(DeletedPublicationRefused):
                module['reconcile'](apply=True)
        # Stage backup writes may occur, but neither public generation nor its
        # failure rollback may rewrite a retired identity into either catalog.
        for root in roots:
            self.assertEqual((root/'katalog.html').read_bytes(),source)
            self.assertNotIn('counter updated',(root/'index.html').read_text())

    def test_transform_refuses_unreviewed_source(self):
        with self.assertRaisesRegex(ValueError,'HASH_REQUIRED'):
            transform('yadro.py', 'x=1\n')

    def test_actual_diagnostic_cleanup_preserves_delayed_retired_media(self):
        import ast
        import json
        from types import SimpleNamespace
        from unittest.mock import patch
        source=os.environ.get('UA_TEST_KADRY_SOURCE')
        if not source:
            raise RuntimeError('UA_TEST_KADRY_SOURCE must point to exact reviewed kadry_diagnostiki.py')
        candidate=ast.parse(transform('kadry_diagnostiki.py',Path(source).read_bytes()))
        # Execute the actual original worker body with only its explicit unlink
        # transformed. External downloads, logs and cache writes are inert.
        worker=next(node for node in candidate.body if isinstance(node,ast.FunctionDef) and node.name=='shag')
        cleanup=next(node for node in candidate.body if isinstance(node,ast.FunctionDef) and node.name=='_delete_cleanup_diagnostic_media')
        media_root=self.root/'video'/'diag'
        folder=media_root/'UA-0002'
        folder.mkdir(parents=True)
        wanted=folder/'01.jpg'
        obsolete=folder/'02.jpg'
        history_guard=PublicDeletionGuard(self.root,self.db,self.fence,self.require)
        for mode in ('active','accepted_intent','absent','historical'):
            with self.subTest(mode=mode):
                with sqlite3.connect(self.db) as c:
                    c.execute('DELETE FROM ua_delete_intents')
                    c.execute('DELETE FROM cars WHERE auto_number=?',('UA-0002',))
                    c.execute('INSERT INTO cars VALUES(2,?,?,1)',('UA-0002','VIN2'))
                wanted.write_bytes(b'existing-wanted-media')
                obsolete.write_bytes(b'retained-after-delete')
                row={'id':2,'auto_number':'UA-0002','condition_photos':'["file1"]','condition_videos':'[]'}
                def captured_rows():
                    if mode=='accepted_intent':
                        self.tombstone()
                    elif mode in ('absent','historical'):
                        with sqlite3.connect(self.db) as c:
                            c.execute('DELETE FROM cars WHERE id=2')
                    return [row],'auto_number'
                guard=history_guard if mode=='historical' else self.guard
                ns={'os':os,'KUDA':str(media_root),'mashiny':captured_rows,
                    'uchet_prochest':lambda:{'UA-0002':{'01.jpg':'file1','02.jpg':'old'}},
                    'uchet_zapisat':lambda data:None,'nomer_mashiny':lambda row,pole:row[pole],
                    '_spisok':json.loads,'FOTO_PREDEL':50,'VIDEO_PREDEL':10,'log':lambda text:None,
                    'skachat_odin':lambda *args:self.fail('unexpected download'),
                    '_delete_publication_fence':lambda **kwargs:self.fence()}
                fake_guard=SimpleNamespace(require_current=guard.require_current,
                                            DeletedPublicationRefused=DeletedPublicationRefused)
                with patch.dict(sys.modules,{'ua_delete_public_guard':fake_guard}):
                    exec(compile(ast.Module(body=[worker,cleanup],type_ignores=[]),'<actual-diagnostic-cleanup>','exec'),ns)
                    ns['shag']()
                self.assertEqual(wanted.read_bytes(),b'existing-wanted-media')
                self.assertEqual(obsolete.exists(),mode!='active')
                if obsolete.exists():
                    self.assertEqual(obsolete.read_bytes(),b'retained-after-delete')

    def test_actual_download_commit_rechecks_retirement_after_network(self):
        import ast
        from types import SimpleNamespace
        from unittest.mock import patch
        source=Path(os.environ['UA_TEST_KADRY_SOURCE']).read_bytes()
        tree=ast.parse(transform('kadry_diagnostiki.py',source))
        download=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='skachat_odin')
        replace=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_delete_replace_diagnostic_media')
        folder=self.root/'video'/'diag'/'UA-0002'
        folder.mkdir(parents=True)
        destination=folder/'01.jpg'
        for mode in ('active','accepted_intent','absent','historical'):
            with self.subTest(mode=mode):
                with sqlite3.connect(self.db) as c:
                    c.execute('DELETE FROM ua_delete_intents')
                    c.execute('DELETE FROM cars WHERE auto_number=?',('UA-0002',))
                    c.execute('INSERT INTO cars VALUES(2,?,?,1)',('UA-0002','VIN2'))
                destination.write_bytes(b'original-retained-media')
                calls=[]
                def request(url):
                    with self.assertRaises(self.fence_module.FenceError):
                        self.require()
                    calls.append(url)
                    if len(calls)==1:
                        return b'{"ok":true,"result":{"file_path":"fixture.jpg"}}'
                    if mode=='accepted_intent':
                        self.tombstone()
                    elif mode in ('absent','historical'):
                        with sqlite3.connect(self.db) as c:
                            c.execute('DELETE FROM cars WHERE id=2')
                    return b'new-download'*100
                guard=(PublicDeletionGuard(self.root,self.db,self.fence,self.require)
                       if mode=='historical' else self.guard)
                ns={'os':os,'json':__import__('json'),'KUDA':str(folder.parent),
                    'tokeny':lambda:['fixture-token'],'_zapros':request,'log':lambda text:None,
                    '_delete_publication_fence':lambda **kwargs:self.fence()}
                fake=SimpleNamespace(require_current=guard.require_current,
                                     DeletedPublicationRefused=DeletedPublicationRefused)
                with patch.dict(sys.modules,{'ua_delete_public_guard':fake}):
                    exec(compile(ast.Module(body=[download,replace],type_ignores=[]),'<actual-download-commit>','exec'),ns)
                    result=ns['skachat_odin']('fixture-file',str(destination))
                self.assertEqual(result,mode=='active')
                self.assertEqual(destination.read_bytes(),b'new-download'*100 if mode=='active' else b'original-retained-media')

    def test_actual_media_relocation_preserves_retired_source_and_targets(self):
        import ast
        from types import SimpleNamespace
        from unittest.mock import patch
        source=Path(os.environ['UA_TEST_KADRY_SOURCE']).read_bytes()
        tree=ast.parse(transform('kadry_diagnostiki.py',source))
        relocate=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='polozhit_pravilno')
        replace=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_delete_replace_diagnostic_media')
        media_root=self.root/'video'/'diag'
        self.tombstone()
        for overflow in (False,True):
            with self.subTest(overflow=overflow):
                folder=media_root/'UA-0002'
                folder.mkdir(parents=True,exist_ok=True)
                source_path=folder/'01.jpg'
                source_path.write_bytes(b'original-retained-source')
                if overflow:
                    for i in range(1,61):
                        (folder/('%02d.mp4'%i)).write_bytes(b'existing-target')
                ns={'os':os,'KUDA':str(media_root),'tip_po_soderzhimomu':lambda path:'.mp4',
                    'log':lambda text:None,'_delete_publication_fence':lambda **kwargs:self.fence()}
                fake=SimpleNamespace(require_current=self.guard.require_current,
                                     DeletedPublicationRefused=DeletedPublicationRefused)
                with patch.dict(sys.modules,{'ua_delete_public_guard':fake}):
                    exec(compile(ast.Module(body=[relocate,replace],type_ignores=[]),'<actual-media-relocation>','exec'),ns)
                    self.assertEqual(ns['polozhit_pravilno'](str(source_path),'.jpg'),str(source_path))
                self.assertEqual(source_path.read_bytes(),b'original-retained-source')
                self.assertFalse((folder/'neverno'/'01.jpg').exists())
                if overflow:
                    self.assertTrue(all(path.read_bytes()==b'existing-target' for path in folder.glob('*.mp4')))
                else:
                    self.assertFalse((folder/'01.mp4').exists())

    def test_wrappers_install_before_main_execution(self):
        ns={}
        candidate=_append("def main():\n    seen.append('old')\nif __name__ == '__main__':\n    main()\n", "def main():\n    seen.append('new')\n")
        exec(candidate,{'__name__':'__main__','seen':ns.setdefault('seen',[])})
        self.assertEqual(ns['seen'],['new'])


if __name__=='__main__':
    unittest.main()
