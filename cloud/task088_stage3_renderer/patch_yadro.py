"""Hash-bound in-memory patch for the inspected live yadro.py base renderers.

The caller owns backup, guarded installation, rollback and real publication.
This module never reads/writes production and never imports the target source.
"""

import ast
import hashlib

EXPECTED_SHA256 = "1c6bddccec30198179f9a179aa67ac8f2e40da1a794c87f2342150eb5d2ec793"
IMPORT = "from uaart_market_prices import render_market_prices as _ua088_render_market_prices\n"


def _node_text(source, node):
    return ast.get_source_segment(source, node)


def _range(source, node):
    lines = source.splitlines(keepends=True)
    # AST columns are UTF-8 byte offsets. Replace complete, standalone statements
    # rather than converting Unicode columns or reserializing unrelated source.
    return sum(map(len, lines[:node.lineno - 1])), sum(map(len, lines[:node.end_lineno]))


def _single(nodes, reason):
    if len(nodes) != 1:
        raise ValueError(reason)
    return nodes[0]


def patch_yadro(source_bytes):
    """Return candidate bytes and provenance, or fail closed on any source drift."""
    if type(source_bytes) is not bytes:
        raise ValueError("SOURCE_BYTES_REQUIRED")
    before = hashlib.sha256(source_bytes).hexdigest()
    if before != EXPECTED_SHA256:
        raise ValueError("YADRO_SOURCE_HASH_MISMATCH")
    source = source_bytes.decode("utf-8")
    tree = ast.parse(source, filename="yadro.py")
    cards = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "karta_html"]
    catalogs = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "katalog_html"]
    if len(cards) != 4 or len(catalogs) != 3:
        raise ValueError("YADRO_WRAPPER_TOPOLOGY_MISMATCH")
    card = cards[0]
    catalog = catalogs[0]
    card_price = _single([
        node for node in card.body if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name) and node.test.id == "cena"
        and 'class=\\"cn_b\\"' in (_node_text(source, node) or "")
    ], "YADRO_CARD_PRICE_ANCHOR_MISMATCH")
    catalog_price = _single([
        node for node in ast.walk(catalog) if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and 'class=\\"cn\\"' in (_node_text(source, node) or "")
        and 'm.get("price_uah")' in (_node_text(source, node) or "")
    ], "YADRO_CATALOG_PRICE_ANCHOR_MISMATCH")
    if card_price.orelse or len(card_price.body) != 1:
        raise ValueError("YADRO_CARD_PRICE_STRUCTURE_MISMATCH")
    base_import = _single([
        node for node in tree.body if isinstance(node, ast.Import)
        and len(node.names) == 1 and node.names[0].name == "html"
        and node.names[0].asname == "_html"
    ], "YADRO_IMPORT_ANCHOR_MISMATCH")
    replacements = []
    for node, replacement in (
        (card_price, '    c.append(_ua088_render_market_prices(m, compact=False, require_car_id=True))\n'),
        (catalog_price, '        c.append(_ua088_render_market_prices(m, compact=True, require_car_id=True))\n'),
    ):
        start, end = _range(source, node)
        replacements.append((start, end, replacement))
    _, import_end = _range(source, base_import)
    replacements.append((import_end, import_end, IMPORT))
    candidate = source
    for start, end, replacement in sorted(replacements, reverse=True):
        candidate = candidate[:start] + replacement + candidate[end:]
    compile(candidate, "yadro.py", "exec")
    changed_tree = ast.parse(candidate)
    changed_cards = [node for node in changed_tree.body if isinstance(node, ast.FunctionDef) and node.name == "karta_html"]
    changed_catalogs = [node for node in changed_tree.body if isinstance(node, ast.FunctionDef) and node.name == "katalog_html"]
    # Every wrapper is byte-identical; only the two base price statements change.
    for old, new in zip(cards[1:] + catalogs[1:], changed_cards[1:] + changed_catalogs[1:]):
        if _node_text(source, old) != _node_text(candidate, new):
            raise ValueError("YADRO_WRAPPER_CHANGED")
    encoded = candidate.encode("utf-8")
    return encoded, {
        "source": "yadro.py", "before_sha256": before,
        "after_sha256": hashlib.sha256(encoded).hexdigest(),
        "price_statements_replaced": 2, "imports_added": 1,
        "catalog_price_copy_replacements": 0,
        "wrappers_unchanged": 5, "candidate_compiles": True,
    }
