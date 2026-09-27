import concurrent.futures
from contextlib import contextmanager
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

from crm_explicit_fields import LABELS, parse
from crm_intake_store import record_source, save

MAPS = {'fuel': {'lpg': 'газ', 'gasoline': 'бензин'},
        'gearbox': {'automatic': 'автомат', 'manual': 'механика'},
        'color': {'black': 'чёрный'}, 'drive': {'fwd': 'передний'}}
PHOTO = '''Mileage 109,353 km
Registration Date 2022/00
Chassis No. KNAG541BBNA169806
Engine Capacity 1,999 cc
Color Black
Transmission Automatic
Fuel Type LPG
Auction Venue Auto Hub Auction
Auction Date 2026-07-29'''
EXPECTED = {'vin': 'KNAG541BBNA169806', 'mileage_km': 109353,
            'engine_cc': 1999, 'color': 'чёрный', 'gearbox': 'автомат', 'fuel': 'газ'}


class ParseTests(unittest.TestCase):
    def test_photo_exact_six_fields(self):
        self.assertEqual(parse(PHOTO, LABELS, MAPS)[0], EXPECTED)

    def test_registration_and_auction_are_not_car_year(self):
        self.assertEqual(parse('Registration Date 2022/00\nAuction Date 2026-07-29', LABELS, MAPS)[0], {})

    def test_label_on_previous_line(self):
        self.assertEqual(parse('Mileage\n\n109,353 km\nEngine Capacity\n1,999 cc', LABELS, MAPS)[0],
                         {'mileage_km': 109353, 'engine_cc': 1999})

    def test_label_never_consumes_next_label(self):
        self.assertEqual(parse('Mileage\nColor Black', LABELS, MAPS)[0], {'color': 'чёрный'})

    def test_conflicts_omitted(self):
        data, rejected, _ = parse(PHOTO+'\nMileage 120,000 km', LABELS, MAPS)
        self.assertNotIn('mileage_km', data)
        self.assertIn('mileage_km', rejected)

    def test_bad_grouping_and_unknown_enums_omitted(self):
        self.assertEqual(parse('Mileage 109,35 km\nEngine Capacity 1,99 cc\nColor uncertain\nFuel Type LPG or gasoline', LABELS, MAPS)[0], {})

    def test_vin_never_corrected_or_decoded(self):
        self.assertEqual(parse('VIN KNAG54IBBNA169806', LABELS, MAPS)[0], {})
        self.assertEqual(parse('VIN knag541bbna169806', LABELS, MAPS)[0], {'vin': EXPECTED['vin']})

    def test_schema_whitelist(self):
        self.assertEqual(parse(PHOTO, {'vin'}, MAPS)[0], {'vin': EXPECTED['vin']})

    def test_caption_label_normalization(self):
        self.assertEqual(parse('Марка: Kia\nМодель: K5\nГод выпуска: 2022\nДвигатель: 1.999 l', LABELS, MAPS)[0],
                         {'brand': 'Kia', 'model': 'K5', 'year': 2022, 'engine_cc': 1999})

    def test_no_cross_field_guess(self):
        self.assertEqual(parse('Model 1999\nAuction Venue Auto Hub Auction\nPrice 24500', LABELS, MAPS)[0], {'model': '1999'})


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'crm.db'
        with sqlite3.connect(self.path) as c:
            c.executescript('''
            CREATE TABLE cars (id INTEGER PRIMARY KEY, auto_number TEXT, vin TEXT,
              brand TEXT, model TEXT, year INTEGER, mileage_km INTEGER, engine_cc INTEGER,
              color TEXT, fuel TEXT, gearbox TEXT, drive TEXT, condition_text TEXT,
              photos TEXT, price_uah INTEGER, price_georgia INTEGER, status TEXT DEFAULT 'kr_bought',
              created_by INTEGER, created_at TEXT, updated_at TEXT, review_status TEXT, published INTEGER DEFAULT 0);
            CREATE TABLE inbox (id INTEGER PRIMARY KEY,from_user_id INTEGER,kind TEXT,text TEXT,file_id TEXT,
              media_group TEXT,tg_chat_id INTEGER,tg_message_id INTEGER,status TEXT,created_at TEXT,
              card_type TEXT,card_id INTEGER);
            CREATE TABLE audit (id INTEGER PRIMARY KEY,actor_id INTEGER,action TEXT,entity_type TEXT,
              entity_id INTEGER,field TEXT,old_value TEXT,new_value TEXT,created_at TEXT);
            ''')
        @contextmanager
        def connect():
            c = sqlite3.connect(self.path, timeout=3)
            c.row_factory = sqlite3.Row
            try:
                with c:
                    yield c
            finally:
                c.close()
        self.db = SimpleNamespace(connect=connect, now=lambda: '2026-09-27T07:40:00',
                                  ST_NEW='new',ST_ARCHIVED='archived', ST_APPROVED_OWNER='approved_owner')
        self.schema = SimpleNamespace(next_auto_number=lambda c: 'UA-%04d' %
                                      (c.execute('SELECT COUNT(*) FROM cars').fetchone()[0]+1))
        self.source = dict(kind='photo', chat_id=10, message_id=123, file_id='test-photo', text=None)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, data=None, msg=123, current=None):
        return save(self.db, self.schema, EXPECTED if data is None else data, 7,
                    dict(self.source, message_id=msg), current)

    def test_create_saved_unpublished_and_no_screenshot_gallery(self):
        card, changed, created = self.write()
        self.assertTrue(created)
        self.assertEqual(changed, EXPECTED)
        self.assertEqual(card['published'], 0)
        self.assertIsNone(card['photos'])
        for field in ('year','brand','model','price_uah','price_georgia'):
            self.assertIsNone(card[field])

    def test_message_replay_does_not_reapply(self):
        card, _, _ = self.write()
        again, changes, created = self.write({'vin':EXPECTED['vin'],'model':'different'})
        self.assertEqual(card, again)
        self.assertFalse(created)
        self.assertEqual(changes, {})

    def test_followup_fills_only_empty(self):
        card, _, _ = self.write()
        again, changes, created = self.write({'brand':'Kia','mileage_km':1},msg=124,current=card['id'])
        self.assertFalse(created)
        self.assertEqual(changes, {'brand':'Kia'})
        self.assertEqual(again['mileage_km'], 109353)

    def test_vin_changes_open_new_draft_without_copying_old_data(self):
        first, _, _ = self.write()
        second, _, created = self.write({'vin':'KNAG541BBNA169807'},124,first['id'])
        self.assertTrue(created)
        self.assertNotEqual(first['id'],second['id'])
        self.assertIsNone(second['mileage_km'])

    def test_normalized_existing_vin_is_reused(self):
        first, _, _ = self.write()
        with self.db.connect() as c:
            c.execute('UPDATE cars SET vin=?', ('knag541bbna-169806',))
        again, _, created = self.write(msg=125)
        self.assertEqual(first['id'],again['id'])
        self.assertFalse(created)

    def test_published_and_archived_records_not_modified(self):
        card, _, _ = self.write()
        with self.db.connect() as c:
            c.execute('UPDATE cars SET published=1,price_uah=24500,photos=?', ('["owner-photo"]',))
        again, changes, _ = self.write({'vin':EXPECTED['vin'],'model':'K5'},124)
        self.assertEqual(changes,{})
        self.assertIsNone(again['model'])
        self.assertEqual(again['photos'],'["owner-photo"]')
        self.assertEqual(again['price_uah'],24500)
        with self.db.connect() as c:
            c.execute("UPDATE cars SET published=0,review_status='archived'")
        self.assertEqual(self.write({'vin':EXPECTED['vin'],'model':'K5'},125)[1],{})

    def test_transaction_rolls_back_on_audit_failure(self):
        with self.db.connect() as c:
            c.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON audit BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.write()
        with self.db.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM cars').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM inbox').fetchone()[0],0)

    def test_concurrent_replays_create_one_card(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            results=list(executor.map(lambda _:self.write(),range(4)))
        self.assertEqual(sum(result[2] for result in results),1)
        self.assertEqual(len({result[0]['id'] for result in results}),1)

    def test_no_vin_never_creates_anonymous_car(self):
        with self.assertRaisesRegex(ValueError,'VIN_REQUIRED'):
            self.write({'model':'K5'})

    def test_admitted_source_survives_ocr_failure_and_is_linked_once(self):
        inbox = record_source(self.db, 7, self.source)
        self.assertEqual(record_source(self.db, 7, self.source), inbox)
        with self.db.connect() as c:
            self.assertIsNone(c.execute('SELECT card_id FROM inbox').fetchone()[0])
        card, _, _ = self.write()
        with self.db.connect() as c:
            rows=c.execute('SELECT id,card_id FROM inbox').fetchall()
            self.assertEqual([tuple(r) for r in rows],[(inbox,card['id'])])


if __name__ == '__main__':
    unittest.main()
