#!/usr/bin/env python3
"""Deterministic AST/SHA-anchored patcher for TASK 081.

This patcher NEVER modifies a file unless the exact source of the target
function hashes to a supplied anchor SHA256. This guarantees fail-closed
behavior: if the live code has drifted from what was audited, the patcher
refuses to touch it and reports the exact mismatch instead of guessing.

Usage (sandbox only in this task round):
    python patcher.py --root <sandbox_dir> --anchors anchors.json --apply

anchors.json maps "relative/file.py::function_name" -> expected sha256 of the
exact function source (as produced by live_probe.py's AST extraction).
"""
import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def find_function(source: str, name: str):
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            seg = ast.get_source_segment(source, node)
            return node, seg
    return None, None


NEW_TOGGLE_PUBLISH = '''def toggle_publish(auto_number, target_published):
    """Patched by TASK 081: capture exact preimage, only allow one final
    message, compensating rollback on any FAIL."""
    preimage = db_get_publish_state(auto_number)
    try:
        if target_published:
            db_set_published(auto_number, 1)
        ok, reason = publikaciya.opublikovat(auto_number)
        if not ok:
            db_restore_publish_state(auto_number, preimage)
            readback = db_get_publish_state(auto_number)
            assert readback == preimage, "rollback verification failed"
            return {"ok": False, "message": reason or "Публикация отменена: сборка не удалась. Старая страница цела."}
        primary_ok = check_page_reachable(auto_number, diag=False)
        diag_ok = check_page_reachable(auto_number, diag=True)
        both_catalogs_ok = catalog_occurrences_exactly_one(auto_number)
        if ok is True and primary_ok and diag_ok and both_catalogs_ok:
            return {"ok": True, "message": "Машина видна клиентам в каталоге."}
        db_restore_publish_state(auto_number, preimage)
        readback = db_get_publish_state(auto_number)
        assert readback == preimage, "rollback verification failed"
        return {"ok": False, "message": "Публикация отменена: проверка после сборки не прошла. Старая страница цела."}
    except Exception as exc:  # noqa: BLE001
        db_restore_publish_state(auto_number, preimage)
        readback = db_get_publish_state(auto_number)
        assert readback == preimage, "rollback verification failed"
        return {"ok": False, "message": f"Публикация отменена: сборщик не смог собрать {auto_number} ({exc}). Старая страница цела."}
'''

NEW_SEO068_NORMALIZE = '''def _ua_seo068_normalize(staging_bundle, auto_number):
    """Patched by TASK 081: ensure diagnostic placeholder exists inside the
    STAGING bundle before any validation runs, so a missing live diag page
    never blocks a brand-new card."""
    diag_path = staging_bundle.diag_path(auto_number)
    if not diag_path.exists():
        staging_bundle.write_diag_placeholder(auto_number, text="Материалы диагностики ожидаются")
    primary_path = staging_bundle.primary_path(auto_number)
    href = staging_bundle.extract_diag_href(primary_path)
    expected_href = staging_bundle.expected_diag_href(auto_number)
    if href != expected_href:
        raise ValueError(
            f"SEO068_WRONG_DIAG_LINK: primary for {auto_number} links to {href}, expected {expected_href}"
        )
    return True
'''

PATCH_TARGETS = {
    "cars_ui.py::toggle_publish": NEW_TOGGLE_PUBLISH,
    "stranica.py::_ua_seo068_normalize": NEW_SEO068_NORMALIZE,
}


def apply_patch(root: Path, target_key: str, anchors: dict, apply: bool):
    rel_file, func_name = target_key.split("::")
    path = root / rel_file
    if not path.exists():
        return False, f"FILE_NOT_FOUND:{rel_file}"
    source = path.read_text(encoding="utf-8")
    node, seg = find_function(source, func_name)
    if node is None:
        return False, f"FUNCTION_NOT_FOUND:{target_key}"
    actual_sha = sha256_text(seg)
    expected_sha = anchors.get(target_key)
    if expected_sha is None:
        return False, f"NO_ANCHOR_SUPPLIED:{target_key} actual_sha={actual_sha}"
    if actual_sha != expected_sha:
        return False, (
            f"ANCHOR_MISMATCH:{target_key} expected={expected_sha} actual={actual_sha} "
            "-- refusing to patch (fail closed)"
        )
    if not apply:
        return True, f"DRY_RUN_ANCHOR_MATCH:{target_key}"
    new_body = PATCH_TARGETS[target_key]
    start = source[: source.index(seg)]
    end = source[source.index(seg) + len(seg):]
    new_source = start + new_body + end
    try:
        ast.parse(new_source)
    except SyntaxError as exc:
        return False, f"PATCH_PRODUCED_INVALID_SYNTAX:{target_key}:{exc}"
    path.write_text(new_source, encoding="utf-8")
    return True, f"PATCHED:{target_key}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--anchors", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    root = Path(args.root)
    anchors = json.loads(Path(args.anchors).read_text(encoding="utf-8"))

    results = []
    all_ok = True
    for key in PATCH_TARGETS:
        ok, msg = apply_patch(root, key, anchors, args.apply)
        results.append({"target": key, "ok": ok, "message": msg})
        if not ok:
            all_ok = False

    print(json.dumps({"all_ok": all_ok, "results": results}, indent=2))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
