#!/usr/bin/env python3
"""Use verified CRM identifiers and model-compatible requests without changing CRM data."""
from __future__ import annotations
import sys
import sqlite3
import types
from pathlib import Path
import task096_recovery10 as recovery
import task096_sonnet5_compat as api_compat

EXTRA_SAFE_NAMES = {'auto_number','komplektaciya','korobka','drivetrain','power_hp','color_exterior','color_interior'}
recovery.SAFE_NAMES.update(EXTRA_SAFE_NAMES)
_original_patch = recovery.patch_remote
_original_load = recovery.load_legacy


def load_compatible_legacy():
    mod = api_compat.install(_original_load(), recovery.ROOT)
    api_compat.selftest(mod)
    return mod


recovery.load_legacy = load_compatible_legacy


def patch_actual_schema(text):
    text = _original_patch(text)
    text = recovery.replace_function(text, 'detect_uid_column', '''
def detect_uid_column(conn, columns):
    # auto_number is the physical column verified by the original TASK096
    # backup controller. Never infer card identity from a numeric row index.
    preferred = ['auto_number','car_uid','uid','code','car_code','public_id','public_code','card_id','car_id','internal_id','slug','id']
    actual = {column.lower():column for column in columns}
    for key in preferred:
        column = actual.get(key)
        if not column or norm_key(column) not in RECOVERY_SAFE_CAR_NAMES:
            continue
        quoted = '"' + column.replace('"','""') + '"'
        rows = conn.execute('SELECT ' + quoted + ' FROM cars WHERE ' + quoted + ' IS NOT NULL LIMIT 80').fetchall()
        if rows and all(canonical_uid(row[0]) is not None for row in rows):
            return column
    raise RuntimeError('CAR_UID_COLUMN_NOT_FOUND')
''')
    text = recovery.replace_function(text, 'safe_context_value', '''
def safe_context_value(column, value):
    key = norm_key(column)
    if key not in RECOVERY_SAFE_CAR_NAMES or value is None or str(value).strip() == '':
        return None
    aliases = {'auto_number':'car_uid','marka':'make','brand':'make','god':'year',
               'kuzov':'body_type','probeg':'mileage','komplektaciya':'trim',
               'toplivo':'fuel_type','korobka':'transmission','kpp':'transmission',
               'privod':'drive_type','drivetrain':'drive_type','obem':'engine_displacement',
               'engine_volume':'engine_displacement','volume':'engine_displacement',
               'cvet':'color_exterior','color':'color_exterior','power':'power_hp'}
    key = aliases.get(key,key)
    if key in ('vin','vin_code'):
        vin = re.sub(r'[^A-Za-z0-9]','',str(value).upper())
        return ('vin_hint',{'wmi':vin[:3],'last4':vin[-4:],'length':len(vin)}) if len(vin)==17 else None
    text = str(value).strip()
    if CURRENCY_RE.search(text):
        return None
    return key,text[:300]
''')
    compile(text,'remote_apply_actual_schema.py','exec')
    return text


recovery.patch_remote = patch_actual_schema


def selftest_actual_schema():
    recovery.selftest()
    source = (recovery.OUT / 'remote_apply.py').read_text(encoding='utf-8')
    patched = patch_actual_schema(source)
    remote = types.ModuleType('remote_schema_test')
    exec(compile(patched,'remote_schema_test.py','exec'),remote.__dict__)
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE cars(id INTEGER,auto_number TEXT,marka TEXT,model TEXT,purchase_price TEXT)')
    db.execute("INSERT INTO cars VALUES(15,'UA-0015','SyntheticMake','SyntheticModel','FORBIDDEN_SENTINEL')")
    db.commit()
    db.set_authorizer(remote.recovery_authorizer)
    assert remote.detect_uid_column(db,remote.cars_columns(db)) == 'auto_number'
    assert remote.safe_context_value('marka','SyntheticMake') == ('make','SyntheticMake')
    assert remote.safe_context_value('purchase_price','FORBIDDEN_SENTINEL') is None
    assert 'purchase_price' not in remote.cars_snapshot(db)['rows'][0]
    try:
        db.execute("UPDATE cars SET model='changed'")
    except sqlite3.DatabaseError:
        pass
    else:
        raise RuntimeError('PRIMARY_WRITE_GUARD_FAILED')
    recovery.load_legacy()
    print('TASK096_AUTO_NUMBER_SCHEMA_TEST_PASS',flush=True)


if __name__ == '__main__':
    selftest_actual_schema()
    if '--selftest' not in sys.argv:
        raise SystemExit(recovery.main())
