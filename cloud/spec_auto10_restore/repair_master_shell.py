"""Remove one exact obsolete chat-style literal from the captured master.

The active master re-adds a mobile chat override absent from all 32 reviewed
primary pages. This pure patch preserves the approved static template pin and
all other source bytes; it never executes or imports application code.
"""
import ast
import hashlib

SOURCE_SHA256 = "f64e0b82b11bfd6089509510e5b131a91b03d40bed97b16075ab2ec60da380ce"
LEGACY_CHAT_CSS_SHA256 = "f2380e8af1c8e6230cd619ba7472bc60c680760bc6f9b4d6a3bac44e004a0ff8"
MARKER = "# UA_SPEC_AUTO10_MASTER_SHELL_V1: obsolete override removed; reviewed shell pin unchanged."


def patch_master_shell(source: str) -> str:
    digest = lambda data: hashlib.sha256(data).hexdigest()
    if MARKER in source:
        # Idempotency only for our exact candidate; reconstruct and verify the
        # original is deliberately impossible without the removed literal.
        raise ValueError("MASTER_SHELL_ALREADY_PATCHED_REQUIRES_MANIFEST")
    if digest(source.encode("utf-8")) != SOURCE_SHA256:
        raise ValueError("MASTER_SHELL_SOURCE_SHA_MISMATCH")
    tree = ast.parse(source)
    assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                   and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                   and node.targets[0].id == "CHAT_CSS"]
    if len(assignments) != 1:
        raise ValueError("MASTER_CHAT_CSS_ASSIGNMENT_COUNT")
    node = assignments[0]
    value = ast.literal_eval(node.value)
    if not isinstance(value, str) or digest(value.encode()) != LEGACY_CHAT_CSS_SHA256:
        raise ValueError("MASTER_CHAT_CSS_LITERAL_SHA_MISMATCH")
    lines = source.splitlines(keepends=True)
    start = sum(len(line.encode()) for line in lines[:node.value.lineno - 1]) + node.value.col_offset
    end = sum(len(line.encode()) for line in lines[:node.value.end_lineno - 1]) + node.value.end_col_offset
    raw = source.encode()
    changed = (raw[:start] + b'""' + raw[end:]).decode()
    # Audit semantic scope: exactly one literal changes, to the empty string.
    expected = ast.parse(source)
    target = next(item for item in expected.body if isinstance(item, ast.Assign)
                  and len(item.targets) == 1 and isinstance(item.targets[0], ast.Name)
                  and item.targets[0].id == "CHAT_CSS")
    target.value = ast.Constant(value="")
    if ast.dump(expected, include_attributes=False) != ast.dump(ast.parse(changed), include_attributes=False):
        raise ValueError("MASTER_SHELL_AST_SCOPE_MISMATCH")
    compile(changed, "master_card.py", "exec")
    return changed + "\n" + MARKER + "\n"
