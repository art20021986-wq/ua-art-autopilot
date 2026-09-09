"""Isolated CRM/spec SQLite and existing-page lifecycle checks; no live CRM."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

RUNTIME = Path(__file__).resolve().parents[1] / 'runtime'
sys.path.insert(0, str(RUNTIME))
import source_policy
import spec_publication as publication
import vin_spec_service as service

PAGE = ('<!doctype html><html><head><title>Shell kept</title><style>.card{color:white}</style></head><body>'
        '<h1>Kia K5</h1><div data-price="yes">10000</div><video src="same.mp4"></video>'
        "<table><tr><td class='k'>VIN</td><td>KNAGS416BHA141028</td></tr></table>"
        '<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:START --><div>Stage 2</div>'
        '<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:END -->'
        '<footer>Same contacts and controls</footer></body></html>')
FACT = {'field_key': 'wheelbase', 'display_value': '2805 мм', 'label_ru': 'Колёсная база',
        'category': 'dimensions', 'unit': 'мм', 'confidence': .95,
        'source_domains': ['auto-data.net'], 'source_urls': ['https://www.auto-data.net/en/fixture']}


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.paths = service.MAIN_DB, service.SPEC_DB
        service.MAIN_DB, service.SPEC_DB = self.root/'crm.db', self.root/'spec.db'
        self.env = patch.dict('os.environ', {'UA_ART_SPEC_DB': str(service.SPEC_DB)})
        self.env.start()
        self.network = patch('urllib.request.urlopen', side_effect=AssertionError('lifecycle tests forbid network'))
        self.network.start()
        with sqlite3.connect(service.MAIN_DB) as conn:
            conn.executescript('''CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT, vin TEXT,
                marka TEXT, model TEXT, god INTEGER, toplivo TEXT, engine_cc INTEGER,
                transmission TEXT, published INTEGER);
                INSERT INTO cars VALUES(16,'UA-0016','KNAGS416BHA141028','Kia','К5',2017,'LPI',2000,'AT',1);''')
        service.ensure_schema()
        (self.root/'video').mkdir()
        self.page = self.root/'video/UA-0016.html'
        self.page.write_text(PAGE)

    def tearDown(self):
        self.network.stop()
        self.env.stop()
        service.MAIN_DB, service.SPEC_DB = self.paths
        self.temp.cleanup()

    def sql(self, statement):
        with sqlite3.connect(service.MAIN_DB) as conn:
            conn.execute(statement)

    def jobs(self):
        with service.connect_spec(True) as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM vin_spec_jobs ORDER BY id')]

    def ready(self, card):
        return {'status': 'READY', 'facts': [dict(FACT)], 'sources': {'auto-data.net': {'status': 'PASS'}}}

    def collect(self):
        service.scan_new_vins()
        return service.process_one(enricher=self.ready)

    def reconcile(self, card, facts, reader=None):
        return publication.reconcile_published(card, facts, root=self.root,
            public_reader=reader or (lambda code: (self.root/'video'/f'{code}.html').read_text()))

    def assert_retired(self, job):
        self.assertEqual((job['status'], job['site_sync_status']), ('SUPERSEDED', 'SUPERSEDED'))
        self.assertIsNone(job['claim_token'])
        self.assertIsNone(job['site_sync_token'])

    def test_new_save_automatic_collect_then_normal_publish_and_sync_preserve_shell(self):
        self.sql('UPDATE cars SET published=0')
        self.page.unlink()
        actual_process, actual_sync = service.process_one, service.sync_one
        collector = Mock(wraps=self.ready)
        with patch.object(service, 'process_one', side_effect=lambda: actual_process(enricher=collector)), \
             patch.object(service, 'sync_one', side_effect=lambda: actual_sync(reconciler=self.reconcile)):
            first = service.worker_cycle()
            self.assertEqual(first['job']['status'], 'READY')
            self.assertFalse(self.page.exists())
            self.assertEqual(self.jobs()[0]['site_sync_status'], 'NOT_REQUIRED')
            # Fixture for the existing ordinary Publish handler: marks the
            # card published and creates its normal page. Spec worker never
            # creates a draft page and requires no additional-spec button.
            self.sql('UPDATE cars SET published=1')
            self.page.write_text(PAGE)
            second = service.worker_cycle()
        self.assertEqual(second['job']['status'], 'PASS')
        self.assertEqual(publication.strip_block(self.page.read_text()), PAGE)
        self.assertEqual(self.page.read_text().count('data-ua-additional-spec="1"'), 1)
        collector.assert_called_once()

    def test_delete_before_collection_retires_both_queues_and_claims(self):
        service.scan_new_vins()
        claimed = service._claim()
        self.sql('DELETE FROM cars')
        self.page.unlink()
        scan = service.scan_new_vins()
        self.assertEqual(scan['retired'], 1)
        self.assert_retired(self.jobs()[0])
        self.assertEqual(service._process_claimed(claimed, enricher=lambda _: self.fail('deleted card collected'))['status'], 'STALE_DISCARDED')
        self.assertIsNone(service.sync_one(reconciler=lambda *_: self.fail('deleted card published')))
        self.assertFalse(self.page.exists())

    def test_delete_during_collection_retires_both_queues_without_storing_results(self):
        service.scan_new_vins()
        def delete(card):
            self.sql('DELETE FROM cars')
            self.page.unlink()
            return self.ready(card)
        result = service.process_one(enricher=delete)
        self.assertEqual(result['status'], 'SUPERSEDED')
        self.assert_retired(self.jobs()[0])
        self.assertEqual(service._visible_facts('UA-0016'), [])
        self.assertFalse(self.page.exists())

    def test_delete_after_ready_never_recreates_page_and_retires_collection_too(self):
        self.collect()
        facts_before = service._visible_facts('UA-0016')
        self.sql('DELETE FROM cars')
        self.page.unlink()
        result = service.sync_one(reconciler=lambda *_: self.fail('deleted card reached reconciler'))
        self.assertEqual(result['status'], 'SUPERSEDED')
        self.assert_retired(self.jobs()[0])
        self.assertEqual(service._visible_facts('UA-0016'), facts_before)
        self.assertFalse(self.page.exists())

    def test_unpublish_keeps_collected_facts_and_cancels_page_sync(self):
        self.collect()
        self.sql('UPDATE cars SET published=0')
        self.page.unlink()
        self.assertEqual(service.reconcile_published_cards(), 0)
        self.assertEqual(self.jobs()[0]['status'], 'READY')
        self.assertEqual(self.jobs()[0]['site_sync_status'], 'NOT_REQUIRED')
        self.assertIsNone(service.sync_one(reconciler=lambda *_: self.fail('unpublished card reached reconciler')))
        self.assertFalse(self.page.exists())

    def test_unpublish_during_public_verify_cannot_report_pass_or_recreate_page(self):
        self.collect()
        def unpublish(code):
            captured = self.page.read_text()
            self.sql('UPDATE cars SET published=0')
            self.page.unlink()
            return captured
        result = service.sync_one(reconciler=lambda card, facts: self.reconcile(card, facts, unpublish))
        self.assertEqual(result['status'], 'NOT_REQUIRED')
        self.assertEqual(self.jobs()[0]['status'], 'READY')
        self.assertEqual(self.jobs()[0]['site_sync_status'], 'NOT_REQUIRED')
        self.assertFalse(self.page.exists())

    def test_uid_edit_during_collection_discards_old_job_then_queues_new_uid(self):
        service.scan_new_vins()
        def edit(card):
            self.sql("UPDATE cars SET auto_number='UA-0018'")
            return self.ready(card)
        self.assertEqual(service.process_one(enricher=edit)['status'], 'SUPERSEDED')
        self.assert_retired(self.jobs()[0])
        self.assertEqual(service.scan_new_vins()['queued'], 1)
        self.assertEqual(self.jobs()[1]['car_uid'], 'UA-0018')
        self.assertEqual(service._visible_facts('UA-0016'), [])
        self.assertFalse((self.root/'video/UA-0018.html').exists())

    def test_vin_edit_during_collection_discards_old_job_and_never_publishes_it(self):
        service.scan_new_vins()
        def edit(card):
            self.sql("UPDATE cars SET vin='KNAGS416BHA000001'")
            return self.ready(card)
        self.assertEqual(service.process_one(enricher=edit)['status'], 'SUPERSEDED')
        self.assert_retired(self.jobs()[0])
        service.scan_new_vins()
        self.assertEqual(service._visible_facts('UA-0016'), [])
        self.assertIsNone(service.sync_one(reconciler=lambda *_: self.fail('stale VIN published')))

    def test_model_edit_during_collection_enters_review_without_storing_old_facts(self):
        service.scan_new_vins()
        def edit(card):
            self.sql("UPDATE cars SET model='Sportage'")
            return self.ready(card)
        self.assertEqual(service.process_one(enricher=edit)['status'], 'STALE_DISCARDED')
        self.assertEqual(service._visible_facts('UA-0016'), [])
        self.assertEqual(self.jobs()[0]['status'], 'NEEDS_REVIEW')
        self.assertEqual(self.jobs()[0]['site_sync_status'], 'NEEDS_REVIEW')

    def test_retry_same_job_does_not_duplicate_section_or_change_shell(self):
        self.collect()
        self.assertEqual(service.sync_one(reconciler=self.reconcile)['status'], 'PASS')
        before = self.page.read_bytes()
        old_id = self.jobs()[0]['id']
        service.retry_card('UA-0016')
        service.process_one(enricher=self.ready)
        result = service.sync_one(reconciler=self.reconcile)
        self.assertEqual(result['status'], 'UNCHANGED')
        self.assertEqual(len(self.jobs()), 1)
        self.assertEqual(self.jobs()[0]['id'], old_id)
        self.assertEqual(self.page.read_bytes(), before)
        self.assertEqual(publication.strip_block(self.page.read_text()), PAGE)

    def test_missing_published_page_is_not_created_by_spec_reconciler(self):
        self.collect()
        self.page.unlink()
        result = service.sync_one(reconciler=self.reconcile)
        self.assertEqual(result['status'], 'PENDING')
        self.assertIn('PUBLIC_PAGE_MISSING_OR_SYMLINK', result['detail'])
        self.assertFalse(self.page.exists())

    def test_delete_after_first_local_write_does_not_restore_deleted_pages(self):
        self.collect()
        (self.root/'site').mkdir()
        other = self.root/'site/UA-0016.html'
        other.write_text(PAGE)
        atomic = publication._atomic
        def delete_after_write(path, data):
            atomic(path, data)
            self.sql('DELETE FROM cars')
            self.page.unlink(missing_ok=True)
            other.unlink(missing_ok=True)
        with patch.object(publication, '_atomic', side_effect=delete_after_write):
            result = service.sync_one(reconciler=self.reconcile)
        self.assertEqual(result['status'], 'SUPERSEDED')
        self.assert_retired(self.jobs()[0])
        self.assertFalse(self.page.exists())
        self.assertFalse(other.exists())


if __name__ == '__main__':
    unittest.main()
