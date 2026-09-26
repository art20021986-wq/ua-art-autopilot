"""Full renderer rehearsal in a private disposable directory on the target host.

Never run this against production paths as output. Only redacted results leave
this process. New helpers are supplied as an explicit base64 payload by controller.
"""
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def validate(payload, production=Path('/home/Carix'), receipt_path=None):
    started = time.time()
    # This script runs in a separate interpreter. Its audit hook lasts until exit.
    sandbox = Path(tempfile.mkdtemp(prefix='crm-consistency-preview-', dir=production/'uploads'))
    os.chmod(sandbox, 0o700)
    protected = {}
    for p in list(production.glob('*.py')) + list((production/'video').glob('*.html')):
        protected[str(p)] = sha(p.read_bytes())
    blocked = []
    result = {'status':'FAIL', 'production_written':False, 'full_acceptance':False}
    try:
        candidates={p for pattern in ('*.py','*.json','.*.json','*.txt') for p in production.glob(pattern) if p.is_file() and p.stat().st_size<=8*1024*1024}
        if sum(p.stat().st_size for p in candidates)+(production/'crm.db').stat().st_size>128*1024*1024:
            raise RuntimeError('SHADOW_COPY_BUDGET_EXCEEDED')
        # Private local copies; no source or CRM rows are returned in the receipt.
        for pattern in ('*.py', '*.json', '.*.json', '*.txt'):
            for p in production.glob(pattern):
                if p.is_file() and p.stat().st_size <= 8*1024*1024:
                    shutil.copy2(p, sandbox/p.name)
                    os.chmod(sandbox/p.name, 0o600)
        for folder in ('video','site','archive','uploads'):
            (sandbox/folder).mkdir(exist_ok=True)
        for folder in ('video','site'):
            original = production/folder
            if original.is_dir():
                for p in original.glob('*.html'):
                    shutil.copy2(p,sandbox/folder/p.name)
        for folder in ('foto','diag'):
            source = production/'video'/folder
            if source.is_dir():
                (sandbox/'video'/folder).symlink_to(source, target_is_directory=True)
        # Existing input videos remain read-only links. Covers get an isolated dir.
        for p in (production/'video').glob('*.mp4'):
            (sandbox/'video'/p.name).symlink_to(p)
        (sandbox/'video'/'stage').mkdir()
        if (production/'video'/'stage').is_dir():
            for p in (production/'video'/'stage').iterdir():
                if p.is_file():shutil.copy2(p,sandbox/'video'/'stage'/p.name)
        src=sqlite3.connect((production/'crm.db').as_uri()+'?mode=ro',uri=True)
        dst=sqlite3.connect(sandbox/'crm.db')
        try:src.backup(dst)
        finally:dst.close();src.close()
        os.chmod(sandbox/'crm.db',0o600)
        for name,encoded in payload.items():
            if not name.endswith('.py') or Path(name).name != name:
                raise ValueError('Invalid payload path')
            (sandbox/name).write_bytes(base64.b64decode(encoded))
        sys.path.insert(0,str(sandbox))
        import build_gallery_patch
        for name in build_gallery_patch.SOURCES:
            original=(production/name).read_bytes()
            (sandbox/name).write_bytes(build_gallery_patch.build(name,original))
        import build_candidate
        build_candidate.build(production/'ua_public_freshness.py',sandbox/'ua_public_freshness.py')
        # Rewrite filesystem roots only in private source copies.
        for p in sandbox.glob('*.py'):
            source=p.read_text()
            p.write_text(source.replace(str(production),str(sandbox)))
        os.chdir(sandbox)
        os.environ['TMPDIR']=str(sandbox/'uploads')
        os.environ['XDG_CACHE_HOME']=str(sandbox/'uploads')
        sys.dont_write_bytecode=True
        real_connect=sqlite3.connect
        def restricted_connect(database,*args,**kwargs):
            path=str(database)
            resolved = Path(path.removeprefix('file:').split('?',1)[0]).resolve()
            if not (resolved.is_relative_to(sandbox) or path==':memory:'):
                blocked.append('sqlite_outside_sandbox')
                raise RuntimeError('SQLITE_OUTSIDE_SANDBOX')
            return real_connect(database,*args,**kwargs)
        sqlite3.connect=restricted_connect
        def inside(path):
            if isinstance(path,int):return True
            try:
                candidate=Path(os.fsdecode(path))
                if receipt_path is not None and candidate.absolute()==Path(receipt_path).absolute():return True
                return candidate.resolve().is_relative_to(sandbox)
            except (TypeError,ValueError):return False
        def audit(event,args):
            paths=[]
            if event=='open':
                path,mode,flags=args
                if flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):paths=[path]
            elif event in ('os.remove','os.rmdir'):
                if Path(os.fsdecode(args[0])).absolute()==sandbox:return
                paths=[Path(os.fsdecode(args[0])).absolute().parent]
            elif event in ('os.mkdir','os.chmod','os.truncate','os.utime'):
                paths=[args[0]]
            elif event in ('os.rename','os.link','os.symlink'):
                paths=list(args[:2])
            elif event=='socket.connect':
                blocked.append('network');raise RuntimeError('PREVIEW_NETWORK_BLOCKED')
            elif event in ('os.system','os.exec','os.posix_spawn'):
                blocked.append('process');raise RuntimeError('PREVIEW_PROCESS_BLOCKED')
            elif event=='subprocess.Popen':
                executable,argv=args[0],args[1]
                # ffprobe is permitted only for inspected local input, stdout output.
                allowed={'-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1'}
                if not (Path(str(executable)).name=='ffprobe' and isinstance(argv,(list,tuple))
                        and len(argv)>1 and all(str(a) in allowed for a in argv[1:-1])
                        and Path(str(argv[-1])).is_file()):
                    blocked.append('process');raise RuntimeError('PREVIEW_PROCESS_BLOCKED')
            if any(not inside(p) for p in paths):
                blocked.append(event);raise RuntimeError('PREVIEW_WRITE_OUTSIDE_SANDBOX')
        sys.addaudithook(audit)
        import publikaciya
        from public_fields import verify_core_fields
        from public_media import verify_photo_structure
        from crm_gallery import gallery_paths
        conn=sqlite3.connect(sandbox/'crm.db');conn.row_factory=sqlite3.Row
        rows=[dict(r) for r in conn.execute('SELECT * FROM cars WHERE published=1 ORDER BY id')]
        conn.close()
        checks=[]
        for row in rows:
            code=row['auto_number']
            html,diag,model=publikaciya._master(code)
            verify_core_fields(html,row)
            verify_photo_structure(html,row,gallery_paths(row,root=sandbox))
            errors=publikaciya.proverit(html,code)
            if errors:raise RuntimeError('EXISTING_RENDER_VALIDATOR_FAILED')
            checks.append({'code':code,'html_sha256':sha(html.encode()),'photos':len(gallery_paths(row,root=sandbox))})
        import publish_transaction_guard as guard
        catalog, catalog_rows=guard._build_catalog()
        guard._validate_catalog(catalog,{r['auto_number']:r for r in rows})
        if blocked:raise RuntimeError('SHADOW_ATTEMPTED_FORBIDDEN_IO')
        changes=[name for name,digest in protected.items() if sha(Path(name).read_bytes())!=digest]
        if changes:raise RuntimeError('PROTECTED_INPUT_CHANGED')
        result.update(status='PASS',cards=checks,catalog_sha256=sha(catalog.encode()),protected_files_unchanged=True)
    except Exception as error:
        result.update(error_type=type(error).__name__,blocked_io=sorted(set(blocked)))
        # Do not emit exception messages: upstream errors can contain private data.
        import traceback
        result['failure_frames']=[{'file':Path(x.filename).name,'function':x.name,'line':x.lineno}
                                  for x in traceback.extract_tb(error.__traceback__)[-6:]]
    finally:
        result['elapsed_seconds']=round(time.time()-started,2)
        result['protected_files_unchanged']=all(Path(name).is_file() and sha(Path(name).read_bytes())==digest for name,digest in protected.items())
        if not result['protected_files_unchanged']:result['status']='FAIL'
        # Remove symlinks before cleanup; never traverse linked production media.
        for folder in ('foto','diag'):
            link=sandbox/'video'/folder
            if link.is_symlink():link.unlink()
        shutil.rmtree(sandbox)
    return result
