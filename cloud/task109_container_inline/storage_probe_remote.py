#!/usr/bin/env python3
"""Read-only production filesystem capacity probe for TASK109."""
from __future__ import annotations

import datetime as dt
import ctypes
import errno
import fcntl
import json
import os
import shutil
import struct
import subprocess
import tempfile


TARGET = "/home/Carix"
OUTPUT = "/home/Carix/autopilot_inbox/cloud/task_068_ferry_vin/task109_storage_probe.json"


class IfDqblk(ctypes.Structure):
    """Linux generic quota structure from <linux/quota.h>."""

    _fields_ = [
        ("dqb_bhardlimit", ctypes.c_uint64),
        ("dqb_bsoftlimit", ctypes.c_uint64),
        ("dqb_curspace", ctypes.c_uint64),
        ("dqb_ihardlimit", ctypes.c_uint64),
        ("dqb_isoftlimit", ctypes.c_uint64),
        ("dqb_curinodes", ctypes.c_uint64),
        ("dqb_btime", ctypes.c_uint64),
        ("dqb_itime", ctypes.c_uint64),
        ("dqb_valid", ctypes.c_uint32),
    ]


def quota_command(command: int, quota_type: int) -> int:
    return (command << 8) | quota_type


def target_mount() -> dict:
    """Return the mount record matching TARGET without exposing unrelated mounts."""
    wanted = os.stat(TARGET).st_dev
    major_minor = "%d:%d" % (os.major(wanted), os.minor(wanted))
    candidates = []
    with open("/proc/self/mountinfo", "r", encoding="utf-8") as handle:
        for line in handle:
            left, separator, right = line.rstrip("\n").partition(" - ")
            if not separator:
                continue
            fields = left.split()
            tail = right.split()
            if len(fields) < 6 or len(tail) < 2 or fields[2] != major_minor:
                continue
            mountpoint = fields[4].replace("\\040", " ")
            if TARGET == mountpoint or TARGET.startswith(mountpoint.rstrip("/") + "/"):
                candidates.append((len(mountpoint), mountpoint, tail[0], tail[1]))
    if not candidates:
        return {"status": "unavailable", "reason": "target_mount_not_found"}
    _, mountpoint, filesystem, source = max(candidates)
    return {
        "status": "found",
        "mountpoint": mountpoint,
        "filesystem": filesystem,
        "source": source,
        "major_minor": major_minor,
    }


def target_project_id() -> dict:
    """Read the Linux/XFS project id assigned to TARGET, when supported."""
    # FS_IOC_FSGETXATTR = _IOR('X', 31, struct fsxattr), sizeof(fsxattr)=28.
    buffer = bytearray(28)
    try:
        descriptor = os.open(TARGET, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            fcntl.ioctl(descriptor, 0x801C581F, buffer, True)
        finally:
            os.close(descriptor)
        values = struct.unpack("=5I8s", buffer)
        return {"status": "found", "project_id": int(values[3]), "xflags": int(values[0])}
    except OSError as exc:
        return {"status": "unavailable", "errno": exc.errno, "reason": errno.errorcode.get(exc.errno, str(exc.errno))}


def kernel_quota_probe() -> dict:
    """Query read-only kernel user/project quotas without requiring `quota(1)`."""
    mount = target_mount()
    project = target_project_id()
    identities = [("user", 0, os.getuid())]
    if project.get("status") == "found":
        identities.append(("project", 2, int(project["project_id"])))
    specials = []
    if mount.get("status") == "found":
        specials.extend([mount["source"], mount["mountpoint"]])
    specials.append(TARGET)
    specials = list(dict.fromkeys(str(value) for value in specials if value))

    libc = ctypes.CDLL(None, use_errno=True)
    quotactl = libc.quotactl
    quotactl.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p]
    quotactl.restype = ctypes.c_int
    attempts = []
    successes = []
    q_getquota = 0x800007
    for identity_name, quota_type, identity in identities:
        for special in specials:
            record = IfDqblk()
            ctypes.set_errno(0)
            result = quotactl(
                quota_command(q_getquota, quota_type),
                special.encode("utf-8"),
                int(identity),
                ctypes.byref(record),
            )
            attempt = {
                "identity": identity_name,
                "special_kind": (
                    "source" if mount.get("source") == special else
                    "mountpoint" if mount.get("mountpoint") == special else
                    "target"
                ),
                "returncode": int(result),
            }
            if result == 0:
                item = {
                    **attempt,
                    "identity_id": int(identity),
                    "block_hard_limit_bytes": int(record.dqb_bhardlimit) * 1024,
                    "block_soft_limit_bytes": int(record.dqb_bsoftlimit) * 1024,
                    "current_space_bytes": int(record.dqb_curspace),
                    "valid_mask": int(record.dqb_valid),
                }
                attempts.append(item)
                successes.append(item)
            else:
                error_number = ctypes.get_errno()
                attempt.update({
                    "errno": int(error_number),
                    "reason": errno.errorcode.get(error_number, str(error_number)),
                })
                attempts.append(attempt)
    return {"mount": mount, "project": project, "attempts": attempts, "successes": successes}


def main() -> int:
    usage = shutil.disk_usage(TARGET)
    def run_read_only(argv):
        try:
            completed = subprocess.run(
                argv, check=False, capture_output=True, text=True, timeout=120,
            )
            return {
                "argv": argv,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-2000:],
            }
        except Exception as exc:
            return {"argv": argv, "error": type(exc).__name__ + ":" + str(exc)}

    # statvfs/shutil may report system-reserved blocks in ``used`` while
    # ``free`` is user-available capacity.  The control plane intentionally
    # reasons about the user-visible quota, so derive its matching used value.
    user_used = int(usage.total) - int(usage.free)
    value = {
        "target_environment": "production",
        "read_only": True,
        "measured_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "total_bytes": int(usage.total),
        "used_bytes": user_used,
        "free_bytes": int(usage.free),
        "measurement": "shutil.disk_usage:/home/Carix;used=total-user_available_free",
        "task_id": "TASK109-CONTAINER-TRACK-INLINE",
        "diagnostics": {
            "kernel_quota": kernel_quota_probe(),
            "quota_bytes": run_read_only(["quota", "-w"]),
            "quota_human": run_read_only(["quota", "-s"]),
            "official_du_bytes": run_read_only(["du", "-s", "-B", "1", "/tmp", "/home/Carix", "/var/www"]),
        },
    }
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=os.path.dirname(OUTPUT),
        prefix=".task109-storage-", suffix=".tmp", delete=False,
    )
    temporary = handle.name
    try:
        with handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, OUTPUT)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
