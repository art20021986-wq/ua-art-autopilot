#!/usr/bin/env python3
"""MVS register source: both register layouts, CRM codes, the index build, the daily job, and the source order.

Rows are copied from the real registers (reestrtz31.12.2025.csv, registeredvehicles.csv, 2026-11-17). ua_vin_lots
and ua_vin_pattern are the installed modules (cloud/crm_new_car_vin_003/_004, hashes pinned); ai_filter and
ai_fast_schema are the exact installed modules (CRM-PHOTO-AUTOFILL-001 test helper).
"""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.append(str(ROOT / 'cloud/crm_new_car_vin_003'))  # installed ua_vin_lots
sys.path.append(str(ROOT / 'cloud/crm_new_car_vin_004'))  # installed ua_vin_pattern
import candidate_builder  # noqa: E402
import ua_vin_decode as decode  # noqa: E402
import ua_vin_lots as lots  # noqa: E402
import ua_vin_mvs as mvs  # noqa: E402

YEARLY_CSV = ('"PERSON";"REG_ADDR_KOATUU";"OPER_CODE";"OPER_NAME";"D_REG";"DEP_CODE";"DEP";"BRAND";"MODEL";"VIN";'
              '"MAKE_YEAR";"COLOR";"KIND";"BODY";"PURPOSE";"FUEL";"CAPACITY";"OWN_WEIGHT";"TOTAL_WEIGHT";"N_REG_NEW"\n'
              '"P";"6310138200";"254";"Р";01.01.25;10000;"D";"LEXUS";"IS 250";"JTHCK262882026114";2008;"ЧЕРВОНИЙ";'
              '"ЛЕГКОВИЙ";"СЕДАН";"ЗАГАЛЬНИЙ";"БЕНЗИН";2499;2075;2575;"АХ1312КК"\n'
              '"P";"8000000000";"254";"Р";01.01.25;10000;"D";"TOYOTA";"RAV-4 HYBRID";"JTMW23FVX0D106165";2021;"БІЛИЙ";'
              '"ЛЕГКОВИЙ";"УНІВЕРСАЛ";"ЗАГАЛЬНИЙ";"ЕЛЕКТРО АБО БЕНЗИН";2487;1755;2135;"КА5010НС"\n'
              '"P";"1";"1";"Р";01.01.25;1;"D";"X";"Y";"SHORT";2020;"";"";"";"";"";0;0;0;""\n')
CURRENT_CSV = ('"koatuu","person","operCodeOperas","dReg","dep","brand","model","vin","makeYear","color","kind","purpose",'
               '"body","fuel","capacity","powerKwt","ownWeight","totalWeight"\n'
               '"5110136900","P","50","2026-01-01","1","BMW","X6","WBAKV210300R24692",2015,"БІЛИЙ","ЗАГАЛЬНИЙ","ЛЕГКОВИЙ",'
               '"УНІВЕРСАЛ","ДИЗЕЛЬНЕ ПАЛИВО","2993","","2140","3000"\n'
               '"6310136300","P","540","2026-01-01","1","BYD","F-3R","LGXC14DF7D0006970",2013,"БІЛИЙ","ЗАГАЛЬНИЙ",'
               '"ЛЕГКОВИЙ","ХЕТЧБЕК","БЕНЗИН АБО ГАЗ","1488","","1170","1575"\n'
               '"8000000000","P","1","2026-02-01","1","LEXUS","IS 250","JTHCK262882026114",2008,"СІРИЙ","ЗАГАЛЬНИЙ",'
               '"ЛЕГКОВИЙ","СЕДАН","БЕНЗИН","2499","","2075","2575"\n')


def zipped(text):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as archive:
        archive.writestr('reestrtz31.12.2025.csv', text)
    return out.getvalue()


