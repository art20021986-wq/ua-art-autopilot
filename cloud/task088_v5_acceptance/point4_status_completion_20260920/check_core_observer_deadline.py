"""Narrow regression for postalarm capture-write refusal; synthetic only."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('core_deadline_target',HERE/'observe_point4_core.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)
checks={}
with tempfile.TemporaryDirectory(dir=HERE,prefix='core-deadline-') as tmp:
    root=Path(tmp);(root/'autopilot_inbox/cloud').mkdir(parents=True)
    class Slow(M.CoreObserver):
        def database(self):
            time.sleep(2)
            raise AssertionError('alarm failed')
    observer=Slow(root,root/'autopilot_inbox/cloud/hard',seconds=1,routing={})
    observer.captures={'video/UA-0001.html':b'x'*(8*1024*1024)}
    started=time.monotonic();report=observer.run()
    assert report['status']=='PARTIAL_NOT_ACCEPTED'
    assert time.monotonic()-started<1.8
    assert not (observer.output/'public_html').exists()
    assert (observer.output/'partial_export_outcome.json').is_file()
    checks['hard_alarm_never_starts_large_capture_save']='PASS'
    observer=M.CoreObserver(root,root/'autopilot_inbox/cloud/between',routing={})
    observer.prepare_output()
    original=observer.write_new
    count=[]
    def write(name,data,parent_fd=None):
        original(name,data,parent_fd)
        count.append(name)
        observer.total_deadline=time.monotonic()-1
    observer.write_new=write
    try:
        try:
            observer.save_captures({'site/first.html':b'first','site/second.html':b'second'})
            raise AssertionError('second capture permitted after deadline')
        except M.Stop as exc:
            assert str(exc)=='TOTAL_TIME_BOUND_EXCEEDED_DURING_CAPTURE_SAVE'
        assert count==['first.html']
        assert (observer.output/'public_html/site/first.html').read_bytes()==b'first'
        assert not (observer.output/'public_html/site/second.html').exists()
    finally:
        os.close(observer.output_fd);observer.output_fd=None
    checks['deadline_checked_before_each_capture_write']='PASS'
report={'status':'PASS','scope':'LOCAL_SYNTHETIC_ONLY','checks':checks,
        'observer_sha256':hashlib.sha256((HERE/'observe_point4_core.py').read_bytes()).hexdigest(),
        'production_or_network_operations':False}
(HERE/'CORE_OBSERVER_DEADLINE_FIX_VALIDATION.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
