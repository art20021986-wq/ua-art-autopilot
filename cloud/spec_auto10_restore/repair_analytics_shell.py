"""Pure narrow follow-up to the pinned, coordinated analytics writer.

Canonical card and catalog HTML belongs to the publisher. Optional analytics
maintenance may not append scripts to that protected shell. This leaves all
existing tags and both WSGI analytics endpoints untouched.
"""
import ast
import hashlib

INPUT_SHA256 = "cb6fc54ae832eb768eb70f2815e010db46e15614ef1864acc3dd0d843386fc23"
MARKER = "UAART-ANALYTICS-CANONICAL-SHELL-OWNERSHIP-002"


def patch_analytics_shell(source: bytes) -> bytes:
    if hashlib.sha256(source).hexdigest() != INPUT_SHA256:
        raise ValueError("ANALYTICS_SHELL_SOURCE_SHA_MISMATCH")
    original = source.decode("utf-8")
    old = ('                if not imya.lower().endswith(".html"):\n'
           '                    continue\n'
           '                put = os.path.join(papka, imya)\n')
    new = ('                if not imya.lower().endswith(".html"):\n'
           '                    continue\n'
           '                # ' + MARKER + '\n'
           '                # Publisher owns these complete static shells.\n'
           '                import re as _ua_shell_re\n'
           '                if (imya.casefold() == "katalog.html" or _ua_shell_re.fullmatch(\n'
           '                        r"UA-[0-9]{4,}(?:-diag)\\.html", imya, _ua_shell_re.I)\n'
           '                        or _ua_shell_re.fullmatch(r"UA-[0-9]{4,}\\.html", imya, _ua_shell_re.I)):\n'
           '                    continue\n'
           '                put = os.path.join(papka, imya)\n')
    if original.count(old) != 1:
        raise ValueError("ANALYTICS_SHELL_PATCH_POINT_MISMATCH")
    changed = original.replace(old, new, 1)
    compile(changed, "analitika_wsgi.py", "exec")
    before_tree, after_tree = ast.parse(original), ast.parse(changed)
    before_response = next(node for node in before_tree.body if isinstance(node, ast.FunctionDef) and node.name == "obolochka")
    after_response = next(node for node in after_tree.body if isinstance(node, ast.FunctionDef) and node.name == "obolochka")
    if ast.dump(before_response, include_attributes=False) != ast.dump(after_response, include_attributes=False):
        raise ValueError("ANALYTICS_WSGI_RESPONSE_CHANGED")
    if changed.count(MARKER) != 1:
        raise ValueError("ANALYTICS_SHELL_MARKER_MISMATCH")
    return changed.encode("utf-8")
