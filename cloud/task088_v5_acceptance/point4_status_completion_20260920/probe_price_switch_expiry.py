"""Only new risk: authority deadline crossing during public render validation."""
from pathlib import Path
import sys,json,hashlib
from unittest.mock import patch
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE.parent/'pr114_review/cloud/task088_price_sync'))
from test_v5_runtime import V5RuntimeTests,R
f=V5RuntimeTests('runTest'); f.setUp()
try:
    event=f.submit(value=14000)
    before=f.cards[1].read_bytes()
    original_check=f.worker._check_surface
    original_write=R._atomic_write
    switch=[]
    def check(*args,**kwargs):
        value=original_check(*args,**kwargs)
        if kwargs.get('require_desired') and args[1].path==f.cards[1]:
            f.now+=40000
        return value
    def atomic(path,data,*args,**kwargs):
        if path==f.cards[1]: switch.append({'time_ms':f.now,'deadline_ms':1030000})
        return original_write(path,data,*args,**kwargs)
    with patch.object(f.worker,'_check_surface',check),patch.object(R,'_atomic_write',atomic):
        result=f.worker.process_operation(event['event_key'])
    observed=f.event(event['event_key'])
    report={'status':'BLOCKER_REPRODUCED' if f.cards[1].read_bytes()!=before else 'PASS_NO_EXPIRED_WRITE',
            'scope':'ISOLATED_SYNTHETIC_AUTHORITY_NO_LIVE_PASS',
            'reason':'Time can expire between _publish early check and atomic public switch.',
            'atomic_write_attempts':switch, 'public_bytes_changed':f.cards[1].read_bytes()!=before,'checkpoint':observed['state'],'error':observed['last_error'],
            'runtime_sha256':hashlib.sha256(Path(R.__file__).read_bytes()).hexdigest(),
            'unchanged_suites_rerun':False}
    (HERE/('PRICE_SWITCH_EXPIRY_PROBE_'+(sys.argv[1] if len(sys.argv)>1 else 'BEFORE')+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,sort_keys=True))
finally:f.doCleanups()
