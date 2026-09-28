"""Environment-only entrypoint for the existing CRITICAL installation route.

The specification's parent acceptance is deliberately outside this child task.
Importing this module performs no network operation or production mutation.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

from contract import load_envelope, receipt_from_result

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


class ControllerError(RuntimeError):
    pass


def _require(condition, code):
    if not condition:
        raise ControllerError(code)


def _bundle_plan(bundle):
    """Read precisely the already bound plan that will be sent to the worker."""
    name = bundle.parameters['plan_path']
    selected = [item for item in bundle.files if item.relative_path == name]
    _require(len(selected) == 1, 'EXACT_STAGED_PLAN_REQUIRED')
    raw = selected[0].content
    _require(hashlib.sha256(raw).hexdigest() == bundle.parameters['plan_sha256'],
             'STAGED_PLAN_HASH_MISMATCH')
    value = json.loads(raw)
    _require(isinstance(value, dict), 'STAGED_PLAN_OBJECT_REQUIRED')
    return value


def _admit(envelope, bundle):
    # This is an exact generated copy of the canonical install module. The
    # request's Python dependency closure pins it before the launcher imports it.
    from lifecycle_controller import RepositoryAdmission
    plan = _bundle_plan(bundle)
    # The authority checkout location is a run-specific envelope field. It is
    # excluded from the static policy; the remote worker performs its own fresh
    # fixed-origin checkout and repeats admission against that exact revision.
    local_plan = dict(plan, authority=dict(plan['authority']))
    current_root, source_root = _authority_roots(envelope, plan)
    local_plan['authority']['repository_root'] = str(current_root)
    local_plan['authority']['source_repository_root'] = str(source_root)
    return RepositoryAdmission(local_plan).check(operation=envelope.operation)


def _authority_roots(envelope, plan):
    """Honor the existing workflow's pinned rollback worktree, without overrides.

    uaart_critical.yml creates that worktree from the fresh main checkout. Its
    common Git directory identifies the original checkout. RepositoryAdmission
    independently checks both commits, ancestry, and all five durable overlays.
    """
    source = Path(envelope.root).resolve(strict=True)
    if envelope.operation != 'rollback':
        return source, source
    raw = subprocess.check_output(['git', '-C', str(source), 'rev-parse',
        '--path-format=absolute', '--git-common-dir'], timeout=20,
        stderr=subprocess.DEVNULL).decode().strip()
    common = Path(raw)
    _require(common.is_absolute() and common.resolve(strict=True) == common and
             common.is_dir() and common.name == '.git', 'EXACT_SHARED_GIT_DIRECTORY_REQUIRED')
    current = common.parent
    _require((current / '.git').resolve(strict=True) == common,
             'ORIGINAL_AUTHORITY_WORKTREE_REQUIRED')
    head = subprocess.check_output(['git', '-C', str(current), 'rev-parse', 'HEAD'],
        timeout=20, stderr=subprocess.DEVNULL).decode().strip()
    _require(head == plan['authority']['main_commit'], 'CURRENT_AUTHORITY_WORKTREE_DRIFT')
    return current, source


def _write_new_json(path, value):
    """Publish a complete receipt once; never replace evidence from another run."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _require(path.parent.resolve() == path.parent and not path.is_symlink(),
             'CANONICAL_RECEIPT_PARENT_REQUIRED')
    temporary = path.parent / ('.receipt-' + secrets.token_hex(16))
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        # link is atomic and refuses any existing target, including a symlink.
        os.link(temporary, path, follow_symlinks=False)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def run(operation, *, root=ROOT, environment=None):
    """Validate authority, execute one fixed operation, then publish proven data."""
    _require(operation in ('backup', 'execute', 'rollback'), 'OPERATION_SCOPE')
    environment = dict(os.environ if environment is None else environment)
    root = Path(root).resolve(strict=True)
    if operation != 'rollback':
        _require(not (root / 'state/AUTOPILOT_HALT.json').exists(),
                 'EXISTING_AUTOPILOT_HALT_BLOCKS_INSTALL')
    envelope = load_envelope(root, environment, operation)
    token = environment.get('PYTHONANYWHERE_API_TOKEN', '')
    _require(isinstance(token, str) and bool(token.strip()), 'PROVIDER_CREDENTIAL_REQUIRED')
    from transport import PythonAnywhereTransport
    from release_bundle import prepare
    transport = PythonAnywhereTransport(token)
    bundle = prepare(envelope, transport)
    _admit(envelope, bundle)
    stage = transport.claim_transport(bundle)
    # Transport owns the distinction between terminal evidence and an uncertain
    # timeout. An uncertain operation does not reach cleanup or a PASS receipt.
    result = transport.run(stage, operation=operation)
    transport.release_transport(stage)
    receipt = receipt_from_result(envelope, result)
    _write_new_json(envelope.receipt_path, receipt)
    return receipt


def main(operation='execute'):
    # The normal dispatcher passes identity in environment variables only.
    if len(sys.argv) != 1:
        print(json.dumps({'status': 'FAIL', 'error': 'APPLICATION_ARGUMENTS_FORBIDDEN'}))
        return 1
    try:
        value = run(operation)
    except Exception as exc:
        # Arbitrary exception messages and HTTP bodies can include credentials.
        print(json.dumps({'status': 'FAIL', 'error_type': type(exc).__name__}, sort_keys=True))
        return 1
    print(json.dumps({'task_id': value['task_id'], 'status': value['status'],
                      'parent_acceptance_status': 'PENDING_LIVE_TELEGRAM_ACCEPTANCE'},
                     sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
