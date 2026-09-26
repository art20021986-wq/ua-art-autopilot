"""Hash-bound visibility refresh in the existing CRM stage catalog process.

Only already managed price fragments are refreshed from the same committed row
used by the existing stage resolver. Legacy unmarked articles retain their price
bytes. The original publisher lock, stage checks, recovery and writes are kept.
"""

import ast
import hashlib

from patch_yadro import _node_text, _range, _single

EXPECTED_SHA256 = "c349d44821f92950234705d41507587c3ca2780dd750abda0028c060569a5beb"
IMPORT = ("from uaart_market_prices import START as _ua088_price_start, END as _ua088_price_end, "
          "replace_catalog_price_slot as _ua088_refresh_catalog_price\n")


def patch_stage_catalog_sync(source_bytes):
    """Compile an exact source-pinned candidate without importing the live file."""
    if type(source_bytes) is not bytes:
        raise ValueError("SOURCE_BYTES_REQUIRED")
    before = hashlib.sha256(source_bytes).hexdigest()
    if before != EXPECTED_SHA256:
        raise ValueError("STAGE_CATALOG_SOURCE_HASH_MISMATCH")
    source = source_bytes.decode("utf-8")
    tree = ast.parse(source, filename="ua_stage_catalog_sync.py")
    patcher = _single([node for node in tree.body if isinstance(node, ast.FunctionDef)
                       and node.name == "patch_catalog_stages"], "STAGE_PATCHER_ANCHOR_MISMATCH")
    replace = _single([node for node in patcher.body if isinstance(node, ast.FunctionDef)
                       and node.name == "replace"], "STAGE_REPLACE_ANCHOR_MISMATCH")
    assignment = _single([node for node in replace.body if isinstance(node, ast.Assign)
        and _node_text(source, node) == "result = _patch_article(block, stage_of(rows[code]))"],
        "STAGE_PRICE_REFRESH_ANCHOR_MISMATCH")
    base_import = _single([node for node in tree.body if isinstance(node, ast.ImportFrom)
                          and node.module == "pathlib"], "STAGE_IMPORT_ANCHOR_MISMATCH")
    _, statement_end = _range(source, assignment)
    _, import_end = _range(source, base_import)
    insertions = [(statement_end, (
        "        if _ua088_price_start in result or _ua088_price_end in result:\n"
        "            result = _ua088_refresh_catalog_price(result, rows[code])\n")),
        (import_end, IMPORT)]
    candidate = source
    for position, addition in sorted(insertions, reverse=True):
        candidate = candidate[:position] + addition + candidate[position:]
    compile(candidate, "ua_stage_catalog_sync.py", "exec")
    changed_tree = ast.parse(candidate)
    before_functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    after_functions = {node.name: node for node in changed_tree.body if isinstance(node, ast.FunctionDef)}
    if before_functions.keys() != after_functions.keys():
        raise ValueError("STAGE_FUNCTION_SET_CHANGED")
    unchanged = 0
    for name, node in before_functions.items():
        if name == "patch_catalog_stages":
            continue
        if _node_text(source, node) != _node_text(candidate, after_functions[name]):
            raise ValueError("STAGE_UNRELATED_FUNCTION_CHANGED:" + name)
        unchanged += 1
    raw = candidate.encode("utf-8")
    return raw, {"source": "ua_stage_catalog_sync.py", "before_sha256": before,
        "after_sha256": hashlib.sha256(raw).hexdigest(), "imports_added": 1,
        "managed_price_refreshes_added": 1, "other_functions_unchanged": unchanged,
        "legacy_unmarked_prices_unchanged": True, "candidate_compiles": True}
