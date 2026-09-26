"""Targeted independent review: exact composed direct-rebuild boundary.

Only an isolated synthetic DB is used. The actual composed main wrapper is
executed; renderer body is an observable probe, not a production import.
"""
import ast
import contextlib
import hashlib
import json
import os
from pathlib import Path
import sys

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
import publication_fence
from test_guard_fence import GuardFenceTests

prices = {
    'cars_ui.py': patch_cars_ui.patch_source((BASE/'cars_ui.py').read_text()).encode(),
    'publish_transaction_guard.py': patch_guard.patch_source((BASE/'publish_transaction_guard.py').read_text()).encode(),
    'stranica.py': patch_stranica.patch_stranica((BASE/'stranica.py').read_bytes())[0],
}
composed = integration.compose_price_candidate(prices,
    {name: (DEPS/name).read_bytes() for name in integration.DEPENDENCY_SHA256})
GuardFenceTests.setUpClass()
fixture = GuardFenceTests(methodName='runTest')
fixture.setUp()
result = {'scope': 'SYNTHETIC_ISOLATED_REVIEW_NOT_PRODUCTION',
          'reason': 'Newly composed media/direct renderer can enter between V5 price checkpoints.',
          'candidate_sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in composed.items()},
          'unchanged_test_suites_rerun': False}
try:
    event = fixture.advance_v5(fixture.submit_v5(), stop='DB_COMMITTED')
    result['persisted_price_checkpoint'] = event['state']
    try:
        with fixture.ns['_task088_price_quiescence']():
            raise AssertionError('expected guarded path rejection')
    except fixture.ns['PublishError'] as exc:
        result['guard_rejection'] = str(exc)
    wrappers = [node for node in ast.parse(composed['stranica.py']).body
                if isinstance(node, ast.FunctionDef) and node.name == 'main']
    last = wrappers[-1]
    observations = []
    def renderer_probe():
        value = fixture.db.execute('SELECT price_georgia FROM cars WHERE id=10').fetchone()[0]
        observations.append(value)
    ns = {'_ua114_main_base': renderer_probe,
          '_ua114_publication_fence': lambda: publication_fence.PublicationFence(
              lock_path=fixture.root/'publish.lock', _test_only_path=True)}
    exec(compile(ast.Module(body=[last], type_ignores=[]), '<exact-composed-main>', 'exec'), ns)
    ns['main']()
    result['direct_main_renderer_called'] = bool(observations)
    result['direct_main_unverified_ge_observed'] = observations
    result['finding'] = 'DIRECT_REBUILD_BYPASSES_PRICE_QUIESCENCE' if observations else 'NOT_REPRODUCED'
    result['status'] = 'BLOCKER_REPRODUCED' if observations else 'PASS'
finally:
    fixture.doCleanups()
(EVIDENCE/'direct_rebuild_quiescence_result.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, sort_keys=True))
