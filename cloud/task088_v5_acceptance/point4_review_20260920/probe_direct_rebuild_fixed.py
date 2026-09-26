"""Independent before/after check of R1; exact composed contexts, fixture DB.

No unchanged suite is rerun. Source modules are not imported into production.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import types
from unittest.mock import patch

ROOT = Path('/workspace/scratch/cc71e1c55fba/pr114_review')
BASE = Path('/workspace/scratch/eb425df3a207/private_v5_sources_recovered')
DEPS = Path('/workspace/scratch/eb425df3a207/private_dependencies_20260920')
EVIDENCE = Path(__file__).parent
os.environ['TMPDIR'] = str(EVIDENCE)
os.environ['TASK088_PUBLISH_GUARD_SOURCE'] = str(BASE / 'publish_transaction_guard.py')
for directory in ('task088_price_sync', 'task088_stage3_renderer', 'task088_v5_writer_fence'):
    sys.path.insert(0, str(ROOT / 'cloud' / directory))
import integrate_private_sources as integration
import patch_cars_ui
import patch_guard
import patch_stranica
import publication_fence as fence
from test_guard_fence import GuardFenceTests

prices = {
    'cars_ui.py': patch_cars_ui.patch_source((BASE/'cars_ui.py').read_text()).encode(),
    'publish_transaction_guard.py': patch_guard.patch_source((BASE/'publish_transaction_guard.py').read_text()).encode(),
    'stranica.py': patch_stranica.patch_stranica((BASE/'stranica.py').read_bytes())[0],
}
composed = integration.compose_price_candidate(prices,
    {name: (DEPS/name).read_bytes() for name in integration.DEPENDENCY_SHA256})
GuardFenceTests.setUpClass()
result = {'scope': 'SYNTHETIC_ISOLATED_REVIEW_NOT_PRODUCTION',
          'reason': 'Verify only newly fixed R1 and nested renderer/guard boundary.',
          'candidate_sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in composed.items()},
          'unchanged_test_suites_rerun': False, 'checks': []}
for checkpoint in ('QUEUED', 'DB_COMMITTED', 'CLEAN'):
    fixture = GuardFenceTests(methodName='runTest')
    fixture.setUp()
    lock = fixture.root/'publish.lock'
    require = fence.require_publication_fence
    factory = lambda **kwargs: fence.PublicationFence(lock_path=lock, _test_only_path=True, **kwargs)
    observations = []
    guard = types.ModuleType('publish_transaction_guard')
    guard.__dict__.update(fixture.ns)
    helper = next(node for node in ast.parse(composed['publish_transaction_guard.py']).body
                  if isinstance(node, ast.FunctionDef) and node.name == '_task088_price_quiescence')
    exec(compile(ast.Module(body=[helper], type_ignores=[]), '<exact-price-base-helper>', 'exec'), guard.__dict__)
    try:
        with patch.object(fence, 'publication_fence', factory), \
             patch.object(fence, 'require_publication_fence', lambda: require(lock_path=lock)), \
             patch.dict(sys.modules, {'publish_transaction_guard': guard}):
            exec(compile(integration.GUARD_BLOCK, '<exact-composed-guard>', 'exec'), guard.__dict__)
            def renderer():
                ns['zapisat']()
                ns['obnovit_etalon']()
                observations.append('main')
            ns = {'main': renderer, 'zapisat': lambda: observations.append('write'),
                  'obnovit_etalon': lambda: observations.append('template')}
            exec(compile(integration.STRANICA_BLOCK, '<exact-composed-renderer-boundaries>', 'exec'), ns)
            if checkpoint != 'CLEAN':
                event = fixture.submit_v5()
                if checkpoint == 'DB_COMMITTED':
                    fixture.advance_v5(event, stop='DB_COMMITTED')
                for name in ('main', 'zapisat', 'obnovit_etalon'):
                    try:
                        ns[name]()
                    except fixture.ns['PublishError'] as exc:
                        assert 'V5_UNVERIFIED_PRICE_INTENTS' in str(exc), str(exc)
                    else:
                        raise AssertionError('unfinished price entered '+name)
                assert not observations
                result['checks'].append(checkpoint+'_DIRECT_MAIN_WRITE_TEMPLATE_BLOCKED_BEFORE_EFFECT')
            else:
                # This is the nesting that would self-deadlock with a second
                # independent BEGIN IMMEDIATE connection.
                with factory(), guard._task088_price_quiescence():
                    ns['main']()
                assert observations == ['write', 'template', 'main']
                result['checks'].append('GUARDED_PUBLICATION_MAIN_WRITE_TEMPLATE_REENTRANT')
                def fail():
                    raise RuntimeError('synthetic render failure')
                ns['_ua114_main_base'] = fail
                try:
                    ns['main']()
                except RuntimeError as exc:
                    assert str(exc) == 'synthetic render failure'
                else:
                    raise AssertionError('render exception lost')
                with sqlite3.connect(fixture.path, timeout=0) as con:
                    con.execute('UPDATE cars SET price_georgia=8001 WHERE id=10')
                ns['_ua114_main_base'] = renderer
                ns['main']()
                result['checks'].append('RENDER_FAILURE_RELEASES_DB_AND_TLS_FOR_NEXT_CALL')
    finally:
        fixture.doCleanups()
result['status'] = 'PASS'
(EVIDENCE/'direct_rebuild_quiescence_fixed_result.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, sort_keys=True))
