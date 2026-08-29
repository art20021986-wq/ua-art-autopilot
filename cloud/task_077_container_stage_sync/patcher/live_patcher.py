"""
live_patcher.py — Gate A patch-application tool for TASK 077/079.

CRM-CONTAINER-STAGE-SYNC-004 v1.0 — SANDBOX ONLY DELIVERY.

FAIL-CLOSED BY DESIGN:

This tool never modifies any real production file in this delivery, and
nothing in this repository invokes it against a production path. It exists
so that a future, separately-approved Gate A/B operator has a deterministic,
fail-closed pipeline instead of a generic search-and-replace:

  1. Requires an explicit mapping of {filename: local_copy_path} supplied by
     the caller. It never discovers or guesses a production path itself.
  2. Verifies each local copy's full-file SHA-256 against the proven live
     anchors captured in TASK 076/077 evidence
     (eta_release_candidate.ANCHOR_SHA256). Any missing file or hash mismatch
     raises AnchorMismatchError immediately.
  3. For files that contain the entry points named in the contract
     (konteyner.prinyat, konteyner.sprosit_dni, konteyner._peresobrat,
     cars_ui.apply_value, cars_ui.toggle_publish), extracts the exact active
     function source via AST and refuses on duplicate or missing
     definitions (extract_function_sources()).
  4. Compares each extracted function source against GOLDEN_FUNCTION_SOURCE.
     That table is intentionally left as None for every entry in this
     delivery, because no real production byte content has been supplied to
     Claude/Cloud in TASK 079 — only SHA-256 anchors and a textual
     description of the call path. Therefore apply() ALWAYS raises
     FailClosedError at this step in this delivery. This is the deliberate,
     honest fail-closed behavior required by the contract.
  5. Only once a real Gate-A operator supplies (a) verified real file bytes
     matching the anchors above and (b) a captured golden function source
     recorded through the same evidence process as TASK 076/077, would this
     tool proceed to build a minimal, targeted patch (import of
     eta_release_candidate and delegation to run_eta_sync_release) and write
     it to a *candidate output path* — never overwriting the input file in
     place, and never touching any production path directly.

Running this file directly does nothing except print a warning; there is no
CLI entry point that touches production.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eta_release_candidate as rc  # noqa: E402


class FailClosedError(rc.ETASyncError):
    pass


# Target entry points per file, exactly as named in the proven live call path
# (TASK 077 evidence / task contract section "Proven call path").
TARGET_FUNCTIONS = {
    "konteyner.py": ("prinyat", "sprosit_dni", "_peresobrat"),
    "cars_ui.py": ("apply_value", "toggle_publish"),
}

# Golden function source table. Intentionally empty/None for every function
# in this delivery — see module docstring. Populating this table with real
# captured source is a separate, evidence-backed Gate A step outside the
# scope of what Claude/Cloud can safely perform without real file bytes.
GOLDEN_FUNCTION_SOURCE = {
    "konteyner.py": {"prinyat": None, "sprosit_dni": None, "_peresobrat": None},
    "cars_ui.py": {"apply_value": None, "toggle_publish": None},
}


def verify_and_extract(local_copy_paths):
    """
    local_copy_paths: dict[filename] -> path to a LOCAL, non-production copy
    supplied by the caller for inspection only.

    Returns dict[filename] -> {function_name: source_text} for files that
    have target functions. Raises AnchorMismatchError / FailClosedError /
    ETASyncError on any verification problem.
    """
    results = {}
    for filename, path in local_copy_paths.items():
        if filename not in rc.ANCHOR_SHA256:
            raise FailClosedError("no anchor configured for %s" % filename)
        if not os.path.exists(path):
            raise FailClosedError("local copy for %s was not supplied" % filename)
        with open(path, "rb") as f:
            data = f.read()
        rc.verify_anchor(filename, data)  # raises AnchorMismatchError on mismatch
        if filename in TARGET_FUNCTIONS:
            text = data.decode("utf-8")
            funcs = rc.extract_function_sources(text, TARGET_FUNCTIONS[filename])
            results[filename] = funcs
    return results


def apply(local_copy_paths, output_dir):
    """
    Full fail-closed patch pipeline. In this delivery this ALWAYS raises
    FailClosedError, either because the supplied local copies do not match
    the proven anchors (expected, since no real production bytes are
    available to Claude/Cloud), or — in the unreachable case that they did —
    because GOLDEN_FUNCTION_SOURCE has no captured real values yet.

    This function never writes to `output_dir` unless every check above has
    passed, and even then it would only ever write a candidate file, never
    overwrite `local_copy_paths` or any production path.
    """
    extracted = verify_and_extract(local_copy_paths)
    for filename, funcs in extracted.items():
        golden = GOLDEN_FUNCTION_SOURCE.get(filename, {})
        for func_name, source in funcs.items():
            expected = golden.get(func_name)
            if expected is None:
                raise FailClosedError(
                    "FAIL_CLOSED: no golden function source captured for %s:%s; "
                    "refusing to patch." % (filename, func_name)
                )
            if source != expected:
                raise FailClosedError(
                    "FAIL_CLOSED: %s:%s source does not match captured golden "
                    "source; refusing to patch." % (filename, func_name)
                )
    # Unreachable in this delivery: GOLDEN_FUNCTION_SOURCE is empty, so the
    # loop above always raises before reaching here. Kept as an explicit
    # guard for any future accidental table population without approval.
    raise FailClosedError(
        "FAIL_CLOSED: apply() reached its unreachable guard branch; refusing "
        "to write any candidate output without a separate owner-approved "
        "Gate A/B step."
    )


if __name__ == "__main__":
    print(
        "live_patcher.py is a library-only, fail-closed Gate A tool for "
        "CRM-CONTAINER-STAGE-SYNC-004 v1.0. It must not be invoked directly "
        "against production paths, and this delivery contains no CLI entry "
        "point that does so."
    )
