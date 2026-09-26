"""Run isolated target-host renderer rehearsal. No installation or production write."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
from preview_transport import API, TASK_ID, REMOTE_SCRIPT, REMOTE_RECEIPT

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
NAMES=('public_fields.py','public_media.py','crm_gallery.py','crm_revision.py','crm_assets.py','build_candidate.py','build_gallery_patch.py','test_public_fields.py')


def package():
    payload={name:base64.b64encode((HERE/name).read_bytes()).decode() for name in NAMES}
    validator=(HERE/'shadow_validate.py').read_text()
    script='''import base64,json,pathlib,re,signal,sys,traceback
if len(sys.argv)!=3 or sys.argv[1]!='preview' or not re.fullmatch(r'[0-9]+',sys.argv[2]):raise SystemExit(2)
receipt=pathlib.Path(RECEIPT_PATH)
result={'status':'FAIL','run_id':sys.argv[2],'production_written':False,'full_acceptance':False}
def timeout(signum,frame):raise TimeoutError('Preview deadline')
signal.signal(signal.SIGALRM,timeout);signal.alarm(180)
try:
 result.update(validate(PAYLOAD,receipt_path=receipt))
except Exception as error:
 result['error_type']=type(error).__name__
 result['failure_frames']=[{'file':pathlib.Path(x.filename).name,'function':x.name,'line':x.lineno} for x in traceback.extract_tb(error.__traceback__)[-5:]]
finally:
 signal.alarm(0)
 receipt.write_text(json.dumps(result,sort_keys=True)+'\\n')
'''
    prefix='RECEIPT_PATH='+repr(REMOTE_RECEIPT)+'\nPAYLOAD='+repr(payload)+'\n'
    source=validator+'\n'+prefix+script
    compile(source,'preview-remote','exec')
    return source.encode()


def main():
    if os.environ.get('UAART_TASK_ID')!=TASK_ID or os.environ.get('UAART_TASK_CLASS')!='STANDARD':
        raise RuntimeError('TASK_IDENTITY')
    run=os.environ.get('UAART_RUN_ID','')
    if not re.fullmatch(r'[0-9]+',run):raise RuntimeError('RUN_IDENTITY')
    request=ROOT/os.environ['UAART_REQUEST_PATH']
    if hashlib.sha256(request.read_bytes()).hexdigest()!=os.environ['UAART_REQUEST_SHA256']:
        raise RuntimeError('REQUEST_SHA')
    receipt_path='state/receipts/'+TASK_ID+'.json'
    if os.environ['UAART_RECEIPT_PATH']!=receipt_path:raise RuntimeError('RECEIPT_IDENTITY')
    api=API(os.environ['PYTHONANYWHERE_API_TOKEN'])
    source=package();api.upload(REMOTE_SCRIPT,source)
    try:
        result=api.run('preview',run)
        (HERE/'shadow_evidence.json').write_text(json.dumps(result,indent=2)+'\n')
        success=result.get('status')=='PASS' and result.get('protected_files_unchanged') is True and result.get('production_written') is False
        receipt={'task_id':TASK_ID,'task_class':'STANDARD','status':'FINISHED' if success else 'FAILED',
                 'target_environment':'shadow','tests':'PASS' if success else 'FAIL','unexpected_changes':0,
                 'production_required':False,'production_touched':False,'rollback_ready':True,
                 'rollback_reason':'Isolated disposable shadow; original source/HTML protected by write guard and hashes',
                 'full_consistency_accepted':False,'renderer_validation':result.get('status'),
                 'run_id':run,'payload_sha256':hashlib.sha256(source).hexdigest()}
        path=ROOT/receipt_path;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(receipt,sort_keys=True)+'\n')
        if not success:raise RuntimeError('SHADOW_RENDER_VALIDATION_FAILED')
    finally:
        for path in (REMOTE_SCRIPT,REMOTE_RECEIPT):
            try:api.delete(path)
            except Exception:pass

if __name__=='__main__':main()
