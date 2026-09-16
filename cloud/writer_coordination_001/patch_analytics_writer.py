"""Pure, exact-source patch for the observed request-driven HTML writer.

This prepares bytes only. It does not upload/reload WSGI or claim legacy drain.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path

SOURCE_SHA256 = "a73be46099596322dcd607ecadd56140d45483a5ad38f1c1a0a0e395cfc8bc94"
MARKER = "UAART-ANALYTICS-WRITER-COORDINATION-001"


def patch(source: bytes) -> bytes:
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError("ANALYTICS_SOURCE_DRIFT")
    text = source.decode("utf-8")
    tree = ast.parse(text)
    matches = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_storozh"]
    if len(matches) != 1:
        raise ValueError("ANALYTICS_FUNCTION_DRIFT")
    node = matches[0]
    lines = text.splitlines(keepends=True)
    original_body = "".join("    " + line if line.strip() else line for line in lines[node.lineno:node.end_lineno])
    replacement = '''def _storozh():
    # UAART-ANALYTICS-WRITER-COORDINATION-001
    # Defer this optional maintenance pass; ordinary HTTP responses still work.
    if time.time() - _FON[0] < 120:
        return
    _ua_fd = None
    try:
        import fcntl as _ua_fcntl
        import stat as _ua_stat
        _ua_lock = os.path.join(DOM, ".ua_art_publish_transaction.lock")
        # Never create/recreate the inode used by existing publishers.
        _ua_fd = os.open(_ua_lock, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        _ua_opened = os.fstat(_ua_fd)
        _ua_named = os.stat(_ua_lock, follow_symlinks=False)
        if (not _ua_stat.S_ISREG(_ua_opened.st_mode)
                or _ua_opened.st_nlink != 1
                or (_ua_opened.st_dev, _ua_opened.st_ino)
                != (_ua_named.st_dev, _ua_named.st_ino)):
            raise OSError("ANALYTICS_LOCK_UNSAFE")
        _ua_fcntl.flock(_ua_fd, _ua_fcntl.LOCK_EX | _ua_fcntl.LOCK_NB)
        _ua_named = os.stat(_ua_lock, follow_symlinks=False)
        if (_ua_opened.st_dev, _ua_opened.st_ino) != (_ua_named.st_dev, _ua_named.st_ino):
            raise OSError("ANALYTICS_LOCK_REPLACED")
        # Persistent intent continues to deny writes after holder death/TTL.
        try:
            os.lstat(os.path.join(DOM, ".uaart_writer_coordination", "active-intent.json"))
        except FileNotFoundError:
            pass
        else:
            return
'''
    replacement += original_body
    replacement += '''    except (OSError, ValueError):
        return
    finally:
        if _ua_fd is not None:
            os.close(_ua_fd)
'''
    changed = "".join(lines[:node.lineno - 1]) + replacement + "".join(lines[node.end_lineno:])
    ast.parse(changed)
    if changed.count(MARKER) != 1:
        raise ValueError("ANALYTICS_PATCH_MARKER_INVALID")
    return changed.encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    result = patch(args.source.read_bytes())
    # Exclusive destination; no production mutation or overwrite option.
    with args.destination.open("xb") as output:
        output.write(result)
    print(hashlib.sha256(result).hexdigest())


if __name__ == "__main__":
    main()
