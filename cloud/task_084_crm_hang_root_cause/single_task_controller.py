#!/usr/bin/env python3
"""Stage TASK 084 and execute its full lifecycle in one remote task."""

from __future__ import annotations

import json

import deploy_controller as core


HERE = core.HERE
REMOTE = core.REMOTE
ORCHESTRATOR = HERE / "remote_orchestrator.py"
FINAL = REMOTE + "/orchestrator_receipt.json"


def stage(api: core.API):
    if api.read(REMOTE + "/.bootstrap_ready", missing=True) is None:
        raise core.ControllerError("REMOTE_STAGING_DIR_NOT_READY")
    candidates, manifest, build = core.build_candidates(api)
    uploads = {
        "task084_remote_installer.py": core.INSTALLER.read_bytes(),
        "task084_remote_orchestrator.py": ORCHESTRATOR.read_bytes(),
        "manifest.json": (
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8"),
    }
    uploads.update({name + ".candidate": data for name, data in candidates.items()})
    for name, data in uploads.items():
        if name.endswith((".py", ".candidate")):
            compile(data.decode("utf-8"), name, "exec")
        path = REMOTE + "/" + name
        api.upload(path, data)
        if api.read(path) != data:
            raise core.ControllerError("UPLOAD_READBACK:" + name)
    return manifest, build


def execute(api: core.API) -> dict:
    api.delete_file(FINAL)
    trigger = api.create_trigger(
        "cd %s && python3.10 task084_remote_orchestrator.py" % REMOTE,
        "task084 single remote lifecycle",
    )
    try:
        raw = api.wait_for_file(FINAL, 1200)
        return json.loads(raw.decode("utf-8"))
    finally:
        api.delete_trigger(trigger)


def validate(value: dict, manifest: dict) -> None:
    if value.get("contract_id") != core.CONTRACT or value.get("status") != "PASS":
        raise core.ControllerError(
            "ORCHESTRATOR_FAILED:" + ";".join(value.get("errors") or [])
        )
    if value.get("transport") != "SINGLE_REMOTE_TASK":
        raise core.ControllerError("ORCHESTRATOR_TRANSPORT")
    if value.get("bot_restarted") is not True or value.get("rollback") is not None:
        raise core.ControllerError("ORCHESTRATOR_LIFECYCLE")
    core.validate_install(value.get("install") or {}, manifest)
    core.validate_postcheck(value.get("postcheck_immediate") or {})
    core.validate_postcheck(value.get("postcheck_delayed") or {})
    for key in ("launcher_immediate", "launcher_delayed"):
        if str((value.get(key) or {}).get("state", "")).lower() != "running":
            raise core.ControllerError("ORCHESTRATOR_" + key.upper())


def main() -> int:
    evidence = {
        "contract_id": core.CONTRACT,
        "transport": "SINGLE_REMOTE_TASK",
        "status": "FAIL",
        "started_at_utc": core.utc_now(),
        "errors": [],
        "bot_restarted": False,
        "rollback": None,
        "crm_db_write": False,
        "media_write": False,
    }
    try:
        api = core.API()
        manifest, build = stage(api)
        evidence["build"] = build
        remote = execute(api)
        evidence["remote"] = remote
        evidence.update({
            "install": remote.get("install"),
            "service": remote.get("service"),
            "bot_restarted": remote.get("bot_restarted", False),
            "launcher_immediate": remote.get("launcher_immediate"),
            "launcher_delayed": remote.get("launcher_delayed"),
            "postcheck_immediate": remote.get("postcheck_immediate"),
            "postcheck_delayed": remote.get("postcheck_delayed"),
            "rollback": remote.get("rollback"),
        })
        validate(remote, manifest)
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
        remote = evidence.get("remote") or {}
        for error in remote.get("errors") or []:
            evidence["errors"].append("REMOTE:" + str(error))
    evidence["finished_at_utc"] = core.utc_now()
    core.atomic_text(
        core.EVIDENCE,
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    core.write_report(evidence)
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
