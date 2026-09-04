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
import socket
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
    public_mount = {
        key: mount[key]
        for key in ("status", "mountpoint", "filesystem", "major_minor", "reason")
        if key in mount
    }
    return {"mount": public_mount, "project": project, "attempts": attempts, "successes": successes}


def xdr_u32(value: int) -> bytes:
    return struct.pack("!I", int(value) & 0xFFFFFFFF)


def xdr_opaque(value: bytes) -> bytes:
    padding = (-len(value)) % 4
    return xdr_u32(len(value)) + value + (b"\0" * padding)


class XdrReader:
    def __init__(self, value: bytes) -> None:
        self.value = value
        self.offset = 0

    def u32(self) -> int:
        if self.offset + 4 > len(self.value):
            raise RuntimeError("XDR_TRUNCATED")
        result = struct.unpack("!I", self.value[self.offset:self.offset + 4])[0]
        self.offset += 4
        return int(result)

    def opaque(self) -> bytes:
        length = self.u32()
        end = self.offset + length
        if end > len(self.value):
            raise RuntimeError("XDR_OPAQUE_TRUNCATED")
        result = self.value[self.offset:end]
        self.offset = end + ((-length) % 4)
        return result

    def remaining(self) -> bytes:
        return self.value[self.offset:]


def rpc_unix_auth() -> bytes:
    hostname = socket.gethostname().encode("utf-8", "replace")[:255]
    groups = [int(value) for value in os.getgroups()[:16]]
    body = (
        xdr_u32(int(dt.datetime.now(dt.timezone.utc).timestamp()))
        + xdr_opaque(hostname)
        + xdr_u32(os.getuid())
        + xdr_u32(os.getgid())
        + xdr_u32(len(groups))
        + b"".join(xdr_u32(value) for value in groups)
    )
    return xdr_u32(1) + xdr_opaque(body)


def rpc_call_udp(host: str, port: int, program: int, version: int, procedure: int,
                 arguments: bytes, *, unix_auth: bool) -> bytes:
    xid = struct.unpack("!I", os.urandom(4))[0]
    credential = rpc_unix_auth() if unix_auth else xdr_u32(0) + xdr_u32(0)
    request = (
        xdr_u32(xid) + xdr_u32(0) + xdr_u32(2)
        + xdr_u32(program) + xdr_u32(version) + xdr_u32(procedure)
        + credential + xdr_u32(0) + xdr_u32(0) + arguments
    )
    last_error = None
    for _ in range(2):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                client.settimeout(5)
                client.sendto(request, (host, int(port)))
                reply, _ = client.recvfrom(65535)
            reader = XdrReader(reply)
            if reader.u32() != xid or reader.u32() != 1:
                raise RuntimeError("RPC_IDENTITY")
            if reader.u32() != 0:
                raise RuntimeError("RPC_DENIED")
            reader.u32()
            reader.opaque()
            accept_status = reader.u32()
            if accept_status != 0:
                raise RuntimeError("RPC_ACCEPT_STATUS_%d" % accept_status)
            return reader.remaining()
        except Exception as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def portmap_get_udp_port(host: str, program: int, version: int) -> int:
    # Portmapper v2 GETPORT; protocol 17 is UDP.
    reply = rpc_call_udp(
        host, 111, 100000, 2, 3,
        xdr_u32(program) + xdr_u32(version) + xdr_u32(17) + xdr_u32(0),
        unix_auth=False,
    )
    port = XdrReader(reply).u32()
    if port <= 0 or port > 65535:
        raise RuntimeError("RPC_PROGRAM_NOT_REGISTERED")
    return port


def nfs_rquota_probe(mount: dict) -> dict:
    """Read the account's NFS quota using Sun's standard rquota v1 RPC."""
    source = str(mount.get("source", ""))
    if mount.get("filesystem") not in {"nfs", "nfs4"} or ":" not in source:
        return {"status": "unavailable", "reason": "not_nfs"}
    server, export = source.split(":", 1)
    try:
        port = portmap_get_udp_port(server, 100011, 1)
    except Exception as exc:
        return {"status": "unavailable", "phase": "portmap", "reason": type(exc).__name__ + ":" + str(exc)}

    arguments = xdr_opaque(export.encode("utf-8")) + xdr_u32(os.getuid())
    attempts = []
    for procedure in (2, 1):
        try:
            reply = rpc_call_udp(
                server, port, 100011, 1, procedure, arguments, unix_auth=True,
            )
            reader = XdrReader(reply)
            status = reader.u32()
            attempt = {"procedure": procedure, "quota_status": status}
            attempts.append(attempt)
            if status != 1:
                continue
            block_size = reader.u32()
            active = bool(reader.u32())
            hard_blocks = reader.u32()
            soft_blocks = reader.u32()
            current_blocks = reader.u32()
            file_hard = reader.u32()
            file_soft = reader.u32()
            current_files = reader.u32()
            block_time_left = reader.u32()
            file_time_left = reader.u32()
            limit_blocks = hard_blocks or soft_blocks
            if not active or block_size <= 0 or limit_blocks <= 0:
                return {
                    "status": "unavailable", "reason": "quota_inactive_or_unlimited",
                    "attempts": attempts,
                }
            total_bytes = int(block_size) * int(limit_blocks)
            used_bytes = int(block_size) * int(current_blocks)
            return {
                "status": "PASS",
                "protocol": "NFS_RQUOTA_V1_UDP",
                "procedure": procedure,
                "active": active,
                "block_size": int(block_size),
                "block_hard_limit": int(hard_blocks),
                "block_soft_limit": int(soft_blocks),
                "current_blocks": int(current_blocks),
                "file_hard_limit": int(file_hard),
                "file_soft_limit": int(file_soft),
                "current_files": int(current_files),
                "block_time_left": int(block_time_left),
                "file_time_left": int(file_time_left),
                "total_bytes": total_bytes,
                "used_bytes": used_bytes,
                "free_bytes": max(total_bytes - used_bytes, 0),
            }
        except Exception as exc:
            attempts.append({
                "procedure": procedure,
                "reason": type(exc).__name__ + ":" + str(exc),
            })
    return {"status": "unavailable", "phase": "rquota", "attempts": attempts}


def main() -> int:
    usage = shutil.disk_usage(TARGET)
    mount = target_mount()
    remote_quota = nfs_rquota_probe(mount)
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

    if remote_quota.get("status") == "PASS":
        total_bytes = int(remote_quota["total_bytes"])
        used_bytes = int(remote_quota["used_bytes"])
        free_bytes = int(remote_quota["free_bytes"])
        measurement = "NFS rquota v1 target-account hard quota"
    else:
        # Diagnostic fallback only. A global NFS volume measurement must not
        # be treated as the account quota by a production storage gate.
        total_bytes = int(usage.total)
        used_bytes = total_bytes - int(usage.free)
        free_bytes = int(usage.free)
        measurement = "shutil.disk_usage:/home/Carix;global-volume-fallback"
    value = {
        "target_environment": "production",
        "read_only": True,
        "measured_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "total_bytes": total_bytes,
        "used_bytes": used_bytes,
        "free_bytes": free_bytes,
        "measurement": measurement,
        "task_id": "TASK109-CONTAINER-TRACK-INLINE",
        "diagnostics": {
            "nfs_rquota": remote_quota,
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
