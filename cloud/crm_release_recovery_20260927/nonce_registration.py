"""Register the narrow nonce-copy repair without changing transaction outcomes."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import re

TASK = 'CRM-ROLLBACK-NONCE-20260927'
ACTIVATION = f'state/runtime_activations/{TASK}.json'
MANIFEST = 'state/AUTOPILOT_RUNTIME_MANIFEST.json'
MODE = 'state/EXECUTION_MODE.json'
PREVIOUS_MANIFEST = f'state/runtime_activations/{TASK}.previous-manifest.json'
PREVIOUS_MODE = f'state/runtime_activations/{TASK}.previous-mode.json'
BASE_MANIFEST_SHA = '2b3b75c686a41f4f6a48b2f9e2d57da12574c2b498505150899b66645d7cd2c5'
BASE_MODE_SHA = '11af7c738faa902412d35f0755a0a829df49ec939d32960abf343203f93bb715'
BASE_CONTROL_SHA = '168ce50bd7ee432573832a888f220fe02205ee4e05192db455c6af144170d74b'
CHANGED = frozenset({'automation/control_plane.py', '.github/workflows/uaart_critical.yml',
                     '.github/workflows/uaart_transaction_watchdog.yml'})
OWNER_COMMAND = 'Убери блоки и установи'


def digest(value):
    return hashlib.sha256(value).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def safe_read(root, relative):
    path = root / relative
    if path.resolve() != path or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('UNSAFE_REGISTRATION_FILE:' + relative)
    return path.read_bytes()


VERIFIER = '''def _verify_nonce_copy_runtime_activation(
    *, root: pathlib.Path, mode: Mapping[str, Any], approval: Mapping[str, Any],
    runtime: Mapping[str, Any], runtime_sha: str,
) -> dt.datetime:
    """Validate the separately authorized nonce transport fix; HALT stays independent."""
    prefix = "state/runtime_activations/CRM-ROLLBACK-NONCE-20260927"
    path = _runtime_activation_file(root, prefix + ".json")
    if sha256_file(path) != require_sha(mode.get("runtime_activation_sha256"), "nonce_activation"):
        raise ControlPlaneError("NONCE_ACTIVATION_SHA")
    activation = _runtime_activation_json(path)
    expected = {
        "schema_version": "UA-ART-NONCE-COPY-REGISTRATION-1",
        "task_id": "CRM-ROLLBACK-NONCE-20260927",
        "scope": "REPAIR_LEDGER_BOUND_NONCE_COPY_ONLY",
        "owner_command": "Убери блоки и установи",
        "owner_actor_id": "321059821",
        "repository": "art20021986-wq/ua-art-autopilot",
        "mode_epoch": mode.get("mode_epoch"),
        "halt_removed": False,
        "transaction_outcome_changed": False,
        "rollback_replay_allowed": False,
        "application_write_allowed": False,
        "previous_manifest_path": prefix + ".previous-manifest.json",
        "previous_manifest_sha256": "2b3b75c686a41f4f6a48b2f9e2d57da12574c2b498505150899b66645d7cd2c5",
        "previous_mode_path": prefix + ".previous-mode.json",
        "previous_mode_sha256": "11af7c738faa902412d35f0755a0a829df49ec939d32960abf343203f93bb715",
        "runtime_manifest_path": RUNTIME_MANIFEST_PATH,
        "runtime_manifest_sha256": runtime_sha,
        "changed_runtime_paths": sorted([
            "automation/control_plane.py", ".github/workflows/uaart_critical.yml",
            ".github/workflows/uaart_transaction_watchdog.yml"]),
    }
    if set(activation) != set(expected) | {"registered_at", "source_commit"}:
        raise ControlPlaneError("NONCE_ACTIVATION_KEYS")
    if any(activation.get(key) != value for key, value in expected.items()):
        raise ControlPlaneError("NONCE_ACTIVATION_SCOPE")
    if not re.fullmatch(r"[0-9a-f]{40}", str(activation.get("source_commit", ""))):
        raise ControlPlaneError("NONCE_ACTIVATION_SOURCE_COMMIT")
    previous = {}
    for kind in ("mode", "manifest"):
        snapshot = _runtime_activation_file(root, activation["previous_" + kind + "_path"])
        if sha256_file(snapshot) != activation["previous_" + kind + "_sha256"]:
            raise ControlPlaneError("NONCE_ACTIVATION_PREVIOUS_" + kind.upper())
        previous[kind] = _runtime_activation_json(snapshot)
    old_mode, old_runtime = previous["mode"], previous["manifest"]
    preserved = dict(mode)
    for key in ("runtime_manifest_sha256", "runtime_activation_path", "runtime_activation_sha256"):
        preserved[key] = old_mode[key]
    if preserved != old_mode:
        raise ControlPlaneError("NONCE_ACTIVATION_MODE_POLICY_DRIFT")
    old_time = _verify_runtime_activation(
        root=root, mode=old_mode, approval=approval, runtime=old_runtime,
        runtime_sha=activation["previous_manifest_sha256"])
    files = runtime.get("files")
    if (not isinstance(files, dict) or set(files) != set(RUNTIME_PINNED_PATHS)
            or {name for name in files if files[name] != old_runtime["files"][name]}
            != set(expected["changed_runtime_paths"])):
        raise ControlPlaneError("NONCE_ACTIVATION_RUNTIME_SCOPE")
    registered = parse_utc(str(activation["registered_at"]))
    if registered < old_time:
        raise ControlPlaneError("NONCE_ACTIVATION_TIME_ORDER")
    return registered


'''


def patch_control_plane(payload):
    if digest(payload) != BASE_CONTROL_SHA:
        raise ValueError('CONTROL_SOURCE_DRIFT')
    source = payload.decode()
    for old, new in (
        ('6f13c864a5d7b400474f3c9a1fe15e0d2d4dfca5d25dd195a628a3225d33e65a',
         'e878ee2dc8dc5022db095eb5a88d34acd7c262228ee592671ed4e691e3cac198'),
        ('817fd29309b0854ffbfbe7d360a07ba0b37348e646655850b1ed99897229dffe',
         'ad183ff63e4bf779591e2cc773aa1074c8005af399fedce810212e75b3dd7726')):
        if source.count(old) != 1:
            raise ValueError('WORKFLOW_PIN_SITE')
        source = source.replace(old, new, 1)
    anchor = 'def _verify_runtime_activation(\n'
    if source.count(anchor) != 1:
        raise ValueError('VERIFIER_SITE')
    source = source.replace(anchor, VERIFIER + anchor, 1)
    anchor = '    if mode.get("runtime_activation_path") == TASK088_ACTIVATION_PATH:\n'
    if source.count(anchor) != 1:
        raise ValueError('DISPATCH_SITE')
    source = source.replace(anchor,
        '    if mode.get("runtime_activation_path") == "' + ACTIVATION + '":\n'
        '        return _verify_nonce_copy_runtime_activation(\n'
        '            root=root, mode=mode, approval=approval, runtime=runtime, runtime_sha=runtime_sha)\n'
        + anchor, 1)
    anchor = '    mode = read_json(mode_path)\n    if mode.get("runtime_activation_path") != TASK088_ACTIVATION_PATH:\n'
    if source.count(anchor) != 1:
        raise ValueError('HISTORICAL_WAIVER_SITE')
    source = source.replace(anchor,
        '    mode = read_json(mode_path)\n'
        '    if mode.get("runtime_activation_path") == "' + ACTIVATION + '":\n'
        '        verify_execution_mode(root=root, required_mode="AUTOMATIC", allow_halt_for_recovery=True)\n'
        '        previous = _runtime_activation_file(root, "' + PREVIOUS_MODE + '")\n'
        '        if sha256_file(previous) != "' + BASE_MODE_SHA + '":\n'
        '            raise ControlPlaneError("NONCE_ACTIVATION_PREVIOUS_MODE")\n'
        '        mode = read_json(previous)\n'
        '    if mode.get("runtime_activation_path") != TASK088_ACTIVATION_PATH:\n', 1)
    compile(source, 'control_plane.py', 'exec')
    return source.encode()


def build(root: Path, source_commit: str, registered_at: str):
    root = root.resolve()
    if not re.fullmatch(r'[0-9a-f]{40}', source_commit):
        raise ValueError('SOURCE_COMMIT')
    when = dt.datetime.fromisoformat(registered_at.replace('Z', '+00:00'))
    if when.tzinfo is None:
        raise ValueError('TIMEZONE_REQUIRED')
    old = {}
    for relative, expected in ((MANIFEST, BASE_MANIFEST_SHA), (MODE, BASE_MODE_SHA)):
        old[relative] = safe_read(root, relative)
        if digest(old[relative]) != expected:
            raise ValueError('BASELINE_DRIFT:' + relative)
    for relative in (ACTIVATION, PREVIOUS_MANIFEST, PREVIOUS_MODE):
        if (root/relative).exists() or (root/relative).is_symlink():
            raise ValueError('ACTIVATION_ALREADY_PRESENT')
    mode, manifest = json.loads(old[MODE]), json.loads(old[MANIFEST])
    if when < dt.datetime.fromisoformat(manifest['generated_at'].replace('Z', '+00:00')):
        raise ValueError('TIME_ORDER')
    files = {name: digest(safe_read(root, name)) for name in manifest['files']}
    if len(files) != 18 or {name for name in files if files[name] != manifest['files'][name]} != CHANGED:
        raise ValueError('RUNTIME_CHANGE_SCOPE')
    output_manifest = encode(dict(manifest, files=files, generated_at=registered_at))
    activation = {
        'schema_version': 'UA-ART-NONCE-COPY-REGISTRATION-1', 'task_id': TASK,
        'scope': 'REPAIR_LEDGER_BOUND_NONCE_COPY_ONLY', 'owner_command': OWNER_COMMAND,
        'owner_actor_id': '321059821', 'repository': 'art20021986-wq/ua-art-autopilot',
        'mode_epoch': mode['mode_epoch'], 'halt_removed': False,
        'transaction_outcome_changed': False, 'rollback_replay_allowed': False,
        'application_write_allowed': False, 'previous_manifest_path': PREVIOUS_MANIFEST,
        'previous_manifest_sha256': BASE_MANIFEST_SHA, 'previous_mode_path': PREVIOUS_MODE,
        'previous_mode_sha256': BASE_MODE_SHA, 'runtime_manifest_path': MANIFEST,
        'runtime_manifest_sha256': digest(output_manifest), 'changed_runtime_paths': sorted(CHANGED),
        'registered_at': registered_at, 'source_commit': source_commit,
    }
    output_activation = encode(activation)
    output_mode = encode(dict(mode, runtime_manifest_sha256=digest(output_manifest),
        runtime_activation_path=ACTIVATION, runtime_activation_sha256=digest(output_activation)))
    return {MANIFEST: output_manifest, MODE: output_mode, ACTIVATION: output_activation,
            PREVIOUS_MANIFEST: old[MANIFEST], PREVIOUS_MODE: old[MODE]}