class FakeWeb:
    """data.gov.ua: two CKAN datasets and their files; records the client name of every request."""
    def __init__(self):
        self.agents = []
        self.files = {'https://x/2020.zip': zipped(YEARLY_CSV.replace('JTHCK', 'AAAAA')),
                      'https://x/2025.zip': zipped(YEARLY_CSV), 'https://x/current.csv': CURRENT_CSV.encode()}

    def __call__(self, request, timeout):
        self.agents.append(request.get_header('User-agent'))
        url = request.full_url
        if url.endswith(mvs.YEARLY):
            items = [{'name': 'reestrTZ2020', 'url': 'https://x/2020.zip'},
                     {'name': 'reestrTZ2025', 'url': 'https://x/2025.zip'}]
        elif url.endswith(mvs.CURRENT):
            items = [{'name': 'registeredVehicles', 'url': 'https://x/current.csv'}]
        else:
            return io.BytesIO(self.files[url])
        return io.BytesIO(json.dumps({'result': {'resources': items}}).encode())


class RegisterTests(unittest.TestCase):
    def test_both_layouts_and_short_vins_skipped(self):
        rows = list(mvs.records(YEARLY_CSV.splitlines())) + list(mvs.records(CURRENT_CSV.splitlines()))
        self.assertEqual([r['vin'] for r in rows], ['JTHCK262882026114', 'JTMW23FVX0D106165', 'WBAKV210300R24692',
                                                    'LGXC14DF7D0006970', 'JTHCK262882026114'])
        self.assertNotIn('АХ1312КК', json.dumps(rows, ensure_ascii=False))  # plates and owners are not kept

    def test_crm_codes(self):
        rows = {r['vin']: r for r in mvs.records(YEARLY_CSV.splitlines())}
        self.assertEqual(mvs.raw_fields(rows['JTMW23FVX0D106165']),
                         {'model': 'RAV-4 HYBRID', 'year': 2021, 'engine_cc': 2487, 'fuel': 'hybrid', 'color': 'білий'})
        ambiguous = next(r for r in mvs.records(CURRENT_CSV.splitlines()) if r['vin'] == 'LGXC14DF7D0006970')
        self.assertNotIn('fuel', mvs.raw_fields(ambiguous))  # «БЕНЗИН АБО ГАЗ» is not guessed

    def test_build_from_2021_on_newest_wins_and_client_name(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        web = FakeWeb()
        index = Path(temp.name) / 'mvs.sqlite3'
        self.assertEqual(mvs.build(index, web), 4)
        self.assertIsNone(mvs.lookup('AAAAA262882026114', index))  # 2020: before the VIN years
        self.assertEqual(mvs.lookup('JTHCK262882026114', index)['color'], 'СІРИЙ')  # the current register wins
        self.assertEqual(set(web.agents), {'uaart-crm-vin/1'})
        self.assertEqual(list(Path(temp.name).iterdir()), [index])  # downloads and the .new file are gone

    def test_empty_register_keeps_the_old_index(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        index = Path(temp.name) / 'mvs.sqlite3'
        index.write_bytes(b'old')
        web = FakeWeb()
        web.files = {url: zipped('"VIN"\n') if url.endswith('.zip') else b'"vin"\n' for url in web.files}
        with self.assertRaisesRegex(ValueError, 'EMPTY_REGISTER'):
            mvs.build(index, web)
        self.assertEqual(index.read_bytes(), b'old')

    def test_stale_and_lookup_without_index(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        index = Path(temp.name) / 'mvs.sqlite3'
        self.assertTrue(mvs.stale(index))
        self.assertIsNone(mvs.lookup('JTHCK262882026114', index))
        index.write_bytes(b'')
        self.assertFalse(mvs.stale(index))
        self.assertTrue(mvs.stale(index, now=time.time() + mvs.MAX_AGE + 1))

    def test_daily_job_scheduled_once_and_starts_a_low_priority_process(self):
        class Queue:
            def __init__(self):
                self.jobs = []

            def get_jobs_by_name(self, name):
                return [j for j in self.jobs if j[1] == name]

            def run_repeating(self, callback, interval, first, name):
                self.jobs.append((interval, name, callback))
        app = type('App', (), {'job_queue': Queue()})()
        mvs.schedule(app)
        mvs.schedule(app)
        self.assertEqual([(i, n) for i, n, _ in app.job_queue.jobs], [(86400, 'vin-mvs-refresh')])
        import asyncio
        with patch.object(mvs, 'stale', return_value=True), patch('subprocess.Popen') as popen:
            asyncio.run(app.job_queue.jobs[0][2](None))
        self.assertEqual(popen.call_args.args[0][:3], ['nice', '-n', '19'])
        self.assertEqual(popen.call_args.args[0][-1], 'refresh')
        with patch.object(mvs, 'stale', return_value=False), patch('subprocess.Popen') as popen:
            asyncio.run(app.job_queue.jobs[0][2](None))
        popen.assert_not_called()


def photo_helper():
    own = {name: sys.modules.pop(name) for name in ('candidate_builder', 'release_constants') if name in sys.modules}
    sys.path.insert(0, str(ROOT / 'cloud/crm_photo_card_001'))
    try:
        import test_photo_card
    finally:
        sys.path.pop(0)
        sys.modules.update(own)
    return test_photo_card


def vpic(row):
    def opener(url, timeout):
        return io.BytesIO(json.dumps({'Results': [row]}).encode())
    return opener


class OrderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        patcher, _ = photo_helper().crm_modules(self.dir)
        self.addCleanup(patcher.stop)
        self.index = self.dir / 'mvs.sqlite3'
        mvs.build(self.index, FakeWeb())
        (self.dir / 'lots.json').write_text(json.dumps({'lots': []}))
        for module, name, value in ((mvs, 'INDEX', self.index), (lots, 'LOTS', self.dir / 'lots.json'),
                                    (lots, 'ARCHIVE', self.dir / 'archive.sqlite3')):
            p = patch.object(module, name, value)
            p.start()
            self.addCleanup(p.stop)

    def test_register_then_vpic_for_what_is_missing(self):
        got = decode.fields('JTMW23FVX0D106165', vpic({'ErrorCode': '0', 'Model': 'RAV4', 'DriveType': 'AWD/All-Wheel Drive',
                                                       'TransmissionStyle': 'Continuously Variable Transmission (CVT)'}))
        self.assertEqual(got, {'model': 'RAV-4 HYBRID', 'year': 2021, 'engine_cc': 2487, 'fuel': 'гибрид',
                               'color': 'белый', 'gearbox': 'вариатор', 'drive': 'полный'})

    def test_lot_wins_over_the_register(self):
        (self.dir / 'lots.json').write_text(json.dumps({'lots': [{
            'vin': 'JTMW23FVX0D106165', 'title': 'Toyota RAV4', 'maker': 'Toyota', 'year': 2022, 'engine_cc': 2500,
            'mileage_km': 10000, 'fuel': 'hybrid', 'transmission': 'AT'}]}))
        got = decode.fields('JTMW23FVX0D106165', vpic({'ErrorCode': '1'}))
        self.assertEqual((got['model'], got['year'], got['color']), ('RAV4', 2022, 'белый'))

    def test_register_alone_when_vpic_rejects(self):
        self.assertEqual(decode.fields('JTHCK262882026114', vpic({'ErrorCode': '1'})),
                         {'model': 'IS 250', 'year': 2008, 'engine_cc': 2499, 'fuel': 'бензин', 'color': 'серый'})


class BuilderTests(unittest.TestCase):
    def test_pins(self):
        for folder, name, table in (('cloud/crm_new_car_vin_004', 'ua_vin_decode.py', candidate_builder.SOURCE_SHA256),
                                    ('cloud/crm_new_car_vin_003', 'ua_new_car_bot.py', candidate_builder.SOURCE_SHA256),
                                    ('cloud/crm_new_car_vin_003', 'ua_vin_lots.py', candidate_builder.DEPENDENCY_SHA256),
                                    ('cloud/crm_new_car_vin_004', 'ua_vin_pattern.py', candidate_builder.DEPENDENCY_SHA256)):
            self.assertEqual(hashlib.sha256((ROOT / folder / name).read_bytes()).hexdigest(), table[name], name)

    def test_refuses_drift(self):
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            candidate_builder.build({'ua_vin_decode.py': b'x', 'ua_new_car_bot.py': b'y'}, {})


if __name__ == '__main__':
    unittest.main()
