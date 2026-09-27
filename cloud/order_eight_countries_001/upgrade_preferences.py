"""Two-stage preferences upgrade with exact source checks and bounded rollback.

Install backend, reload existing WSGI and client bot, verify v2 bootstrap, then
install frontend. No process/settings/database changes are made by this tool.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
from build import ROOT, patch_form
from deploy import atomic_write, write_json

BACKEND=tuple('ua_order/'+name for name in ('bindings.py','bot_flow.py','contract.py','crm.py','host.py','telegram.py','web.py','preferences.py','preferences.json','preference_summary.py'))
FRONTEND=tuple('video/order/'+name for name in ('order.js','order.css','podbor.html','preferences-state.js','preferences-form.js'))+('video/podbor.html',)
FILES=BACKEND+FRONTEND
NEW={'ua_order/preferences.py','ua_order/preferences.json','ua_order/preference_summary.py','video/order/preferences-state.js','video/order/preferences-form.js'}


def sha(raw):return hashlib.sha256(raw).hexdigest()


def safe_path(base,name):
    if name not in FILES:raise ValueError('Unapproved target: '+name)
    path=base/name
    if any(p.is_symlink() for p in (path,*path.parents)) or not path.resolve().is_relative_to(base.resolve()):raise ValueError('Symlink or escaped target: '+name)
    return path


def current_hash(path):return sha(path.read_bytes()) if path.is_file() else None


def prepare(baseline,output):
    baseline=Path(baseline).resolve();output=Path(output).resolve()
    if output.exists() or str(output).startswith('/home/Carix') or not baseline.is_dir():raise ValueError('Use a reviewed baseline and fresh local bundle directory')
    if not all((baseline/name).is_file() for name in FILES if name not in NEW):raise ValueError('Baseline is incomplete')
    output.mkdir(parents=True)
    manifest={'task':'UA-ART-ORDER-PREFERENCES-001','version':'1.2','files':{}}
    for name in FILES:
        source=ROOT/name if name.startswith('ua_order/') else ROOT/'web'/Path(name).name
        raw=patch_form((baseline/name).read_text()).encode() if name=='video/podbor.html' else source.read_bytes()
        target=output/'files'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        old=safe_path(baseline,name)
        manifest['files'][name]={'before':current_hash(old),'after':sha(raw),'mode':old.stat().st_mode&0o777 if old.exists() else 0o644}
    write_json(output/'manifest.json',manifest)
    return {'bundle':str(output),'manifest_sha256':sha((output/'manifest.json').read_bytes()),'files':len(FILES),'production_write':False}


def load_manifest(bundle,expected):
    raw=(bundle/'manifest.json').read_bytes()
    if sha(raw)!=expected:raise ValueError('Unreviewed manifest')
    manifest=json.loads(raw)
    if manifest.get('task')!='UA-ART-ORDER-PREFERENCES-001' or set(manifest.get('files',{}))!=set(FILES):raise ValueError('Unexpected release file set')
    for name,entry in manifest['files'].items():
        if current_hash(safe_path(bundle/'files',name))!=entry['after']:raise ValueError('Bundle changed: '+name)
    return manifest


def install(base,bundle,backup,expected,stage):
    if stage not in ('backend','frontend'):raise ValueError('Unknown installation stage')
    manifest=load_manifest(bundle,expected);names=BACKEND if stage=='backend' else FRONTEND
    if stage=='backend':
        if backup.exists():raise ValueError('Use a fresh private backup')
        for name,entry in manifest['files'].items():
            if current_hash(safe_path(base,name))!=entry['before']:raise ValueError('Live source changed: '+name)
        backup.mkdir(mode=0o700,parents=False)
        for name,entry in manifest['files'].items():
            if entry['before'] is not None:
                path=backup/'files'/name;path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                atomic_write(path,(base/name).read_bytes(),0o600)
        write_json(backup/'manifest.json',manifest)
        write_json(backup/'status.json',{'stage':'prepared','manifest_sha256':expected})
    else:
        status=json.loads((backup/'status.json').read_text())
        if status!={'stage':'backend_installed','manifest_sha256':expected}:raise ValueError('Install and verify backend before frontend')
        if sha((backup/'manifest.json').read_bytes())!=expected:raise ValueError('Backup manifest mismatch')
        for name in BACKEND:
            if current_hash(safe_path(base,name))!=manifest['files'][name]['after']:raise ValueError('Backend changed: '+name)
    for name in names:
        if current_hash(safe_path(base,name))!=manifest['files'][name]['before']:raise ValueError('Concurrent source change: '+name)
    if stage=='frontend':write_json(backup/'status.json',{'stage':'frontend_publishing','manifest_sha256':expected})
    try:
        for name in names:
            entry=manifest['files'][name];target=safe_path(base,name)
            if current_hash(target)!=entry['before']:raise ValueError('Concurrent source change: '+name)
            atomic_write(target,(bundle/'files'/name).read_bytes(),entry['mode'])
        write_json(backup/'status.json',{'stage':stage+'_installed','manifest_sha256':expected})
    except BaseException:
        rollback(base,backup,expected)
        raise
    return {'stage':stage+'_installed','backup':str(backup),'reload_required':stage=='backend'}


def rollback(base,backup,expected):
    raw=(backup/'manifest.json').read_bytes()
    if sha(raw)!=expected:raise ValueError('Backup manifest mismatch')
    manifest=json.loads(raw)
    if set(manifest['files'])!=set(FILES):raise ValueError('Unexpected rollback targets')
    for name,entry in manifest['files'].items():
        if current_hash(safe_path(base,name)) not in (entry['before'],entry['after']):raise ValueError('Later change prevents rollback: '+name)
        if entry['before'] is not None and current_hash(safe_path(backup/'files',name))!=entry['before']:raise ValueError('Backup changed: '+name)
    status=json.loads((backup/'status.json').read_text())
    keep_backend=status['stage'] in ('frontend_publishing','frontend_installed','frontend_rolled_back')
    targets=tuple(reversed(FRONTEND)) if keep_backend else (*reversed(FRONTEND),*BACKEND)
    for name in targets:
        entry=manifest['files'][name];target=safe_path(base,name)
        if entry['before'] is None:target.unlink(missing_ok=True)
        else:atomic_write(target,(backup/'files'/name).read_bytes(),entry['mode'])
    stage='frontend_rolled_back' if keep_backend else 'rolled_back'
    write_json(backup/'status.json',{'stage':stage,'manifest_sha256':expected})
    return {'stage':stage,'reload_required':not keep_backend,'compatible_backend_retained':keep_backend}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('prepare','install','rollback'))
    parser.add_argument('--baseline');parser.add_argument('--output');parser.add_argument('--bundle');parser.add_argument('--backup');parser.add_argument('--manifest-sha256');parser.add_argument('--stage',choices=('backend','frontend'))
    args=parser.parse_args()
    if args.action=='prepare':result=prepare(args.baseline,args.output)
    else:
        base=Path('/home/Carix');backup=Path(args.backup).resolve()
        if backup.parent!=base or not backup.name.startswith('order_preferences_backup_'):raise ValueError('Use a private /home/Carix/order_preferences_backup_* path')
        if not args.manifest_sha256:raise ValueError('Pass the reviewed manifest hash')
        with (base/'order_install.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if args.action=='install':result=install(base,Path(args.bundle).resolve(),backup,args.manifest_sha256,args.stage)
            else:result=rollback(base,backup,args.manifest_sha256)
    print(json.dumps(result,indent=2))
