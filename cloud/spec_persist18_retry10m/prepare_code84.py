#!/usr/bin/env python3
"""Prepare pinned legacy integration candidates; never import or write live code.

Existing source bytes are preserved except one insertion before the unique
top-level __main__ guard, or at EOF for modules without one. Runtime wrappers
capture the final effective definitions, including conditional legacy wrappers.
"""
from __future__ import annotations
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

PINS = {
    "master_card.py": "f64e0b82b11bfd6089509510e5b131a91b03d40bed97b16075ab2ec60da380ce",
    "stranica.py": "42aa5fc9db162e59fcf36b7ee9b2002360205827023786a65cf2205ab16066cc",
    "yadro.py": "1e92a22a3fc485ea2cfe3d00a50586e872b3f6e4f628923b2ab9744534406992",
    "publikaciya.py": "fb7fa77277ebc3330c85ab3744c85ac7f084074a314866a5bf388a283f2622c0",
    "vin_spec_service.py": "247943e514f34dc37265791bf56fd36e58bcbaa8b2064285544733b1afc42bae",
}
MARKER = "# >>> UA-ART-ISSUE84-PERMANENT-SPEC-V1"
END_MARKER = "# <<< UA-ART-ISSUE84-PERMANENT-SPEC-V1"

COMMON = r'''
from ua_spec_permanent import ensure_html as _ua84_ensure_html
from ua_spec_permanent import card_uid_from_path as _ua84_uid_from_path
from ua_spec_permanent import write_lock as _ua84_write_lock

def _ua84_require_uid(value):
    candidate = _ua84_uid_from_path(str(value) + ".html")
    if candidate is None:
        raise ValueError("UA84_CARD_UID_REQUIRED")
    return candidate

def _ua84_model_uid(model):
    # Existing generators use nomer(model); its result is validated before use.
    value = None
    if hasattr(model, "get"):
        value = model.get("auto_number")
    if not value:
        value = nomer(model)
    return _ua84_require_uid(value)
'''

