"""Pure exact-source patch for native publisher visibility authority boundaries.

The final atomic forward switch rechecks active visibility authority. Legacy
compensation enters the explicitly owned recovery scope before its existing
per-file exception handling. Outside visibility context both hooks preserve
the canonical publisher behavior. This does not authorize uncooperative HTML
writers: exclusive cooperative writer coverage remains a separate live gate.
No private module is imported or private source read by this patcher.
"""
import ast
import hashlib
import textwrap


SOURCE_SHA256 = "296c389b477472032bad714e41f12bfa4b7e47ad784ac6900ba55f136d939c72"
FORWARD_ANCHOR = "    os.replace(vrem, put)\n"
FORWARD_INSERT = (
    "    from visibility_lifecycle import require_active_authority as _task088_require_active_authority\n"
    "    _task088_require_active_authority()\n"
)
RECOVERY_IMPORT = "    from visibility_lifecycle import recovery_scope as _task088_visibility_recovery_scope\n"
RECOVERY_WITH = "    with _task088_visibility_recovery_scope():\n"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _restore_boundary(source):
    candidates = [node for node in ast.parse(source).body
                  if isinstance(node, ast.FunctionDef) and node.name == "_otkat"]
    if len(candidates) != 1:
        raise ValueError("EXACT_PUBLISHER_RESTORE_FUNCTION_REQUIRED")
    node = candidates[0]
    if node.decorator_list or node.args.args[0].arg != "papka_rez":
        raise ValueError("EXACT_PUBLISHER_RESTORE_SIGNATURE_REQUIRED")
    lines = source.splitlines(keepends=True)
    start = node.body[0].lineno - 1
    original_body = "".join(lines[start:node.end_lineno])
    return ("".join(lines[:start]) + RECOVERY_IMPORT + RECOVERY_WITH
            + textwrap.indent(original_body, "    ")
            + "".join(lines[node.end_lineno:]))


def patch_publikaciya(source):
    """Return (candidate_bytes, digest-only report); refuse drift/reapplication."""
    if type(source) is not bytes or _sha(source) != SOURCE_SHA256:
        raise ValueError("CURRENT_PUBLIKACIYA_SOURCE_SHA256_MISMATCH")
    text = source.decode("utf-8")
    tree = ast.parse(text)
    actual_switches = [node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name) and node.func.value.id == "os"
        and node.func.attr == "replace"]
    if len(actual_switches) != 1 or text.count(FORWARD_ANCHOR) != 1:
        raise ValueError("EXACT_PUBLISHER_FORWARD_SWITCH_REQUIRED")
    result = text.replace(FORWARD_ANCHOR, FORWARD_INSERT + FORWARD_ANCHOR, 1)
    result = _restore_boundary(result)
    candidate = result.encode("utf-8")
    compile(candidate, "<pinned-publisher-authority-candidate>", "exec")
    return candidate, {"before_sha256": SOURCE_SHA256,
        "after_sha256": _sha(candidate), "bytes": len(candidate),
        "forward_atomic_switches": 1, "explicit_legacy_recovery_boundaries": 1,
        "private_source_imported": False,
        "scope": "Visibility authority hook only; legacy behavior retained outside context",
        "recovery_limit": "Requires active operation/journal ownership and cooperative publication fence; does not prove arbitrary external HTML conflict exclusion"}


def patch_source(source):
    if type(source) is not str:
        raise ValueError("PUBLISHER_SOURCE_TEXT_REQUIRED")
    return patch_publikaciya(source.encode("utf-8"))[0].decode("utf-8")
