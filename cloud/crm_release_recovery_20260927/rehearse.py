"""Reproduce the incident in temporary files using unchanged pinned validators.

No GitHub/PythonAnywhere calls, no credentials, no production writes, and no
changes to active checkout state. Output is evidence of workspace assembly only.
"""
import datetime
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tarfile
import tempfile

import prepare_nonce_fix as fix


TASK = 'DELIVERY-STATUS-INSTALL-20260927'
REQUEST_SHA = '54c3be3cfc4dd0dab6f508524499715a6844011f4aa9520cc6e09f51f8c132ff'
RUN_ID = '36268504600'
SOURCE_COMMIT = '9fd580ca61c67dfb944bc4826fd1f18459ffba0b'
STEM = TASK + '.' + REQUEST_SHA + '.' + RUN_ID
REQUEST = 'tasks/requests/' + TASK + '.json'
CLAIM = 'state/claims/' + STEM + '.json'
TRANSACTION = 'state/transactions/' + STEM + '.json'
LEDGER = 'state/autostart_consumed/' + TASK + '.' + REQUEST_SHA + '.json'


def run():
    archive = subprocess.check_output(['git', 'archive', '--format=tar', SOURCE_COMMIT], cwd=fix.ROOT)
    evidence = []
    for relative in fix.SOURCES:
        with tempfile.TemporaryDirectory(prefix='crm-rollback-rehearsal-') as directory:
            pinned = Path(directory)
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                tar.extractall(pinned, filter='data')
            original = (fix.ROOT / relative).read_bytes()
            env = {**os.environ, 'PINNED_ROOT': str(pinned), 'SOURCE_COMMIT': SOURCE_COMMIT,
                   'CLAIM_PATH': CLAIM, 'TRANSACTION_PATH': TRANSACTION,
                   'EXPECTED_TRANSACTION_PATH': TRANSACTION, 'REQUEST_PATH': REQUEST,
                   'EXPECTED_REQUEST_PATH': REQUEST}
            validator = runpy.run_path(str(pinned / 'automation/control_plane.py'))

            def verify():
                _, _, raw, digest = validator['load_request'](REQUEST, pinned)
                assert digest == REQUEST_SHA
                return validator['verify_autostart_ledger'](
                    LEDGER, REQUEST, raw, digest, RUN_ID, expected_source_commit=SOURCE_COMMIT,
                    root=pinned, allow_expired_for_recovery=True, allow_halt_for_recovery=True)

            def copy(payload):
                result = subprocess.run([sys.executable, '-I', '-c', fix.copied_state_script(payload.decode())],
                                        cwd=fix.ROOT, env=env, text=True, capture_output=True, timeout=15)
                if result.returncode:
                    raise RuntimeError(result.stderr)

            copy(original)
            try:
                verify()
            except validator['ControlPlaneError'] as error:
                baseline_error = str(error)
                assert baseline_error == 'AUTOSTART_NONCE_RESERVATION_MISSING', baseline_error
            else:
                raise AssertionError('Expected missing nonce in original workspace')
            candidate = fix.candidate(relative, original)
            copy(candidate)
            binding = verify()
            transaction = json.loads((pinned / TRANSACTION).read_bytes())
            assert transaction['status'] == 'ROLLING_BACK'
            current_halt = json.loads((fix.ROOT / 'state/AUTOPILOT_HALT.json').read_bytes())
            assert current_halt['run_id'] == RUN_ID
            evidence.append({'workflow': relative, 'baseline_error': baseline_error,
                             'candidate_ledger_verification': 'PASS',
                             'transaction_status_preserved': transaction['status'],
                             'original_workflow_sha256': fix.hashlib.sha256(original).hexdigest(),
                             'candidate_workflow_sha256': fix.hashlib.sha256(candidate).hexdigest(),
                             'ledger_binding': binding})
    return {'schema_version': 'CRM-ROLLBACK-WORKSPACE-REHEARSAL-1',
            'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'repository_source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=fix.ROOT, text=True).strip(),
            'failed_source_commit': SOURCE_COMMIT, 'failed_run_id': RUN_ID,
            'status': 'PASS', 'scope': 'LOCAL_WORKSPACE_ASSEMBLY_ONLY',
            'production_written': False, 'rollback_invoked': False,
            'active_workflows_changed': False, 'runtime_manifest_changed': False,
            'halt_cleared': False, 'transaction_closed': False,
            'production_install_ready': False, 'results': evidence}


if __name__ == '__main__':
    print(json.dumps(run(), ensure_ascii=False, indent=2, sort_keys=True))
