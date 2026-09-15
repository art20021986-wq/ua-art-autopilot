#!/usr/bin/env python3
"""Read-only facts for PR114; never emits a writer PASS or inferred identity.

Run only through the existing authenticated Carix route. No deployed imports,
network, credentials, lock acquisition, source changes or database writes.
"""
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

ROOT = Path('/home/Carix')
NAMED_SOURCES = ('cars_ui.py','team_bot.py','db.py','cars_schema.py',
    'start_safe.py','run_all.py','yadro.py','stranica.py','master_card.py',
    'publikaciya.py','publish_transaction_guard.py','ua_stage_catalog_sync.py',
    'catalog_design_guard.py','analitika_wsgi.py','uaart_bridge_wsgi.py',
    'uaart_price_sync_runtime.py','uaart_price_control_reader.py')
CALL_TERMS = ('flock','lock','publish','write','replace','rename','unlink',
    'commit','execute','who','get_staff','permission','can_edit')

def fact(path):
    value = {'path': str(path), 'exists': path.exists(), 'symlink': path.is_symlink()}
    if not value['exists'] or value['symlink']:
        return value
    info = path.lstat()
    value.update(mode=oct(stat.S_IMODE(info.st_mode)), uid=info.st_uid,
                 size=info.st_size, modified_ns=info.st_mtime_ns)
    if not stat.S_ISREG(info.st_mode) or info.st_size > 4*1024*1024:
        value['inspection'] = 'METADATA_ONLY'
        return value
    raw = path.read_bytes()
    value['sha256'] = hashlib.sha256(raw).hexdigest()
    if path.suffix != '.py':
        return value
    try:
        tree = ast.parse(raw)
    except (SyntaxError, ValueError, UnicodeDecodeError):
        value['syntax'] = 'UNPARSEABLE'
        return value
    functions=[]
    for node in ast.walk(tree):
        if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            continue
        calls=set()
        for child in ast.walk(node):
            if isinstance(child,ast.Call):
                func=child.func
                name=func.id if isinstance(func,ast.Name) else func.attr if isinstance(func,ast.Attribute) else ''
                if any(term in name.lower() for term in CALL_TERMS):
                    calls.add(name)
        if calls or node.name in ('who','get_staff','_storozh'):
            functions.append({'function':node.name,'line':node.lineno,'calls':sorted(calls)})
    value['relevant_functions']=functions
    return value

def main():
    if Path.home()!=ROOT or ROOT.is_symlink() or not ROOT.is_dir():
        raise SystemExit('AUTHENTICATED_CARIX_HOST_REQUIRED')
    result={'contract':'PR114-READONLY-WRITER-IDENTITY-FACTS-1',
        'observed_at':datetime.now(timezone.utc).isoformat(),
        'production_written':False,'network_used':False,'credentials_read':False,
        'writer_verdict':'NOT_EVALUATED','sources':[], 'crm_processes':[],
        'remaining':['Authenticated Always-On, scheduled-task, console and WSGI worker provenance',
            'Complete writer reachability and loaded-source/fence evidence',
            'Independent existing authenticated bot/private-chat evidence',
            'Current existing edit ACL and actual allowed chat scope review']}
    for name in NAMED_SOURCES:
        try:result['sources'].append(fact(ROOT/name))
        except OSError as exc:result['sources'].append({'path':str(ROOT/name),'error_type':type(exc).__name__})
    result['analitika_stop']=fact(ROOT/'analitika_stop.txt')
    database=ROOT/'crm.db'
    if database.is_symlink() or not database.is_file():
        raise SystemExit('REGULAR_EXISTING_CRM_DATABASE_REQUIRED')
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=1) as conn:
        columns=[row[1] for row in conn.execute('PRAGMA table_info(staff)')]
        result['staff_columns']=columns
        if {'user_id','role','active'} <= set(columns):
            result['current_staff']=[{'user_id':r[0],'role':r[1],'active':r[2]}
                for r in conn.execute('SELECT user_id,role,active FROM staff ORDER BY user_id')]
        else:result['staff_status']='EXACT_STAFF_FIELDS_UNAVAILABLE'
        result['published_identities']=[list(r) for r in conn.execute(
            'SELECT id,auto_number FROM cars WHERE published=1 ORDER BY auto_number,id')]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            if proc.stat().st_uid!=os.geteuid():continue
            argv=(proc/'cmdline').read_bytes().split(b'\0')
            matches=sorted({name for name in ('start_safe.py','run_all.py','team_bot.py','uaart_price_control_reader.py')
                if any(item==str(ROOT/name).encode() or item==name.encode() for item in argv)})
            if matches:result['crm_processes'].append({'pid':int(proc.name),'known_entry_names':matches})
        except OSError:continue
    result['crm_processes'].sort(key=lambda v:v['pid'])
    result['finished_at']=datetime.now(timezone.utc).isoformat()
    print(json.dumps(result,sort_keys=True,ensure_ascii=True,indent=2))

if __name__=='__main__':
    main()
