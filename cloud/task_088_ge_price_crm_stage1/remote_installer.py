#!/usr/bin/env python3
"""Bounded TASK088 CRM installer; exact per-execution plan and receipts required."""
from __future__ import annotations
import argparse, fcntl, hashlib, json, os, pathlib, re, sqlite3, stat, tempfile
from ui_patch import patch_text, verify_candidate_runtime
from db_verification import backup_sqlite, verify_price_roundtrip, VerificationError

TASK_ID = 'TASK088-GE-PRICE-CRM-STAGE1'
ROOT = pathlib.Path('/home/Carix')
HERE = pathlib.Path(__file__).resolve().parent
HASH = re.compile(r'[0-9a-f]{64}\Z')

class InstallError(RuntimeError): pass

def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))+'\n').encode()

def sha(data): return hashlib.sha256(data).hexdigest()

def atomic(path, data, mode=0o600):
    fd, raw = tempfile.mkstemp(dir=path.parent)
    temporary = pathlib.Path(raw)
    try:
        with os.fdopen(fd, 'wb') as target:
            target.write(data); target.flush(); os.fsync(target.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally: temporary.unlink(missing_ok=True)

def regular(path):
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.is_symlink() or info.st_nlink != 1:
        raise InstallError('UNSAFE_FILE:'+path.name)
    if info.st_size > 16*1024*1024: raise InstallError('FILE_SIZE:'+path.name)
    return path.read_bytes(), stat.S_IMODE(info.st_mode)

class Installer:
    def __init__(self, root, work, identity, plan):
        self.root, self.work = pathlib.Path(root), pathlib.Path(work)
        self.identity, self.plan = dict(identity), dict(plan)
        self.source, self.db = self.root/'cars_ui.py', self.root/'crm.db'
        self.state_path=self.work/'state.json'
        for key in ('source_before_sha256','source_after_sha256'):
            if not HASH.fullmatch(str(self.plan.get(key,''))):
                raise InstallError('PINNED_PLAN_REQUIRED:'+key)
        if type(self.plan.get('test_car_id')) is not int: raise InstallError('EXPLICIT_TEST_CAR_REQUIRED')
        paths=self.plan.get('protected_paths')
        if not isinstance(paths,list) or not paths: raise InstallError('PROTECTED_SITE_PATHS_REQUIRED')
        self.protected=[]
        for raw in paths:
            path=pathlib.Path(raw)
            if (not path.is_absolute() or not path.is_relative_to(self.root) or '..' in path.parts
                    or path in (self.source,self.db,self.root) or path.resolve()!=path):
                raise InstallError('PROTECTED_PATH_SCOPE')
            self.protected.append(path)

    def protected_snapshot(self):
        result={}
        for path in self.protected:
            if path.is_symlink() or not path.exists(): raise InstallError('PROTECTED_PATH_MISSING_OR_SYMLINK')
            files=[path] if path.is_file() else sorted(path.rglob('*'))
            for item in files:
                if item.is_symlink(): raise InstallError('PROTECTED_SYMLINK')
                if item.is_file():
                    data,mode=regular(item)
                    result[str(item)]={'sha256':sha(data),'mode':mode}
        if not result: raise InstallError('EMPTY_PROTECTED_SNAPSHOT')
        return result

    def state(self, expected):
        value=json.loads(regular(self.state_path)[0])
        if any(value.get(k)!=v for k,v in self.identity.items()): raise InstallError('STATE_IDENTITY')
        if value.get('backup_manifest_sha256')!=expected: raise InstallError('BACKUP_IDENTITY')
        if value['plan']!=self.plan: raise InstallError('PLAN_DRIFT')
        return value

    def save(self,state): atomic(self.state_path,canonical(state))

    def candidate(self,original):
        text,metadata=patch_text(original.decode())
        candidate=text.encode(); compile(candidate,str(self.source),'exec')
        if sha(candidate)!=self.plan['source_after_sha256']: raise InstallError('CANDIDATE_SHA_MISMATCH')
        proof=verify_candidate_runtime(text)
        if proof.get('status')!='PASS': raise InstallError('CALLBACK_PREFLIGHT_NOT_VERIFIED:'+str(proof))
        return candidate,metadata,proof

    def backup(self):
        original,mode=regular(self.source)
        if sha(original)!=self.plan['source_before_sha256']: raise InstallError('LIVE_SOURCE_DRIFT')
        candidate,metadata,ui=self.candidate(original)
        protected=self.protected_snapshot()
        backup=self.work/'backup'; backup.mkdir(exist_ok=False)
        atomic(backup/'cars_ui.py',original,mode)
        backup_sqlite(self.db,backup/'crm.db')
        shadow=backup/'verification.db'; backup_sqlite(backup/'crm.db',shadow)
        with sqlite3.connect(shadow) as c:
            cols={r[1] for r in c.execute('PRAGMA table_info(cars)')}
            if 'price_georgia' not in cols: c.execute('ALTER TABLE cars ADD COLUMN price_georgia INTEGER')
        shadow_proof=verify_price_roundtrip(shadow,self.plan['test_car_id'])
        manifest=dict(self.identity,files={'cars_ui.py':sha(original),'crm.db':sha((backup/'crm.db').read_bytes())},
                      protected=protected,plan=self.plan)
        digest=sha(canonical(manifest)); atomic(backup/'manifest.json',canonical(manifest))
        state=dict(self.identity,backup_manifest_sha256=digest,plan=self.plan,protected=protected,
                   source_mode=mode,status='BACKED_UP',source_changed=False,column_added=False,
                   shadow_proof=shadow_proof,patch_metadata=metadata,backup=str(backup))
        self.save(state)
        return dict(backup=str(backup),backup_manifest_sha256=digest,shadow_db=shadow_proof,
                    live_db='NOT_WRITTEN',ui_callbacks=ui,ui_runtime='NOT_VERIFIED')

    def install(self,expected):
        state=self.state(expected)
        if state['status']!='BACKED_UP': raise InstallError('INSTALL_STATE')
        original,mode=regular(self.source)
        if sha(original)!=self.plan['source_before_sha256']: raise InstallError('LIVE_SOURCE_DRIFT')
        if self.protected_snapshot()!=state['protected']: raise InstallError('PROTECTED_DRIFT')
        candidate,metadata,ui=self.candidate(original)
        if self.root == ROOT and ui.get('live_bot_verified') is not True:
            raise InstallError('LIVE_BOT_ACCEPTANCE_NOT_CONFIGURED')
        try:
            with sqlite3.connect(self.db,timeout=10) as c:
                c.execute('BEGIN IMMEDIATE')
                cols={r[1] for r in c.execute('PRAGMA table_info(cars)')}
                if 'price_uah' not in cols: raise InstallError('UKRAINE_COLUMN_MISSING')
                if 'price_georgia' not in cols:
                    # Record intended schema change before commit for crash recovery.
                    state['column_added']=True; self.save(state)
                    c.execute('ALTER TABLE cars ADD COLUMN price_georgia INTEGER')
            dbproof=verify_price_roundtrip(self.db,self.plan['test_car_id'])
            if dbproof.get('status')!='PASS' or dbproof.get('restoration_needed'):
                raise InstallError('DB_PROOF_FAILED')
            if sha(regular(self.source)[0])!=self.plan['source_before_sha256']:
                raise InstallError('SOURCE_CONCURRENT_CHANGE')
            if self.protected_snapshot()!=state['protected']: raise InstallError('PROTECTED_DRIFT')
            state['source_changed']=True; self.save(state)
            atomic(self.source,candidate,mode)
            if regular(self.source)[0]!=candidate: raise InstallError('SOURCE_READBACK')
            state.update(status='INSTALLED',db_proof=dbproof,ui_callbacks=ui)
            self.save(state)
        except Exception as failure:
            if isinstance(failure, VerificationError):
                state['db_failure_details'] = failure.details
                self.save(state)
            # Do not overwrite the database backup: verifier restores only its
            # test fields or leaves a durable recovery journal if a writer raced.
            try: self.rollback(expected)
            except Exception as recovery_error:
                state['recovery_error']=str(recovery_error); self.save(state)
            raise
        return dict(backup=state['backup'],backup_manifest_sha256=expected,
                    db=self.normalized_db(dbproof),ui_callbacks=ui,ui_runtime='NOT_VERIFIED')

    @staticmethod
    def normalized_db(proof):
        directions=proof.get('directions',{})
        if proof.get('status')!='PASS' or set(directions)!={'price_uah','price_georgia'}:
            raise InstallError('DB_DIRECTIONS_INCOMPLETE')
        required=('write','commit','fresh_readback','other_price_unchanged',
                  'full_row_invariant','restore_commit','restore_fresh_readback')
        if any(item.get(key)!='PASS' for item in directions.values() for key in required):
            raise InstallError('DB_MEASUREMENTS_INCOMPLETE')
        return dict(write_price_georgia='PASS',db_commit='PASS',read_back='PASS',
                    price_uah_unchanged='PASS',ua_ge_independence='PASS',rollback_test_value='PASS',
                    measured_proof=proof)

    def verify(self,expected):
        state=self.state(expected)
        if state['status']!='INSTALLED': raise InstallError('INSTALL_NOT_COMPLETED')
        current,_=regular(self.source)
        if sha(current)!=self.plan['source_after_sha256']: raise InstallError('SOURCE_POST_RESTART_DRIFT')
        if self.protected_snapshot()!=state['protected']: raise InstallError('PROTECTED_POST_RESTART_DRIFT')
        ui=verify_candidate_runtime(current.decode())
        if ui.get('status')!='PASS': raise InstallError('CALLBACK_VERIFY_FAILED')
        return dict(backup_manifest_sha256=expected,db=self.normalized_db(state['db_proof']),
                    ui_callbacks=ui,ui_runtime='NOT_VERIFIED',
                    acceptance_limitation='Callback execution is isolated; a live Telegram session has not been exercised.')

    def rollback(self,expected):
        state=self.state(expected)
        before=pathlib.Path(state['backup'])/'cars_ui.py'
        original,mode=regular(before)
        if sha(original)!=self.plan['source_before_sha256']: raise InstallError('BACKUP_CORRUPT')
        current=sha(regular(self.source)[0])
        if current not in (self.plan['source_before_sha256'],self.plan['source_after_sha256']):
            raise InstallError('ROLLBACK_SOURCE_CONCURRENT_CHANGE')
        if current==self.plan['source_after_sha256']: atomic(self.source,original,mode)
        if state['column_added']:
            with sqlite3.connect(self.db,timeout=10) as c:
                c.execute('BEGIN IMMEDIATE')
                cols={r[1] for r in c.execute('PRAGMA table_info(cars)')}
                if 'price_georgia' in cols:
                    if c.execute('SELECT 1 FROM cars WHERE price_georgia IS NOT NULL LIMIT 1').fetchone():
                        raise InstallError('ROLLBACK_PRESERVE_NEW_GE_VALUES')
                    c.execute('ALTER TABLE cars DROP COLUMN price_georgia')
        if self.protected_snapshot()!=state['protected']: raise InstallError('ROLLBACK_PROTECTED_DRIFT')
        # A verifier journal with restoration_needed must be addressed explicitly.
        for journal in self.db.parent.glob('task088-price-roundtrip-*.json'):
            if json.loads(journal.read_text()).get('restoration_needed'):
                raise InstallError('DB_RESTORATION_JOURNAL_PENDING')
        state.update(status='ROLLED_BACK',source_changed=False,column_added=False); self.save(state)
        return dict(backup_manifest_sha256=expected,restored_exact=True,
                    protected_files_unchanged=True,crm_unchanged=True,live_verify='PASS')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=('backup','install','verify','rollback'),required=True)
    for key in ('run-id','request-sha256','transaction-id','manifest-sha256'):
        parser.add_argument('--'+key,required=True)
    parser.add_argument('--backup-manifest-sha256')
    args=parser.parse_args()
    identity=dict(task_id=TASK_ID,run_id=args.run_id,request_sha256=args.request_sha256,
                  transaction_id=args.transaction_id,manifest_sha256=args.manifest_sha256)
    if (not re.fullmatch(r'[0-9]+',args.run_id) or not re.fullmatch(r'[A-Za-z0-9._-]{1,100}',args.transaction_id)
            or not HASH.fullmatch(args.request_sha256) or not HASH.fullmatch(args.manifest_sha256)):
        raise InstallError('EXECUTION_IDENTITY')
    expected_dir=ROOT/'autopilot_inbox/cloud/task_088_ge_price_crm_stage1/runs'/(args.run_id+'-'+args.request_sha256)
    if HERE!=expected_dir or HERE.resolve()!=HERE: raise InstallError('EXECUTION_DIRECTORY')
    receipt=HERE/('receipt-'+args.mode+'.json')
    with (HERE.parent.parent/'execution.lock').open('a+b') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        if receipt.exists():
            prior=json.loads(regular(receipt)[0])
            if any(prior.get(k)!=v for k,v in identity.items()) or prior.get('mode')!=args.mode:
                raise InstallError('RECEIPT_IDENTITY')
            return 0 if prior.get('status')=='PASS' else 1
        # A durable start record prevents an Always On restart after a crash
        # from replaying a partially completed operation.
        started=HERE/('started-'+args.mode+'.json')
        if started.exists(): raise InstallError('OPERATION_ALREADY_STARTED_RECOVERY_REQUIRED')
        atomic(started,canonical(dict(identity,mode=args.mode)))
        result=dict(identity,mode=args.mode,status='FAIL',site_write=False,publisher_write=False,unexpected_changes=0)
        try:
            plan=json.loads(regular(HERE/'plan.json')[0])
            if any(plan.get(key)!=value for key,value in identity.items()):
                raise InstallError('PLAN_EXECUTION_IDENTITY')
            installer=Installer(ROOT,HERE,identity,plan)
            if args.mode=='backup': result.update(installer.backup())
            else:
                if not HASH.fullmatch(str(args.backup_manifest_sha256 or '')): raise InstallError('BACKUP_SHA_REQUIRED')
                result.update(getattr(installer,args.mode)(args.backup_manifest_sha256))
            result['status']='PASS'
        except Exception as exc:
            result['error']=type(exc).__name__+':'+str(exc)
            if isinstance(exc, VerificationError): result['recovery_details']=exc.details
        atomic(receipt,canonical(result))
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
        return 0 if result['status']=='PASS' else 1

if __name__=='__main__': raise SystemExit(main())
