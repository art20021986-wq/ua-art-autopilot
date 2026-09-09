"""Build the separately authorized runtime registration as data only.

No live writes, remote calls or HALT removal.  Call after all three runtime
sources are frozen; the caller reviews and commits the returned five files.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import re

TASK = "UA-ART-RECOVERY-TASK120-002"
REPOSITORY = "art20021986-wq/ua-art-autopilot"
MANIFEST = "state/AUTOPILOT_RUNTIME_MANIFEST.json"
MODE = "state/EXECUTION_MODE.json"
APPROVAL = "tasks/approvals/TASK107-R2-AUTOMATIC-MODE.json"
HALT = "state/AUTOPILOT_HALT.json"
ACTIVATION = f"state/runtime_activations/{TASK}.json"
OLD_MANIFEST = f"state/runtime_activations/{TASK}.previous-manifest.json"
OLD_MODE = f"state/runtime_activations/{TASK}.previous-mode.json"
BASE_MANIFEST_SHA = "bfb650e2bd58dd2f556213e1c875552e8ba33b55e7e71de1bfe9f311f6003110"
BASE_MODE_SHA = "8013a8d15951b958a63e812330e7591c04882d0384f9c4bda85861bb7840469f"
BASE_APPROVAL_SHA = "6e6071e5a06e7d69a20aebc035bd57f74ef903e353cfe5a7e017df947a3eb643"
HALT_SHA = "35c8f42ec20d33f259cbf87aaaa193c86c4d5ae469fa4a8e67e6d049ce0091e9"
CHANGED = frozenset({
    "automation/control_plane.py", "automation/transaction_watchdog.py",
    ".github/workflows/uaart_transaction_watchdog.yml",
})


class ActivationError(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encode(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def read(root: Path, relative: str) -> bytes:
    path = root.absolute() / relative
    for candidate in (path, *path.parents):
        if candidate.is_symlink():
            raise ActivationError("SYMLINK:" + relative)
    if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise ActivationError("FILE_INVALID:" + relative)
    return path.read_bytes()


def _time(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ActivationError("TIME_INVALID") from exc
    if parsed.tzinfo is None:
        raise ActivationError("TIME_ZONE_REQUIRED")
    return parsed.astimezone(dt.timezone.utc)


def build_registration(*, root: Path, original_root: Path, registered_at: str,
                       source_commit: str) -> dict[str, bytes]:
    """Return exact activation bytes while preserving every original input."""
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ActivationError("SOURCE_COMMIT_INVALID")
    baseline = {}
    for relative, expected in ((MANIFEST, BASE_MANIFEST_SHA), (MODE, BASE_MODE_SHA),
                               (APPROVAL, BASE_APPROVAL_SHA), (HALT, HALT_SHA)):
        data = read(original_root, relative)
        if digest(data) != expected:
            raise ActivationError("BASELINE_SHA:" + relative)
        baseline[relative] = data
        if read(root, relative) != data:
            raise ActivationError("INPUT_ALREADY_CHANGED:" + relative)
    for relative in (ACTIVATION, OLD_MANIFEST, OLD_MODE):
        if (root / relative).exists() or (root / relative).is_symlink():
            raise ActivationError("ACTIVATION_ALREADY_EXISTS:" + relative)
    old_manifest = json.loads(baseline[MANIFEST])
    old_mode = json.loads(baseline[MODE])
    if len(old_manifest["files"]) != 18:
        raise ActivationError("RUNTIME_FILE_SET")
    if _time(registered_at) < _time(old_mode["activated_at"]):
        raise ActivationError("REGISTRATION_TIME_ORDER")
    current_files = {relative: digest(read(root, relative))
                     for relative in old_manifest["files"]}
    changed = {relative for relative in current_files
               if current_files[relative] != old_manifest["files"][relative]}
    if changed != CHANGED:
        raise ActivationError("RUNTIME_CHANGED_SET:" + ",".join(sorted(changed)))
    manifest = dict(old_manifest, files=current_files, generated_at=registered_at)
    manifest_data = encode(manifest)
    activation = {
        "schema_version": "UA-ART-RUNTIME-ROUTE-ACTIVATION-1",
        "task_id": TASK,
        "scope": "REGISTER_RECOVERY_ROUTE_ONLY",
        "owner_command": "подключай проверенный маршрут исполнения.",
        "owner": "Артём Бровинский / UA ART COMPANY LLC",
        "owner_actor_id": "321059821",
        "registered_at": registered_at,
        "source_commit": source_commit,
        "repository": REPOSITORY,
        "mode_epoch": old_mode["mode_epoch"],
        "halt_removal_authorized": False,
        "production_changes_authorized": False,
        "previous_manifest_path": OLD_MANIFEST,
        "previous_manifest_sha256": BASE_MANIFEST_SHA,
        "previous_mode_path": OLD_MODE,
        "previous_mode_sha256": BASE_MODE_SHA,
        "original_approval_sha256": BASE_APPROVAL_SHA,
        "runtime_manifest_path": MANIFEST,
        "runtime_manifest_sha256": digest(manifest_data),
        "changed_runtime_paths": sorted(CHANGED),
        "expected_halt_sha256": HALT_SHA,
    }
    activation_data = encode(activation)
    mode_data = encode(dict(old_mode, runtime_manifest_sha256=digest(manifest_data),
                           runtime_activation_path=ACTIVATION,
                           runtime_activation_sha256=digest(activation_data)))
    result = {OLD_MANIFEST: baseline[MANIFEST], OLD_MODE: baseline[MODE],
              MANIFEST: manifest_data, ACTIVATION: activation_data, MODE: mode_data}
    for relative, before in baseline.items():
        if read(original_root, relative) != before or read(root, relative) != before:
            raise ActivationError("SOURCE_DRIFT:" + relative)
    return result
