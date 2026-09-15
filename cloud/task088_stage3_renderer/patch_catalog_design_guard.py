"""Hash-bound patch of the final golden-template catalog price renderer."""

import ast
import hashlib

from patch_yadro import _node_text, _range, _single

EXPECTED_SHA256 = "51127bbc2be949e1d37f7b6995c0e5a7a32a497c8436139322ce5b0fea308d60"
IMPORT = "from uaart_market_prices import replace_catalog_price_slot as _ua088_replace_catalog_price_slot\n"


def patch_catalog_design_guard(source_bytes):
    if type(source_bytes) is not bytes:
        raise ValueError("SOURCE_BYTES_REQUIRED")
    before = hashlib.sha256(source_bytes).hexdigest()
    if before != EXPECTED_SHA256:
        raise ValueError("CATALOG_GUARD_SOURCE_HASH_MISMATCH")
    source = source_bytes.decode("utf-8")
    tree = ast.parse(source, filename="catalog_design_guard.py")
    renderer = _single([node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "render_card"], "CATALOG_RENDERER_MISMATCH")
    first = _single([
        node for node in renderer.body if isinstance(node, ast.Assign)
        and _node_text(source, node) == "price = _money(row)"
    ], "CATALOG_PRICE_START_MISMATCH")
    last = _single([
        node for node in renderer.body if isinstance(node, ast.Assign)
        and "block[:price_match.start()]" in (_node_text(source, node) or "")
        and "block[price_match.end():]" in (_node_text(source, node) or "")
    ], "CATALOG_PRICE_END_MISMATCH")
    sequence = renderer.body[renderer.body.index(first):renderer.body.index(last) + 1]
    if len(sequence) != 8 or not any(isinstance(node, ast.If) for node in sequence):
        raise ValueError("CATALOG_PRICE_SEQUENCE_MISMATCH")
    import_node = _single([node for node in tree.body if isinstance(node, ast.ImportFrom) and node.module == "typing"], "CATALOG_IMPORT_ANCHOR_MISMATCH")
    start, _ = _range(source, first)
    _, end = _range(source, last)
    _, import_end = _range(source, import_node)
    replacements = [
        (start, end, "    block = _ua088_replace_catalog_price_slot(block, row)\n"),
        (import_end, import_end, IMPORT),
    ]
    candidate = source
    for start, end, replacement in sorted(replacements, reverse=True):
        candidate = candidate[:start] + replacement + candidate[end:]
    compile(candidate, "catalog_design_guard.py", "exec")
    patched_tree = ast.parse(candidate)
    unchanged = 0
    before_functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    after_functions = {node.name: node for node in patched_tree.body if isinstance(node, ast.FunctionDef)}
    if before_functions.keys() != after_functions.keys():
        raise ValueError("CATALOG_FUNCTION_SET_CHANGED")
    for name, node in before_functions.items():
        if name == "render_card":
            continue
        if _node_text(source, node) != _node_text(candidate, after_functions[name]):
            raise ValueError("CATALOG_UNRELATED_FUNCTION_CHANGED:" + name)
        unchanged += 1
    encoded = candidate.encode("utf-8")
    return encoded, {
        "source": "catalog_design_guard.py", "before_sha256": before,
        "after_sha256": hashlib.sha256(encoded).hexdigest(),
        "price_sections_replaced": 1, "imports_added": 1,
        "other_functions_unchanged": unchanged, "candidate_compiles": True,
        "golden_path": "/home/Carix/catalog_design_golden.html",
    }
