from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = r'''#!/usr/bin/env python3
"""UA-SITE-COUNTERS-123: default read-only preflight, --apply after validation."""
import argparse
import fcntl
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

ROOT = Path('/home/Carix')
EXPECTED_PUBLISHER = 'ce6bd00338fbdc38b91f9554ea7baab3b8e921ffe6c1035aa4aba0186e2b549d'
EXPECTED_HOME = '3a8869b4da2fe58898a1237c0fea1b09d45dea80f7c61ab855c0d3a1cf739f8d'
CORE_TEXT = __CORE__
FRAGMENT = __FRAGMENT__

def sha(data):
    return hashlib.sha256(data).hexdigest()

def atomic(path,data,mode=0o600,create_only=False):
    fd,name = tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.chmod(name,mode)
        if create_only:
            try:
                os.link(name,path)
            except FileExistsError:
                if path.read_bytes() != data:
                    raise RuntimeError('Concurrent core change')
        else:
            os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)

def preflight(validate_live=True):
    publisher = ROOT/'publish_transaction_guard.py'
    before = publisher.read_bytes()
    if sha(before) != EXPECTED_PUBLISHER:
        raise RuntimeError('Publisher SHA changed; refusing overwrite')
    if sha((ROOT/'video/index.html').read_bytes()) != EXPECTED_HOME:
        raise RuntimeError('Homepage SHA changed; refusing overwrite')
    core = CORE_TEXT.encode('utf-8')
    core_path = ROOT/'ua_site_counters.py'
    if core_path.exists() and core_path.read_bytes() != core:
        raise RuntimeError('Different counter core exists')
    candidate = before+b'\n\n'+FRAGMENT.encode('utf-8')
    compile(candidate,str(publisher),'exec')
    namespace = {'__name__':'ua123_preflight'}
    exec(compile(core,str(core_path),'exec'),namespace)
    updates,counts = namespace['prepare_updates']((ROOT/'video',ROOT/'site'))
    # Cross-check catalog identities against existing CRM, without database writes.
    con = sqlite3.connect('file:'+str(ROOT/'crm.db')+'?mode=ro',uri=True)
    try:
        con.row_factory = sqlite3.Row
        rows = [dict(row) for row in con.execute('SELECT * FROM cars')]
    finally:
        con.close()
    row_map = {row['auto_number']:row for row in rows}
    records,_ = namespace['catalog_snapshot']((ROOT/'video/katalog.html').read_text())
    if not set(records) <= set(row_map):
        raise RuntimeError('Catalog identity missing from CRM')
    if validate_live:
        # This is the existing, hash-verified publisher; no publication is invoked.
        spec = importlib.util.spec_from_file_location('ua123_existing_publisher',publisher)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for path,old,new in updates:
            if path.name == 'katalog.html':
                module._validate_catalog(new.decode('utf-8'),{key:row_map[key] for key in records})
    updates.append((publisher,before,candidate))
    report = {'counts':counts,'catalog_ids':sorted(records),
        'core_sha256':sha(core),'publisher_before_sha256':sha(before),
        'publisher_after_sha256':sha(candidate),
        'files':[{'path':str(path),'before_sha256':sha(old),'after_sha256':sha(new)} for path,old,new in updates]}
    return updates,core,report

def apply(updates,core,report):
    backup = ROOT/'backups/site_counters_123'/time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
    backup.mkdir(parents=True,exist_ok=False)
    manifest = {}
    for index,(path,old,new) in enumerate(updates):
        if path.read_bytes() != old: raise RuntimeError('Source changed before backup')
        saved = str(index)+'.gz'
        atomic(backup/saved,gzip.compress(old,mtime=0))
        manifest[str(path)] = {'stored':saved,'mode':path.stat().st_mode & 0o777,
                              'before_sha256':sha(old),'after_sha256':sha(new)}
    atomic(backup/'manifest.json',json.dumps(manifest,indent=2).encode())
    written = []
    try:
        atomic(ROOT/'ua_site_counters.py',core,0o644,create_only=True)
        for path,old,new in updates:
            if path.read_bytes() != old: raise RuntimeError('Concurrent source change:'+str(path))
            if new != old:
                atomic(path,new,manifest[str(path)]['mode'])
                written.append((path,old,new))
            if path.read_bytes() != new: raise RuntimeError('Readback mismatch:'+str(path))
    except Exception:
        for path,old,new in reversed(written):
            if path.read_bytes() == new:
                atomic(path,old,manifest[str(path)]['mode'])
        raise
    return dict(report,status='INSTALLED',backup=str(backup))

def rollback(directory):
    backup = Path(directory).resolve()
    if backup.parent != (ROOT/'backups/site_counters_123').resolve():
        raise RuntimeError('Unexpected backup path')
    manifest = json.loads((backup/'manifest.json').read_text())
    originals = []
    for name,item in manifest.items():
        path = Path(name)
        if path.resolve().parent not in (ROOT.resolve(),(ROOT/'video').resolve(),(ROOT/'site').resolve()):
            raise RuntimeError('Unexpected restore target')
        old = gzip.decompress((backup/item['stored']).read_bytes())
        if sha(old) != item['before_sha256'] or sha(path.read_bytes()) != item['after_sha256']:
            raise RuntimeError('Rollback hash mismatch')
        originals.append((path,old,item['mode']))
    for path,old,mode in reversed(originals): atomic(path,old,mode)
    return {'status':'ROLLED_BACK','backup':str(backup)}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--rollback')
    args = parser.parse_args()
    if args.apply and args.rollback: raise RuntimeError('Choose apply or rollback')
    # Use the exact lock already used by publication/rebuild; never create another writer.
    with (ROOT/'.ua_art_publish_transaction.lock').open('rb') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.rollback: result = rollback(args.rollback)
        else:
            updates,core,report = preflight()
            result = apply(updates,core,report) if args.apply else dict(report,status='PREFLIGHT_OK')
        print(json.dumps(result,ensure_ascii=False))

if __name__ == '__main__': main()
'''


def build():
    core = (HERE/'markup_helpers.py').read_text()+'\nCLIENT_SCRIPT = '+repr((HERE/'counters.js').read_text())+'\n'+(HERE/'counter_core.py').read_text()
    fragment = (HERE/'publisher_fragment.py').read_text()
    compile(core,'ua_site_counters.py','exec')
    (HERE/'ua_site_counters.py').write_text(core)
    installer = TEMPLATE.replace('__CORE__',repr(core)).replace('__FRAGMENT__',repr(fragment))
    compile(installer,'home_counters_install_20260910.py','exec')
    (HERE/'home_counters_install_20260910.py').write_text(installer)


if __name__ == '__main__': build()
