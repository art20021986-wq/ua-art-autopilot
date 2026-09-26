"""New boundary: real fixture fence and actual Lifecycle durable revision/row."""
import hashlib,json,sys,sqlite3
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE.parent/'pr114_review/cloud/task088_v5_writer_fence'))
from test_visibility_lifecycle import NativeVisibility,visibility as V
import publication_fence as F
f=NativeVisibility('runTest');f.setUp()
checks=[]
real_require=F.require_publication_fence
try:
    # Redirect only path selection; execute the actual descriptor/owner check.
    require=lambda:real_require(lock_path=f.binding.publication_lock)
    with patch.object(F,'require_publication_fence',require):
        with V.authority_scope(lambda:None,recovery_check=lambda:None):
            try:
                with V.recovery_scope():pass
            except F.FenceError as exc:assert str(exc)=='PUBLICATION_FENCE_REQUIRED'
            else:raise AssertionError('Missing real fence was accepted')
        checks.append('MISSING_ACTUAL_FIXTURE_FENCE_REJECTED')
        f.call('unpublish-before-recovery')
        def publish(code):
            f.binding.clock=lambda:2000
            with V.recovery_scope():
                V.require_active_authority()
            checks.append('OWNED_DURABLE_REVISION_COMPENSATES_AFTER_TTL')
            with sqlite3.connect(f.database) as conn:
                conn.execute('UPDATE cars SET price_uah=14000 WHERE id=1')
            try:
                with V.recovery_scope():pass
            except V.VisibilityError as exc:assert str(exc)=='VISIBILITY_RECOVERY_EPOCH_CONFLICT'
            else:raise AssertionError('New operator row was accepted for stale restore')
            checks.append('NEWER_OPERATOR_ROW_BLOCKS_STALE_COMPENSATION')
            try:V.require_active_authority()
            except V.VisibilityError as exc:assert str(exc)=='VISIBILITY_AUTHORITY_EXPIRED'
            else:raise AssertionError('Recovery privilege escaped scope')
            checks.append('RECOVERY_SCOPE_DOES_NOT_REAUTHORIZE_FORWARD_WRITE')
            raise KeyboardInterrupt()
        f.service.publish=publish
        try:f.call('publish-expired',1)
        except KeyboardInterrupt:pass
        else:raise AssertionError('Unknown result must stay pending')
        assert f.service.intent(f.key('publish-expired'))['state']=='PROJECTION_STARTED'
        assert V.current_row(f.binding,1)['price_uah']==14000
        checks.append('UNKNOWN_PROJECTION_AND_NEW_OPERATOR_ROW_PRESERVED')
    report={'status':'PASS','scope':'ISOLATED_FIXTURE_SQLITE_REAL_FENCE_NO_LIVE_PASS',
        'reason':'Publisher primitive tests mocked fence; verify native recovery checks actual lock ownership and journal epoch.',
        'checks':checks,'lifecycle_sha256':hashlib.sha256(Path(V.__file__).read_bytes()).hexdigest(),
        'fence_sha256':hashlib.sha256(Path(F.__file__).read_bytes()).hexdigest(),
        'test_path_selection_redirected':True,'lock_ownership_check_mocked':False,'unchanged_suites_rerun':False}
    (HERE/'NATIVE_RECOVERY_OWNERSHIP_PROBE.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,sort_keys=True))
finally:f.doCleanups()
