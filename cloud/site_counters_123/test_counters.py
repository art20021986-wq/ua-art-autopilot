import contextlib
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import ua_site_counters as core
import home_counters_install_20260910 as installer


def catalog(rows, uk=False):
    buttons = ''.join('<button data-f="%s" data-ru="старое" data-uk="старе">16</button>' % key
                      for key in ('all','kiev','georgia','sea','korea'))
    cards = ''.join('<article class="catalog-card" data-stage="%s"><a href="%s.html"><img src="%s.webp"></a>'
                    '<div data-ua-card="%s" data-category="%s">VIN/specification</div></article>'
                    % (stage,number,number,number,stage) for number,stage in rows)
    return '<html lang="%s"><head><title>UA ART catalog</title></head><body>' % ('uk' if uk else 'ru') + buttons + '<div class="catalog-grid">'+cards+'</div></body></html>'


ROWS = [('UA-%04d' % i, 'kiev' if i <= 5 else 'gruzia' if i == 6 else 'more' if i <= 14 else 'korea') for i in range(1,19)]


def home(uk=False):
    stages = ''.join('<a class="stage-card" data-stage="%s" data-count="0"><img src="keep-%s.webp"><span class="stage-copy"><em data-ru="0" data-uk="0">0</em></span></a>' % (key,key) for key in core.STAGES)
    return '<html lang="%s"><body><p>Protected design, VIN and media</p>' % ('uk' if uk else 'ru') + stages + '<a class="outline-cta" href="katalog.html"><i data-ru="Открыть все автомобили · 16" data-uk="Відкрити всі автомобілі · 16">16</i></a></body></html>'


