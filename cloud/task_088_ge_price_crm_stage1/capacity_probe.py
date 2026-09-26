#!/usr/bin/env python3
"""Read-only account quota helpers retained from TASK109; no probe output writes.

Only target-mount discovery and NFS rquota RPC are retained. Global filesystem
capacity is deliberately not accepted as account quota. Errors omit messages.
"""
from __future__ import annotations
import datetime as dt
import os
import socket
import struct
TARGET = "/home/Carix"

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
        return {"status": "unavailable", "phase": "portmap", "reason": type(exc).__name__}

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
            limit_blocks = hard_blocks
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
                "reason": type(exc).__name__,
            })
    return {"status": "unavailable", "phase": "rquota", "attempts": attempts}
