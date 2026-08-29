"""TASK 073 ROUND 5 - gate_b_controller_v4.py

Manual-only Gate B orchestrator. NEVER auto-triggered by this repo.
Requires the exact owner approval token. Uses the PythonAnywhere Files
API (upload/read-back), Consoles API (remote execute), and the
always_on_tasks restart endpoint - the same class of proven endpoints
used in task_069/task_072, not a new API shell.
"""

import json
import os
import sys
import time

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

APPROVED_TOKEN = "CRM-UNIFIED-CATALOG-001-V1.0-APPROVED"
REMOTE_DIR = "autopilot_inbox/cloud/task_073"
API_BASE = "https://www.pythonanywhere.com/api/v0/user/{user}"


class GateBBlocked(RuntimeError):
    pass


def _headers(token):
    return {"Authorization": "Token %s" % token}


def check_approval(approval_input):
    if approval_input != APPROVED_TOKEN:
        raise GateBBlocked("APPROVAL_TOKEN_MISMATCH")
    return True


def _extract_json(text):
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise RuntimeError("NO_JSON_IN_OUTPUT")
    return json.loads(text[start:end + 1])


def upload_file(session, username, token, remote_path, local_path):
    url = API_BASE.format(user=username) + "/files/path/home/%s/%s" % (username, remote_path)
    with open(local_path, "rb") as fh:
        resp = session.post(url, headers=_headers(token), files={"content": fh}, timeout=60)
    if resp.status_code not in (200, 201):
        raise RuntimeError("UPLOAD_FAILED:%s:%s" % (remote_path, resp.status_code))
    return True


def read_back(session, username, token, remote_path, local_path):
    url = API_BASE.format(user=username) + "/files/path/home/%s/%s" % (username, remote_path)
    resp = session.get(url, headers=_headers(token), timeout=30)
    if resp.status_code != 200:
        raise RuntimeError("READBACK_GET_FAILED:%s" % remote_path)
    with open(local_path, "rb") as fh:
        local_bytes = fh.read()
    if resp.content != local_bytes:
        raise RuntimeError("READBACK_MISMATCH:%s" % remote_path)
    return True


def find_launcher_task(session, username, token):
    url = API_BASE.format(user=username) + "/always_on_tasks/"
    resp = session.get(url, headers=_headers(token), timeout=30)
    if resp.status_code != 200:
        raise RuntimeError("ALWAYS_ON_LIST_FAILED:%s" % resp.status_code)
    tasks = resp.json()
    matches = [t for t in tasks if "start_safe.py" in t.get("command", "")]
    if len(matches) != 1:
        raise RuntimeError("LAUNCHER_NOT_UNIQUE:%d" % len(matches))
    return matches[0]


def restart_launcher(session, username, token, task_id):
    url = API_BASE.format(user=username) + "/always_on_tasks/%s/restart/" % task_id
    resp = session.post(url, headers=_headers(token), timeout=30)
    if resp.status_code not in (200, 302):
        raise RuntimeError("RESTART_FAILED:%s" % resp.status_code)
    return True


def create_console(session, username, token, executable="python3.10"):
    url = API_BASE.format(user=username) + "/consoles/"
    resp = session.post(url, headers=_headers(token), data={"executable": executable}, timeout=30)
    if resp.status_code not in (200, 201):
        raise RuntimeError("CONSOLE_CREATE_FAILED:%s" % resp.status_code)
    return resp.json()["id"]