class CounterTests(unittest.TestCase):
    def test_publication_unpublication_and_stage_change(self):
        self.assertEqual(core.catalog_snapshot(catalog(ROWS))[1],dict(all=18,kiev=5,georgia=1,sea=8,korea=4))
        self.assertEqual(core.catalog_snapshot(catalog(ROWS+[('UA-0019','korea')]))[1]['all'],19)
        self.assertEqual(core.catalog_snapshot(catalog(ROWS))[1]['all'],18)
        moved = [('UA-0001','more')]+ROWS[1:]
        self.assertEqual(core.catalog_snapshot(catalog(moved))[1],dict(all=18,kiev=4,georgia=1,sea=9,korea=4))

    def test_duplicates_and_future_ids(self):
        self.assertEqual(core.catalog_snapshot(catalog(ROWS+ROWS))[1]['all'],18)
        self.assertEqual(core.catalog_snapshot(catalog(ROWS+[('UA-10000','korea')]))[1]['all'],19)
        with self.assertRaises(core.HomeCounterError):
            core.catalog_snapshot(catalog(ROWS+[('UA-0001','more')]))

    def test_unknown_stage_does_not_drop_total_and_empty_is_zero(self):
        self.assertEqual(core.catalog_snapshot(catalog([('UA-0001','new-stage')]))[1],dict(all=1,kiev=0,georgia=0,sea=0,korea=0))
        self.assertEqual(core.catalog_snapshot(catalog([]))[1],dict(all=0,kiev=0,georgia=0,sea=0,korea=0))
        for invalid in (catalog(ROWS)[:-7],'<html><body>Error</body></html>',catalog([('bad','kiev')])):
            with self.assertRaises(core.HomeCounterError): core.catalog_snapshot(invalid)

    def test_missing_id_or_conflicting_attributes_fail(self):
        source=catalog(ROWS[:1])
        with self.assertRaises(core.HomeCounterError): core.catalog_snapshot(source.replace('data-category="kiev"','data-category="sea"'))
        with self.assertRaises(core.HomeCounterError): core.catalog_snapshot(source.replace('data-ua-card="UA-0001"','').replace('UA-0001.html','no-id.html'))

    def test_patches_preserve_media_identifiers_and_layout_outside_counters(self):
        counts=core.catalog_snapshot(catalog(ROWS))[1]
        before=home()
        after=core.patch_home(before,counts)
        self.assertIn('Открыть все автомобили · 18',after)
        self.assertIn('Відкрити всі автомобілі · 18',after)
        self.assertIn('5 автомобилей',after)
        normalized=core.CARD_RE.sub('',after.split(core.START)[0])
        normalized=core.CTA_RE.sub('',normalized)
        expected=core.CTA_RE.sub('',core.CARD_RE.sub('',before))
        self.assertEqual(normalized+'</body></html>',expected)
        cat_after=core.patch_catalog(catalog(ROWS),counts)
        self.assertEqual(core.catalog_snapshot(cat_after),core.catalog_snapshot(catalog(ROWS)))
        for number,_ in ROWS: self.assertIn('src="'+number+'.webp"',cat_after)

    def test_idempotence_and_language_and_replacement_of_old_counter(self):
        counts=core.catalog_snapshot(catalog(ROWS))[1]
        for old,fn in ((home(True),core.patch_home),(catalog(ROWS,True),core.patch_catalog)):
            once=fn(old,counts)
            self.assertEqual(fn(once,counts),once)
            self.assertEqual(once.count('id="ua-site-counters-123"'),int(fn is core.patch_home))
        self.assertIn('>Відкрити всі автомобілі · 18</i>',core.patch_home(home(True),counts))
        old=home().replace('</body>','<!-- UA-HOME-STAGE-COUNTER-SYNC-093:START --><script>old wrong counter</script><!-- UA-HOME-STAGE-COUNTER-SYNC-093:END --></body>')
        self.assertNotIn('old wrong counter',core.patch_home(old,counts))

    def test_wrong_layout_rejected(self):
        counts=core.catalog_snapshot(catalog(ROWS))[1]
        with self.assertRaises(core.HomeCounterError): core.patch_home(home().replace('data-stage="sea"','data-stage="other"'),counts)
        with self.assertRaises(core.HomeCounterError): core.patch_catalog(catalog(ROWS).replace('data-f="sea"','data-f="other"'),counts)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for name in ('video','site'):
            (self.root/name).mkdir()
            (self.root/name/'katalog.html').write_text(catalog(ROWS))
            (self.root/name/'index.html').write_text(home())
        (self.root/'publish_transaction_guard.py').write_text('def _install_catalog(source,target): pass\nclass Snapshot: pass\n')
        c=sqlite3.connect(self.root/'crm.db')
        c.execute('CREATE TABLE cars (id INTEGER, auto_number TEXT, published INTEGER)')
        c.executemany('INSERT INTO cars VALUES (?,?,?)',[(i,'UA-%04d'%i,int(i<19)) for i in range(1,20)])
        c.commit();c.close()
        self.addCleanup(patch.stopall)
        patch.object(installer,'ROOT',self.root).start()
        patch.object(installer,'EXPECTED_PUBLISHER',installer.sha((self.root/'publish_transaction_guard.py').read_bytes())).start()
        patch.object(installer,'EXPECTED_HOME',installer.sha((self.root/'video/index.html').read_bytes())).start()

    def test_preflight_apply_backup_rollback_preserve_database(self):
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        updates,code,report=installer.preflight(validate_live=False)
        self.assertEqual(before,{p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertEqual(report['counts']['all'],18)
        result=installer.apply(updates,code,report)
        self.assertEqual((self.root/'crm.db').read_bytes(),before[self.root/'crm.db'])
        self.assertTrue((self.root/'publish_transaction_guard.py').read_bytes().startswith(before[self.root/'publish_transaction_guard.py']))
        installer.rollback(result['backup'])
        for path,data in before.items(): self.assertEqual(path.read_bytes(),data)

    def test_different_catalog_copies_fail_without_writes(self):
        (self.root/'site/katalog.html').write_text(catalog(ROWS[:-1]))
        with self.assertRaises(core.HomeCounterError): core.prepare_updates((self.root/'video',self.root/'site'))

    def test_concurrent_change_preserved_and_prior_writes_restored(self):
        updates,code,report=installer.preflight(validate_live=False)
        original=installer.atomic
        original_catalog=(self.root/'video/katalog.html').read_bytes()
        target=self.root/'publish_transaction_guard.py'
        def competing(path,*args,**kwargs):
            original(path,*args,**kwargs)
            if path==self.root/'video/index.html': target.write_text('concurrent edit')
        with patch.object(installer,'atomic',side_effect=competing):
            with self.assertRaises(RuntimeError): installer.apply(updates,code,report)
        self.assertEqual(target.read_text(),'concurrent edit')
        self.assertEqual((self.root/'video/katalog.html').read_bytes(),original_catalog)

    def test_existing_different_core_is_not_overwritten(self):
        updates,code,report=installer.preflight(validate_live=False)
        (self.root/'ua_site_counters.py').write_text('concurrent helper')
        with self.assertRaises(RuntimeError): installer.apply(updates,code,report)
        self.assertEqual((self.root/'ua_site_counters.py').read_text(),'concurrent helper')

    def test_stale_source_and_rollback_edits_are_rejected(self):
        updates,code,report=installer.preflight(validate_live=False)
        result=installer.apply(updates,code,report)
        with self.assertRaises(RuntimeError): installer.preflight(validate_live=False)
        target=self.root/'video/index.html';target.write_text('later owner edit')
        with self.assertRaises(RuntimeError): installer.rollback(result['backup'])
        self.assertEqual(target.read_text(),'later owner edit')


if __name__=='__main__': unittest.main()
