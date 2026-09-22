#!/usr/bin/env python3
"""Build a scoped candidate from the verified LIVE publisher, never replace it with TASK083."""
import argparse
import ast
import hashlib
from pathlib import Path

SNAPSHOT = '    paths: set[pathlib.Path] = {root / "katalog.html" for root in ROOTS}'
WITH_HOMES = SNAPSHOT + '\n    paths.update(root / "index.html" for root in ROOTS)'
RETURN = '    return {\n        "candidate": before,'
RESTORE = '        current = _matching_paths(self.codes)'
SAFE_RESTORE = RESTORE + '\n        current -= {root / "index.html" for root in ROOTS} - self.before_paths'
HOOK = '''    # UA-ART-HOME-TOTAL-AUTO-001: caller already owns the publication lock.
    from home_total import patch_home_total
    for home_root in ROOTS:
        home_path = home_root / "index.html"
        home_before = _read(home_path)
        home_after = patch_home_total(home_before.decode("utf-8"), len(row_map)).encode("utf-8")
        if home_after != home_before:
            _atomic(home_path, home_after, home_path.stat().st_mode & 0o777)
        if _read(home_path) != home_after:
            raise PublishError("HOME_TOTAL_READBACK_MISMATCH:" + str(home_path))
'''


def patch_publisher(source):
    tree = ast.parse(source)
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Snapshot":
            functions.update({"Snapshot." + child.name: child for child in node.body
                              if isinstance(child, ast.FunctionDef)})
    lines = source.splitlines(keepends=True)
    changes = []
    for name, old, new in (("_matching_paths", SNAPSHOT, WITH_HOMES),
                           ("_install_catalog", RETURN, HOOK + RETURN),
                           ("Snapshot.restore", RESTORE, SAFE_RESTORE)):
        if name not in functions:
            raise ValueError("PUBLISHER_FUNCTION_MISSING:" + name)
        node = functions[name]
        start, end = sum(map(len, lines[:node.lineno - 1])), sum(map(len, lines[:node.end_lineno]))
        segment = source[start:end]
        if new in segment:
            continue
        if segment.count(old) != 1:
            raise ValueError("PUBLISHER_ANCHOR_MISMATCH:" + name)
        changes.append((start, end, segment.replace(old, new, 1)))
    for start, end, replacement in sorted(changes, reverse=True):
        source = source[:start] + replacement + source[end:]
    ast.parse(source)
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    if args.source.resolve() == args.candidate.resolve():
        raise ValueError("CANDIDATE_MUST_BE_SEPARATE")
    data = args.source.read_bytes()
    if hashlib.sha256(data).hexdigest() != args.expected_sha256:
        raise ValueError("LIVE_SOURCE_HASH_MISMATCH")
    candidate = patch_publisher(data.decode("utf-8"))
    with args.candidate.open("x", encoding="utf-8") as stream:
        stream.write(candidate)


if __name__ == "__main__":
    main()