PAYLOADS = {
    "master_card.py": COMMON + r'''
_ua84_previous_obrabotat_kartochku = obrabotat_kartochku
def obrabotat_kartochku(html, kod):
    result = _ua84_previous_obrabotat_kartochku(html, kod)
    return _ua84_ensure_html(result, _ua84_require_uid(kod))
''',
    "stranica.py": COMMON + r'''
_ua84_previous_sobrat_kartochku = sobrat_kartochku
def sobrat_kartochku(m, kadry, sredn=None):
    result = _ua84_previous_sobrat_kartochku(m, kadry, sredn)
    return _ua84_ensure_html(result, _ua84_model_uid(m))

_ua84_previous_zapisat = zapisat
def zapisat(put, soderzhimoe, *args, **kwargs):
    uid = _ua84_uid_from_path(put)
    if uid is None:
        # Legacy stranica.zapisat accepts a filename stem and appends .html.
        uid = _ua84_uid_from_path(str(put) + ".html")
    if uid is not None:
        with _ua84_write_lock():
            soderzhimoe = _ua84_ensure_html(soderzhimoe, uid)
            return _ua84_previous_zapisat(put, soderzhimoe, *args, **kwargs)
    return _ua84_previous_zapisat(put, soderzhimoe, *args, **kwargs)
''',
    "yadro.py": COMMON + r'''
_ua84_previous_karta_html = karta_html
def karta_html(m, foto, bron=True):
    result = _ua84_previous_karta_html(m, foto, bron)
    return _ua84_ensure_html(result, _ua84_model_uid(m))

_ua84_previous_zapisat_atomarno = zapisat_atomarno
def zapisat_atomarno(put, soderzhimoe):
    uid = _ua84_uid_from_path(put)
    if uid is not None:
        with _ua84_write_lock():
            soderzhimoe = _ua84_ensure_html(soderzhimoe, uid)
            return _ua84_previous_zapisat_atomarno(put, soderzhimoe)
    return _ua84_previous_zapisat_atomarno(put, soderzhimoe)
''',
    "publikaciya.py": COMMON + r'''
_ua84_previous_zapisat_atomarno = _zapisat_atomarno
def _zapisat_atomarno(put, tekst):
    uid = _ua84_uid_from_path(put)
    if uid is not None:
        with _ua84_write_lock():
            tekst = _ua84_ensure_html(tekst, uid)
            return _ua84_previous_zapisat_atomarno(put, tekst)
    return _ua84_previous_zapisat_atomarno(put, tekst)
''',
    "vin_spec_service.py": r'''
def start_worker() -> bool:
    from ua_spec84_runtime import start_worker as _ua84_start
    return _ua84_start()

def stop_worker(timeout: float = 5.0) -> None:
    from ua_spec84_runtime import stop_worker as _ua84_stop
    return _ua84_stop(timeout=timeout)

def retry_card(value) -> bool:
    from ua_spec84_runtime import retry_card as _ua84_retry
    return _ua84_retry(value)

def card_state(value) -> dict:
    from ua_spec84_runtime import card_state as _ua84_state
    return _ua84_state(value)
''',
}
EXPECTED = {
    "master_card.py": {"obrabotat_kartochku"},
    "stranica.py": {"sobrat_kartochku", "zapisat"},
    "yadro.py": {"karta_html", "zapisat_atomarno"},
    "publikaciya.py": {"_zapisat_atomarno"},
    "vin_spec_service.py": {"start_worker", "stop_worker", "retry_card", "card_state"},
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def is_main_guard(node):
    if not isinstance(node, ast.If):
        return False
    test = node.test
    if not (isinstance(test, ast.Compare) and len(test.ops) == len(test.comparators) == 1
            and isinstance(test.ops[0], ast.Eq)):
        return False
    values = (test.left, test.comparators[0])
    return (any(isinstance(item, ast.Name) and item.id == "__name__" for item in values)
            and any(isinstance(item, ast.Constant) and item.value == "__main__" for item in values))


def module_scope_functions(tree):
    """Include conditional definitions; exclude nested function/class bodies."""
    found = set()
    def walk(nodes):
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found.add(node.name)
            elif not isinstance(node, ast.ClassDef):
                for field in ("body", "orelse", "finalbody"):
                    children = getattr(node, field, None)
                    if isinstance(children, list):
                        walk(children)
                for handler in getattr(node, "handlers", ()):
                    walk(handler.body)
    walk(tree.body)
    return found


def patch_source(name, before):
    require(name in PINS, "UNEXPECTED_MODULE")
    require(digest(before) == PINS[name], "ORIGINAL_PIN_MISMATCH:" + name)
    source = before.decode("utf-8")
    require(MARKER not in source and "_ua84_previous_" not in source, "PATCH_ALREADY_PRESENT:" + name)
    tree = ast.parse(source, filename=name, feature_version=(3, 10))
    require(EXPECTED[name] <= module_scope_functions(tree), "ENTRYPOINTS_MISSING:" + name)
    guards = [node for node in tree.body if is_main_guard(node)]
    require(len(guards) <= 1, "AMBIGUOUS_MAIN_GUARDS:" + name)
    if name == "stranica.py":
        require(len(guards) == 1, "STRANICA_MAIN_GUARD_REQUIRED")
    if guards:
        guard = guards[0]
        require(tree.body[-1] is guard, "CODE_AFTER_MAIN_GUARD:" + name)
        index = sum(len(line) for line in source.splitlines(keepends=True)[:guard.lineno - 1])
    else:
        index = len(source)
    insertion = "\n\n" + MARKER + "\n" + PAYLOADS[name].strip() + "\n" + END_MARKER + "\n\n"
    after = source[:index] + insertion + source[index:]
    candidate_tree = ast.parse(after, filename=name, feature_version=(3, 10))
    require(after[:index] + after[index + len(insertion):] == source, "PROTECTED_SOURCE_CHANGED:" + name)
    require(after.count(MARKER) == after.count(END_MARKER) == 1, "PATCH_MARKER_COUNT:" + name)
    require(EXPECTED[name] <= module_scope_functions(candidate_tree), "CANDIDATE_ENTRYPOINTS_MISSING:" + name)
    return after.encode("utf-8"), {"insertion_line": source[:index].count("\n") + 1,
                                   "insertion_sha256": digest(insertion.encode("utf-8")),
                                   "before_main_guard": bool(guards), "protected_source_byte_changes": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/home/Carix"))
    parser.add_argument("--staging", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.root.resolve(strict=True)
    stage = args.staging.resolve()
    require(stage != root, "STAGING_CANNOT_BE_SOURCE_ROOT")
    require(not stage.exists(), "STAGING_MUST_BE_NEW")
    prepared, manifest = [], []
    for name in PINS:
        path = root / name
        require(path.is_file() and not path.is_symlink(), "REGULAR_ORIGINAL_REQUIRED:" + name)
        before = path.read_bytes()
        after, details = patch_source(name, before)
        relative = "candidate/" + name
        prepared.append((path, before, relative, after))
        manifest.append({"name": name, "input": str(path), "candidate": relative,
                         "before_sha256": digest(before), "after_sha256": digest(after), **details})
    require(all(path.read_bytes() == before for path, before, _, _ in prepared), "SOURCE_CHANGED_DURING_PREPARE")
    stage.mkdir(mode=0o700, parents=True, exist_ok=False)
    for _, _, relative, after in prepared:
        destination = stage / relative
        destination.parent.mkdir(mode=0o700, exist_ok=True)
        destination.write_bytes(after)
        destination.chmod(0o600)
    report = {"mode": "PREPARE_ONLY", "task": "UA-ART-SPEC-PERSIST-18-10M-001",
              "created_at": datetime.now(timezone.utc).isoformat(), "code_files": manifest,
              "production_writes": 0, "database_writes": 0,
              "required_new_modules": ["ua_spec_permanent.py", "ua_spec84_runtime.py", "spec_retry84.py", "spec84_collector.py"]}
    output = stage / "code-manifest.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output.chmod(0o600)
    print(json.dumps({"result": "PREPARED_ONLY", "staging": str(stage), "code_files": len(manifest), "production_writes": 0}))


if __name__ == "__main__":
    main()
