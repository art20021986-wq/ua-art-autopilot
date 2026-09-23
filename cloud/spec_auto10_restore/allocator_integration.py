"""Hash-pinned pure patches for actual CRM card-creation allocator entrypoints.

No CRM/application imports, database access, deployment, or service changes.
The db.py patch also gives legacy wizard-created cars a canonical identifier.
"""
from __future__ import annotations

import ast
import hashlib

MARKER = "UA_AUTO10_CARD_NUMBER_V1"
EXPECTED = {
    "next_auto_number": "3e655902f98d26bc436623e23e9b137637795121321c533f01eb5810d93a30e7",
    "create_card": "e5a09a2a9ef9f56121910f914640099acbd8f87f6313b82c643b546f67d73ed9",
    "store": "7ddb70281a4edf9e2e082be10a7c66cd66e33b5ee945cf47ec39d2e7e4955d5e",
    "save": "d70a5eb0d08f7f0a95dc80640a6f04bfb3775036cb470a3b49bd39a4f311ac73",
}


class IntegrationError(RuntimeError):
    pass


def _replace(source, name, replacement):
    if MARKER in source:
        raise IntegrationError("CARD_NUMBER_ALREADY_PATCHED")
    nodes = [node for node in ast.parse(source).body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if len(nodes) != 1:
        raise IntegrationError("CARD_NUMBER_FUNCTION_MISSING_OR_DUPLICATED:" + name)
    node = nodes[0]
    old = ast.get_source_segment(source, node)
    if hashlib.sha256(old.encode()).hexdigest() != EXPECTED[name]:
        raise IntegrationError("CARD_NUMBER_UNREVIEWED_FUNCTION:" + name)
    # Byte-column offsets from AST cannot safely slice Unicode text. Replacing
    # the exact source segment avoids that ambiguity while checking uniqueness.
    if source.count(old) != 1:
        raise IntegrationError("CARD_NUMBER_FUNCTION_NOT_UNIQUE:" + name)
    candidate = source.replace(old, replacement, 1)
    compile(candidate, "candidate/" + name + ".py", "exec")
    return candidate


def patch_cars_schema(source):
    return _replace(source, "next_auto_number", '''def next_auto_number(conn, prefix="UA-"):
    # UA_AUTO10_CARD_NUMBER_V1: reservation and card INSERT share one transaction.
    from car_number_allocator import reserve
    return reserve(conn, prefix)
'''.rstrip())


def patch_db(source):
    if MARKER in source:
        raise IntegrationError("CARD_NUMBER_ALREADY_PATCHED")
    node = next((node for node in ast.parse(source).body
                 if isinstance(node, ast.FunctionDef) and node.name == "create_card"), None)
    if node is None:
        raise IntegrationError("CARD_NUMBER_FUNCTION_MISSING_OR_DUPLICATED:create_card")
    body = ast.get_source_segment(source, node)
    anchor = "    with connect() as c:\n        cur = c.execute("
    replacement = '''    with connect() as c:
        # UA_AUTO10_CARD_NUMBER_V1: legacy wizard cars also receive a stable UID.
        if table == "cars":
            from car_number_allocator import reserve
            cols.append("auto_number")
            vals.append(reserve(c))
        cur = c.execute('''
    if body.count(anchor) != 1:
        raise IntegrationError("CARD_NUMBER_CREATE_ANCHOR_MISSING")
    return _replace(source, "create_card", body.replace(anchor, replacement, 1))


def patch_ai_filter(source):
    if MARKER in source:
        raise IntegrationError("CARD_NUMBER_ALREADY_PATCHED")
    for name, count in (("store", 2), ("save", 1)):
        node = next((node for node in ast.parse(source).body
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name), None)
        if node is None:
            raise IntegrationError("CARD_NUMBER_FUNCTION_MISSING_OR_DUPLICATED:" + name)
        body = ast.get_source_segment(source, node)
        replaced = 0
        for indent in (" " * 8, " " * 12):
            old = (indent + "with db.connect() as c:\n" + indent + "    number = S.next_auto_number(c)\n" +
                   indent + 'db.update_card_field("cars", card_id, "auto_number", number, actor)')
            occurrences = body.count(old)
            replaced += occurrences
            body = body.replace(old, indent + "number = _ua_auto10_card_number(card_id, actor)")
        if replaced != count:
            raise IntegrationError("CARD_NUMBER_ASSIGNMENT_SITES_CHANGED:" + name)
        source = _replace(source, name, body)
    source += '''

# UA_AUTO10_CARD_NUMBER_V1: called by both actual recognition save routes.
def _ua_auto10_card_number(card_id, actor):
    from car_number_allocator import ensure_card_number
    with db.connect() as connection:
        number, assigned = ensure_card_number(connection, int(card_id))
    if assigned:
        db.log_action(actor, "card_edit", "cars", card_id, "auto_number", None, number)
    return number
'''
    compile(source, "candidate/ai_filter.py", "exec")
    return source