def send_console_input(session, username, token, console_id, text):
    url = API_BASE.format(user=username) + "/consoles/%s/send_input/" % console_id
    resp = session.post(url, headers=_headers(token), data={"input": text + "\n"}, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError("CONSOLE_INPUT_FAILED:%s" % resp.status_code)
    return True


def get_console_output(session, username, token, console_id):
    url = API_BASE.format(user=username) + "/consoles/%s/get_latest_output/" % console_id
    resp = session.get(url, headers=_headers(token), timeout=30)
    if resp.status_code != 200:
        raise RuntimeError("CONSOLE_OUTPUT_FAILED:%s" % resp.status_code)
    return resp.json().get("output", "")


def run_remote_command(session, username, token, command, wait_seconds=20, sleep_fn=time.sleep):
    console_id = create_console(session, username, token)
    send_console_input(session, username, token, console_id, command)
    sleep_fn(wait_seconds)
    return get_console_output(session, username, token, console_id)


def run_gate_b(approval, username, token, local_root, session=None, sleep_fn=time.sleep):
    check_approval(approval)
    if session is None:
        if requests is None:
            raise GateBBlocked("NO_REQUESTS_LIB")
        session = requests.Session()

    report = {"steps": []}

    for local_name in ("patcher_v4.py", "gate_b_installer_v4.py", "gate_b_postcheck_v4.py"):
        local_path = os.path.join(local_root, local_name)
        remote_path = "%s/%s" % (REMOTE_DIR, local_name)
        upload_file(session, username, token, remote_path, local_path)
        read_back(session, username, token, remote_path, local_path)
        report["steps"].append({"upload_readback": local_name, "status": "OK"})

    shadow_cmd = "cd /home/%s/%s && python3.10 gate_b_installer_v4.py --root /home/%s --shadow" % (
        username, REMOTE_DIR, username)
    shadow_out = run_remote_command(session, username, token, shadow_cmd, sleep_fn=sleep_fn)
    report["shadow_output"] = shadow_out
    if "SHADOW_PASS" not in shadow_out:
        report["status"] = "FAIL_SHADOW"
        return report

    install_cmd = "cd /home/%s/%s && python3.10 gate_b_installer_v4.py --root /home/%s --install" % (
        username, REMOTE_DIR, username)
    install_out = run_remote_command(session, username, token, install_cmd, wait_seconds=60, sleep_fn=sleep_fn)
    report["install_output"] = install_out
    try:
        install_json = _extract_json(install_out)
    except Exception:
        install_json = {}
    if install_json.get("status") != "INSTALL_PASS":
        report["status"] = "FAIL_INSTALL_ROLLED_BACK"
        return report

    task = find_launcher_task(session, username, token)
    restart_launcher(session, username, token, task["id"])
    report["restart"] = "OK"

    postcheck_cmd = "cd /home/%s/%s && python3.10 gate_b_postcheck_v4.py" % (username, REMOTE_DIR)
    postcheck_out = run_remote_command(session, username, token, postcheck_cmd, wait_seconds=90, sleep_fn=sleep_fn)
    report["postcheck_output"] = postcheck_out

    try:
        postcheck_json = _extract_json(postcheck_out)
    except Exception:
        postcheck_json = {}

    if postcheck_json.get("status") == "PASS":
        report["status"] = "PASS"
    else:
        backup_dir = install_json.get("backup_dir")
        rollback_cmd = "cd /home/%s/%s && python3.10 gate_b_installer_v4.py --root /home/%s --rollback --backup-dir %s" % (
            username, REMOTE_DIR, username, backup_dir)
        run_remote_command(session, username, token, rollback_cmd, sleep_fn=sleep_fn)
        restart_launcher(session, username, token, task["id"])
        report["status"] = "FAIL_POSTCHECK_ROLLED_BACK"

    return report


def main():
    approval = os.environ.get("GATE_B_APPROVAL", "")
    username = os.environ.get("PYTHONANYWHERE_USERNAME")
    token = os.environ.get("PYTHONANYWHERE_API_TOKEN")
    local_root = os.path.dirname(os.path.abspath(__file__))
    try:
        report = run_gate_b(approval, username, token, local_root)
    except GateBBlocked as exc:
        report = {"status": "BLOCKED", "reason": str(exc)}
    print(json.dumps(report, indent=2, sort_keys=True))
    if report.get("status") != "PASS":
        sys.exit(1)


if __name__ == "__main__":
    main()
