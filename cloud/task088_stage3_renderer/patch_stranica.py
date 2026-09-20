"""Strict in-memory price patch for the independently implemented master renderer."""

import ast
import hashlib

from patch_yadro import IMPORT, _node_text, _range, _single

EXPECTED_SHA256 = "2794f01c00a49f1a55c66f3e6af4657808f857e9167f59a5da84c9b8430d724a"
CURRENT_SHA256 = "cdb532f36e6e8fd17c7f933ad347a8bb0bcd8c00644d9c8ea7d9e3ddbb6ae687"


def patch_stranica(source_bytes):
    if type(source_bytes) is not bytes:
        raise ValueError("SOURCE_BYTES_REQUIRED")
    before = hashlib.sha256(source_bytes).hexdigest()
    if before not in (EXPECTED_SHA256, CURRENT_SHA256):
        raise ValueError("STRANICA_SOURCE_HASH_MISMATCH")
    source = source_bytes.decode("utf-8")
    tree = ast.parse(source, filename="stranica.py")
    cards = sorted([node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "sobrat_kartochku"], key=lambda node: node.lineno)
    catalogs = sorted([node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "sobrat_katalog"], key=lambda node: node.lineno)
    if len(cards) != 6 or len(catalogs) != 3:
        raise ValueError("STRANICA_WRAPPER_TOPOLOGY_MISMATCH")
    card, catalog = cards[0], catalogs[0]
    homepage = _single([
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "sobrat_glavnuyu"
    ], "STRANICA_HOME_RENDERER_MISMATCH")
    card_price = _single([
        node for node in card.body if isinstance(node, ast.Expr)
        and '<div class=\'cena\' style=\'margin-top:14px\'>' in (_node_text(source, node) or "")
        and "cena(m)" in (_node_text(source, node) or "")
    ], "STRANICA_CARD_PRICE_ANCHOR_MISMATCH")
    old_caption = _single([
        node for node in card.body if isinstance(node, ast.Expr)
        and "растаможка и сертификат — доплат нет." in (_node_text(source, node) or "")
    ], "STRANICA_CARD_CAPTION_ANCHOR_MISMATCH")
    if card.body.index(old_caption) != card.body.index(card_price) + 1:
        raise ValueError("STRANICA_CARD_CAPTION_NOT_ADJACENT")
    catalog_price = _single([
        node for node in ast.walk(catalog) if isinstance(node, ast.Expr)
        and "<div class='cn'>%s</div></div>" in (_node_text(source, node) or "")
        and "cena(m)" in (_node_text(source, node) or "")
    ], "STRANICA_CATALOG_PRICE_ANCHOR_MISMATCH")
    homepage_price = _single([
        node for node in ast.walk(homepage) if isinstance(node, ast.Expr)
        and "<div class='cn'>%s</div></div>" in (_node_text(source, node) or "")
        and "cena(m)" in (_node_text(source, node) or "")
    ], "STRANICA_HOME_PRICE_ANCHOR_MISMATCH")
    first_import = _single([
        node for node in tree.body if isinstance(node, ast.Import)
        and [alias.name for alias in node.names] == ["os", "io", "re", "json", "glob", "time", "base64", "sqlite3", "traceback"]
    ], "STRANICA_IMPORT_ANCHOR_MISMATCH")
    start, _ = _range(source, card_price)
    _, end = _range(source, old_caption)
    cat_start, cat_end = _range(source, catalog_price)
    home_start, home_end = _range(source, homepage_price)
    _, import_end = _range(source, first_import)
    replacements = [
        (start, end, '    c.append(_ua088_render_market_prices(m, compact=False, require_car_id=True))\n'),
        (cat_start, cat_end, '        c.append(_ua088_render_market_prices(m, compact=True, require_car_id=True) + "</div>")\n'),
        (home_start, home_end, '            c.append(_ua088_render_market_prices(m, compact=True, require_car_id=True) + "</div>")\n'),
        (import_end, import_end, IMPORT),
    ]
    candidate = source
    for start, end, replacement in sorted(replacements, reverse=True):
        candidate = candidate[:start] + replacement + candidate[end:]
    compile(candidate, "stranica.py", "exec")
    after_tree = ast.parse(candidate)
    for name, originals in (("sobrat_kartochku", cards), ("sobrat_katalog", catalogs)):
        afters = sorted([node for node in ast.walk(after_tree) if isinstance(node, ast.FunctionDef) and node.name == name], key=lambda node: node.lineno)
        if len(originals) != len(afters):
            raise ValueError("STRANICA_WRAPPER_COUNT_CHANGED")
        for old, new in zip(originals[1:], afters[1:]):
            if _node_text(source, old) != _node_text(candidate, new):
                raise ValueError("STRANICA_WRAPPER_CHANGED")
    encoded = candidate.encode("utf-8")
    return encoded, {
        "source": "stranica.py", "before_sha256": before,
        "after_sha256": hashlib.sha256(encoded).hexdigest(),
        "price_statements_replaced": 3, "old_caption_removed": 1,
        "catalog_price_copy_replacements": 0,
        "homepage_price_statements_replaced": 1,
        "imports_added": 1, "wrappers_unchanged": len(cards) + len(catalogs) - 2,
        "candidate_compiles": True,
    }
