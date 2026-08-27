"""
safe_writer.py

Hardened SafeWriter. All Gate A writes must go through this module. It
never writes outside its resolved run root, never follows symlinks,
rejects hard-link targets, verifies free space before writing, and
performs atomic fsync'd writes with a restrictive file mode.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile

MIN_FREE_BYTES_MARGIN = 10 * 1024 * 1024


class SafeWriterError(Exception):
    pass


class InsufficientSpaceError(SafeWriterError):
    pass


class UnsafePathError(SafeWriterError):
    pass


class SafeWriter:
    def __init__(self, run_root: str):
        if os.path.islink(run_root):
            raise UnsafePathError(f"run root must not be a symlink: {run_root}")
        os.makedirs(run_root, exist_ok=True)
        self.run_root = os.path.realpath(run_root)

    def _resolve_inside_root(self, relpath: str) -> str:
        if os.path.isabs(relpath):
            raise UnsafePathError("relpath must be relative")
        candidate = os.path.normpath(os.path.join(self.run_root, relpath))
        if candidate != self.run_root and not candidate.startswith(self.run_root + os.sep):
            raise UnsafePathError(f"path escapes run root: {relpath}")
        self._assert_no_symlink_parents(candidate)
        return candidate

    def _assert_no_symlink_parents(self, path: str) -> None:
        current = self.run_root
        rel = os.path.relpath(path, self.run_root)
        parts = rel.split(os.sep)
        for part in parts[:-1]:
            current = os.path.join(current, part)
            if os.path.islink(current):
                raise UnsafePathError(f"symlink in parent path: {current}")

    def _check_free_space(self, nbytes: int) -> None:
        usage = shutil.disk_usage(self.run_root)
        if usage.free < nbytes + MIN_FREE_BYTES_MARGIN:
            raise InsufficientSpaceError(
                f"insufficient free space: need {nbytes + MIN_FREE_BYTES_MARGIN}, "
                f"have {usage.free}"
            )

    def _reject_unsafe_existing_target(self, path: str) -> None:
        try:
            st = os.lstat(path)
        except FileNotFoundError:
            return
        if stat.S_ISLNK(st.st_mode):
            raise UnsafePathError(f"refusing to overwrite symlink: {path}")
        if not stat.S_ISREG(st.st_mode):
            raise UnsafePathError(f"refusing to overwrite non-regular file: {path}")
        if st.st_nlink != 1:
            raise UnsafePathError(f"refusing to overwrite hard-linked file: {path}")

    def write_bytes(self, relpath: str, data: bytes) -> str:
        target = self._resolve_inside_root(relpath)
        self._reject_unsafe_existing_target(target)
        self._check_free_space(len(data))
        target_dir = os.path.dirname(target)
        os.makedirs(target_dir, exist_ok=True)
        self._assert_no_symlink_parents(target)
        fd, tmp_path = tempfile.mkstemp(prefix=".swtmp_", dir=target_dir)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, target)
        except Exception:
            try:
                os.remove(tmp_path)
            except FileNotFoundError:
                pass
            raise
        dir_fd = os.open(target_dir, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        return hashlib.sha256(data).hexdigest()

    def read_source_no_follow(self, path: str) -> bytes:
        if os.path.islink(path):
            raise UnsafePathError(f"refusing to read symlink: {path}")
        pre = os.lstat(path)
        if stat.S_ISLNK(pre.st_mode):
            raise UnsafePathError(f"refusing to read symlink: {path}")
        if pre.st_nlink != 1:
            raise UnsafePathError(f"refusing to read hard-linked source: {path}")
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, os.O_RDONLY | nofollow)
        try:
            post = os.fstat(fd)
            if (post.st_ino, post.st_dev) != (pre.st_ino, pre.st_dev):
                raise UnsafePathError(f"target swapped between lstat and open: {path}")
            data = b""
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                data += chunk
            return data
        finally:
            os.close(fd)

    @staticmethod
    def fingerprint(path: str) -> dict:
        st = os.lstat(path)
        if stat.S_ISLNK(st.st_mode):
            raise UnsafePathError(f"refusing to fingerprint symlink: {path}")
        with open(path, "rb") as fh:
            data = fh.read()
        return {
            "path": path, "mode": oct(st.st_mode), "size": st.st_size,
            "mtime_ns": st.st_mtime_ns, "sha256": hashlib.sha256(data).hexdigest(),
        }
