"""Pure exact-source TASK083 patch; never imports or installs the application."""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

SOURCE_SHA256 = "13dbcbced164c73bb1767fee6d35ca9597c14b552baaeb31ebbf90cad70b1b46"
MARKER = "UAART-TASK083-WRITER-COORDINATION-001"

ADMISSION = '''# UAART-TASK083-WRITER-COORDINATION-001
import functools as _ua083_functools
import stat as _ua083_stat
import threading as _ua083_threading
_ua083_local = _ua083_threading.local()


def _ua083_check_intent():
    try:
        os.lstat(ROOT / ".uaart_writer_coordination" / "active-intent.json")
    except FileNotFoundError:
        return
    raise Blocked("TASK083_DEFERRED_DURABLE_WRITER_INTENT")


def _ua083_identity(path, fd=None):
    named = os.stat(path, follow_symlinks=False)
    opened = os.fstat(fd) if fd is not None else named
    if (not _ua083_stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
            or not _ua083_stat.S_ISREG(named.st_mode)
            or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)):
        raise Blocked("TASK083_DEFERRED_UNSAFE_WRITER_LOCK")
    return (opened.st_dev, opened.st_ino)


def _ua083_guard(function):
    @_ua083_functools.wraps(function)
    def guarded(*args, **kwargs):
        held = getattr(_ua083_local, "held", None)
        if held is not None:
            if held[2] != os.getpid():
                raise Blocked("TASK083_DEFERRED_INHERITED_ADMISSION")
            for path, identity in held[1]:
                if _ua083_identity(path) != identity:
                    raise Blocked("TASK083_DEFERRED_WRITER_LOCK_REPLACED")
            _ua083_check_intent()
            return function(*args, **kwargs)
        fd = None
        admitted = False
        try:
            publication = ROOT / ".ua_art_publish_transaction.lock"
            # Existing inode only: never create/truncate/replace a writer lock.
            fd = os.open(publication, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
            identity = _ua083_identity(publication, fd)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if _ua083_identity(publication, fd) != identity:
                raise Blocked("TASK083_DEFERRED_WRITER_LOCK_REPLACED")
            identities = [(publication, identity)]
            # Preserve main's existing acquisition order for these three locks.
            for path in (TASK082_INSTALL_LOCK, TASK082_RUNTIME_LOCK, LOCK_PATH):
                identities.append((path, _ua083_identity(path)))
            _ua083_check_intent()
            _ua083_local.held = (fd, identities, os.getpid())
            admitted = True
            return function(*args, **kwargs)
        except OSError:
            if admitted:
                raise
            raise Blocked("TASK083_DEFERRED_WRITER_COORDINATION") from None
        finally:
            if fd is not None:
                _ua083_local.held = None
                os.close(fd)
    return guarded


'''


def patch(source: bytes) -> bytes:
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError("TASK083_SOURCE_DRIFT")
    original = source.decode("utf-8")
    tree = ast.parse(original)
    targets = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {"run_install", "run_rollback", "main"}]
    if len(targets) != 3 or any(n.decorator_list for n in targets):
        raise ValueError("TASK083_ENTRYPOINT_DRIFT")
    lines = original.splitlines(keepends=True)
    insertions = {n.lineno: "@_ua083_guard\n" for n in targets}
    first = min(n.lineno for n in targets)
    changed = "".join((ADMISSION if i == first else "") + insertions.get(i, "") + line
                      for i, line in enumerate(lines, 1))
    # Main must not create missing legacy lock files or touch their metadata.
    old = "    for path in (TASK082_INSTALL_LOCK, TASK082_RUNTIME_LOCK, LOCK_PATH):\n        path.touch(exist_ok=True)\n"
    if changed.count(old) != 1:
        raise ValueError("TASK083_LOCK_INITIALIZER_DRIFT")
    changed = changed.replace(old, "", 1)
    result_tree = ast.parse(changed)
    # Only three decorators and the reviewed lock initializer removal can alter
    # existing AST. All installer/rollback payload and old lock order are intact.
    helpers = {"_ua083_check_intent", "_ua083_identity", "_ua083_guard"}
    new_body = [n for n in result_tree.body if not
                (isinstance(n, ast.FunctionDef) and n.name in helpers) and not
                (isinstance(n, ast.Import) and any(a.asname and a.asname.startswith("_ua083_") for a in n.names)) and not
                (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_ua083_local" for t in n.targets))]
    for node in new_body:
        if isinstance(node, ast.FunctionDef) and node.name in {"run_install", "run_rollback", "main"}:
            node.decorator_list = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            node.body = [n for n in node.body if not (isinstance(n, ast.For) and
                         isinstance(n.iter, ast.Tuple) and [getattr(e, "id", None) for e in n.iter.elts] ==
                         ["TASK082_INSTALL_LOCK", "TASK082_RUNTIME_LOCK", "LOCK_PATH"])]
    result_tree.body = new_body
    if ast.dump(result_tree, include_attributes=False) != ast.dump(tree, include_attributes=False):
        raise ValueError("TASK083_OUTSIDE_ADMISSION_AST_CHANGED")
    return changed.encode("utf-8")


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    result = patch(args.source.read_bytes())
    with args.destination.open("xb") as out:
        out.write(result)
    print(hashlib.sha256(result).hexdigest())


if __name__ == "__main__":
    main()
