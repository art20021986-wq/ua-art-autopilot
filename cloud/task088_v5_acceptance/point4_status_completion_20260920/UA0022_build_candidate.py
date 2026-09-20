#!/usr/bin/env python3
"""Build only the source-pinned UA-0022 publication/rebuild serialization fix.

Private inputs are never imported or executed. Generated private runtime
sources must stay private; this builder and its small additive patch are safe
to review separately. Building this candidate does not install anything.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path

CONTRACT = "UA-ART-UA0022-REBUILD-SERIALIZATION-001-v1.0"
SOURCE_SHA256 = {
    "cars_ui.py": "4c00512c56ee19ccda4ff0086aa696facf8aeea013c894168007c78c9490adde",
    "stranica.py": "2794f01c00a49f1a55c66f3e6af4657808f857e9167f59a5da84c9b8430d724a",
    "publish_transaction_guard.py": "3d80712290e0881ebe7583231b532de422f808e6f18b5f6a90566d9e1eed3e0d",
    "publikaciya.py": "296c389b477472032bad714e41f12bfa4b7e47ad784ac6900ba55f136d939c72",
}
HELPER_SHA256 = "c739a1017c53c6391dbf875621d6c860216fe8a132b738eef47b8f8019594a21"
MARKER = "UA-ART-UA0022-REBUILD-SERIALIZATION-V1"

CARS_BLOCK = '''

# UA-ART-UA0022-REBUILD-SERIALIZATION-V1:CARS:START
from publication_fence import publication_fence as _ua0022_publication_fence

def _ua0022_wrap_rebuild(original):
    def guarded():
        # Keep reload and the entire rebuild in one publication interval.
        try:
            with _ua0022_publication_fence(timeout=90.0):
                return original()
        except Exception as exc:
            log.warning("Пересборка страниц: %s", exc)
            return False
    return guarded

_peresobrat_stranicy = _ua0022_wrap_rebuild(_peresobrat_stranicy)
# UA-ART-UA0022-REBUILD-SERIALIZATION-V1:CARS:END
'''

STRANICA_BLOCK = '''

# UA-ART-UA0022-REBUILD-SERIALIZATION-V1:STRANICA:START
from publication_fence import publication_fence as _ua0022_publication_fence

def _ua0022_wrap_main(original):
    def guarded(*args, **kwargs):
        # Include rendering, page writes, validation and legacy restoration.
        with _ua0022_publication_fence(timeout=90.0):
            return original(*args, **kwargs)
    return guarded

main = _ua0022_wrap_main(main)
# UA-ART-UA0022-REBUILD-SERIALIZATION-V1:STRANICA:END
'''

GUARD_BLOCK = '''

# UA-ART-UA0022-REBUILD-SERIALIZATION-V1:GUARD:START
from publication_fence import publication_fence as _ua0022_publication_fence

def _exclusive_lock():
    # Same inode as legacy publishers; one registry makes nesting reentrant.
    return _ua0022_publication_fence(timeout=WAIT_SECONDS)
# UA-ART-UA0022-REBUILD-SERIALIZATION-V1:GUARD:END
'''


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def transform(name: str, source: str) -> str:
    if MARKER in source:
        raise ValueError("ALREADY_PATCHED:" + name)
    tree = ast.parse(source, filename=name)
    functions = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if name == "cars_ui.py":
        if "_peresobrat_stranicy" not in functions:
            raise ValueError("REBUILD_BOUNDARY_MISSING")
        result = source + CARS_BLOCK
    elif name == "stranica.py":
        anchor = 'if __name__ == "__main__":\n    main()'
        if "main" not in functions or source.count(anchor) != 1:
            raise ValueError("MAIN_ANCHOR_MISMATCH")
        result = source.replace(anchor, STRANICA_BLOCK + "\n" + anchor, 1)
    elif name == "publish_transaction_guard.py":
        if "_exclusive_lock" not in functions:
            raise ValueError("PUBLICATION_LOCK_BOUNDARY_MISSING")
        result = source + GUARD_BLOCK
    else:
        raise ValueError("OUT_OF_SCOPE:" + name)
    compile(result, name, "exec")
    return result


def build(source_dir: Path, helper: Path, output_dir: Path) -> dict:
    # Validate all sources before creating any candidate output.
    originals = {}
    for name, expected in SOURCE_SHA256.items():
        data = (source_dir / name).read_bytes()
        if sha(data) != expected:
            raise ValueError("SOURCE_SHA256_MISMATCH:" + name)
        originals[name] = data.decode("utf-8")
    helper_bytes = helper.read_bytes()
    if sha(helper_bytes) != HELPER_SHA256:
        raise ValueError("HELPER_SHA256_MISMATCH")
    modified = {name: transform(name, source) for name, source in originals.items()
                if name != "publikaciya.py"}
    output_dir.mkdir(parents=True, exist_ok=False)
    os.chmod(output_dir, 0o700)
    private = output_dir / "private_runtime"
    private.mkdir(mode=0o700)
    records = {}
    patch = []
    for name, after in modified.items():
        path = private / name
        path.write_text(after, encoding="utf-8")
        path.chmod(0o600)
        records[name] = {"before_sha256": SOURCE_SHA256[name], "after_sha256": sha(path.read_bytes())}
        patch.extend(difflib.unified_diff(originals[name].splitlines(keepends=True),
                                         after.splitlines(keepends=True),
                                         fromfile="a/" + name, tofile="b/" + name, n=1))
    helper_path = private / "publication_fence.py"
    helper_path.write_bytes(helper_bytes)
    helper_path.chmod(0o600)
    records["publication_fence.py"] = {"before_sha256": None, "after_sha256": HELPER_SHA256}
    patch_path = output_dir / "narrow_runtime_changes.diff"
    patch_path.write_text("".join(patch), encoding="utf-8")
    manifest = {
        "contract": CONTRACT,
        "status": "ISOLATED_CANDIDATE_NOT_INSTALLED",
        "source_sha256": SOURCE_SHA256,
        "changes": records,
        "additive_patch_sha256": sha(patch_path.read_bytes()),
        "unchanged_foreign_guard": "publikaciya.py",
        "effect_scope": ["serialize legacy main with normal publication", "serialize reload with legacy main"],
        "limitations": [
            "No production installation or publication is performed by this builder.",
            "Other independent writers, including spec-only refresh, require separate source verification.",
            "Media deletion and DB callbacks outside legacy main are outside this narrow change.",
            "Existing processes must load the bound candidate before runtime behavior changes.",
            "The original legacy rebuild behavior, validator and rollback semantics remain unchanged.",
            "Production lock root is the verified /home/Carix; isolated tests inject a temporary fence.",
        ],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source_dir, args.helper, args.output_dir), indent=2))
