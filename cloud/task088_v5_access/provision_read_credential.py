#!/usr/bin/env python3
"""Receive one owner-provided GitHub fine-grained token through a hidden TTY.

No network, reader activation, credential discovery, command-line secret, or
environment secret is supported. Permission scope is selected by the owner on
GitHub; the token's actual scope cannot be established by this offline receiver.
"""

import getpass
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import warnings


HOME_DIRECTORY = Path("/home/Carix")
TOKEN_NAME = "github-read.token"
TOKEN_PATTERN = re.compile(r"github_pat_[A-Za-z0-9_]{20,240}\Z")


class ProvisionError(Exception):
    """Only fixed, non-secret codes cross the public error boundary."""


def _flags():
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ProvisionError("E_PLATFORM")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _open_home(home):
    """Walk every absolute path component without following symlinks."""
    home = Path(home)
    if not home.is_absolute() or ".." in home.parts:
        raise ProvisionError("E_HOME")
    descriptor = os.open("/", _flags())
    try:
        for component in home.parts[1:]:
            child = os.open(component, _flags(), dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        info = os.fstat(descriptor)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o022:
            raise ProvisionError("E_HOME_PERMISSIONS")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _child_directory(parent, name, *, private):
    created = False
    try:
        os.mkdir(name, 0o700, dir_fd=parent)
        created = True
    except FileExistsError:
        pass
    descriptor = os.open(name, _flags(), dir_fd=parent)
    try:
        if created:
            os.fchmod(descriptor, 0o700)
        info = os.fstat(descriptor)
        mode = stat.S_IMODE(info.st_mode)
        # A pre-existing .config may be readable; the token directory must be 700.
        if (info.st_uid != os.geteuid() or mode & 0o022
                or (private and mode != 0o700)):
            raise ProvisionError("E_DIRECTORY_PERMISSIONS")
        os.fsync(parent)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def open_token_directory(home=HOME_DIRECTORY):
    descriptor = _open_home(home)
    try:
        child = _child_directory(descriptor, ".config", private=False)
        os.close(descriptor)
        descriptor = child
        child = _child_directory(descriptor, "uaart-price-control", private=True)
        os.close(descriptor)
        descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def require_absent(parent):
    try:
        os.stat(TOKEN_NAME, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise ProvisionError("E_ALREADY_EXISTS")


def read_hidden_token():
    if not sys.stdin.isatty():
        raise ProvisionError("E_TTY_REQUIRED")
    try:
        # A controlling TTY is mandatory. The prompt never uses a redirected log.
        tty_descriptor = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
        with os.fdopen(tty_descriptor, "w", encoding="utf-8") as terminal:
            if not terminal.isatty():
                raise ProvisionError("E_TTY_REQUIRED")
            with warnings.catch_warnings():
                # getpass warns before falling back to echoed input: prohibit it.
                warnings.simplefilter("error", getpass.GetPassWarning)
                token = getpass.getpass("GitHub read-only token (hidden): ", stream=terminal)
    except (KeyboardInterrupt, EOFError):
        raise ProvisionError("E_INPUT_ABORTED") from None
    except getpass.GetPassWarning:
        raise ProvisionError("E_HIDDEN_INPUT_UNAVAILABLE") from None
    except OSError:
        raise ProvisionError("E_TTY_REQUIRED") from None
    if not TOKEN_PATTERN.fullmatch(token):
        raise ProvisionError("E_TOKEN_FORMAT")
    return token


def _remove_owned_partial(parent, identity, name=TOKEN_NAME):
    """Never remove a replacement file created by another process."""
    try:
        current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (current.st_dev, current.st_ino) == identity:
            os.unlink(name, dir_fd=parent)
            os.fsync(parent)
    except FileNotFoundError:
        pass


def store_token(parent, token):
    if not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token):
        raise ProvisionError("E_TOKEN_FORMAT")
    require_absent(parent)
    temporary_name = ".receive-" + secrets.token_hex(16)
    try:
        descriptor = os.open(temporary_name,
                             os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=parent)
    except FileExistsError:
        raise ProvisionError("E_ALREADY_EXISTS") from None
    info = os.fstat(descriptor)
    identity = (info.st_dev, info.st_ino)
    try:
        os.fchmod(descriptor, 0o600)
        data = (token + "\n").encode("ascii")
        offset = 0
        while offset < len(data):
            count = os.write(descriptor, data[offset:])
            if count <= 0:
                raise ProvisionError("E_WRITE")
            offset += count
        os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.read(descriptor, len(data) + 1) != data:
            raise ProvisionError("E_READ_BACK")
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise ProvisionError("E_FILE_PERMISSIONS")
        # Publish only complete, synced bytes. link is atomic and never overwrites.
        try:
            os.link(temporary_name, TOKEN_NAME, src_dir_fd=parent,
                    dst_dir_fd=parent, follow_symlinks=False)
        except FileExistsError:
            raise ProvisionError("E_ALREADY_EXISTS") from None
        os.unlink(temporary_name, dir_fd=parent)
        current = os.stat(TOKEN_NAME, dir_fd=parent, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != identity:
            raise ProvisionError("E_FILE_REPLACED")
        os.fsync(parent)
    except BaseException:
        _remove_owned_partial(parent, identity)
        _remove_owned_partial(parent, identity, temporary_name)
        raise
    finally:
        os.close(descriptor)


def main():
    parent = None
    try:
        if len(sys.argv) != 1:
            raise ProvisionError("E_ARGUMENTS")
        if not sys.stdin.isatty():
            raise ProvisionError("E_TTY_REQUIRED")
        parent = open_token_directory()
        require_absent(parent)
        token = read_hidden_token()
        try:
            store_token(parent, token)
        finally:
            # Python does not promise memory erasure; no extra durable copy exists.
            token = None
        print("UAART_READ_CREDENTIAL_READY")
        return 0
    except ProvisionError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("E_INPUT_ABORTED", file=sys.stderr)
        return 1
    except Exception:
        # Exception messages and tracebacks can contain secrets: never print them.
        print("E_PROVISION", file=sys.stderr)
        return 1
    finally:
        if parent is not None:
            os.close(parent)


if __name__ == "__main__":
    raise SystemExit(main())
