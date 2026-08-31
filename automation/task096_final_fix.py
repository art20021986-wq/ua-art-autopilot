#!/usr/bin/env python3
"""TASK 096 final sandbox recovery with sanitized transport diagnostics."""
import json
import re
import sys
import task096_recovery10_schema as schema

_original_loader = schema.load_compatible_legacy


def _semantic_margin_guard(candidate):
    if not isinstance(candidate, dict):
        return
    facts = candidate.get("facts") or []
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        text = " ".join(str(fact.get(k) or "") for k in ("field_key", "label_ru", "display_value"))
        if re.search(r"(?i)(?:\bmargin\b|\bmarkup\b|марж|наценк)", text):
            raise RuntimeError("TASK096_INTERNAL_MARGIN_FORBIDDEN")


def _transport_error_code(exc):
    # Never log API responses, credentials, source content, or arbitrary text.
    prefix = str(exc).partition(":")[0]
    if re.fullmatch(r"PYTHONANYWHERE_HTTP_[1-5][0-9]{2}", prefix):
        return prefix
    allowed = {
        "PYTHONANYWHERE_NETWORK_ERROR", "PYTHONANYWHERE_RESPONSE_TOO_LARGE",
        "REMOTE_PATH_NOT_ALLOWED", "REMOTE_FILE_MISSING", "UPLOAD_FAILED",
        "UPLOAD_READBACK_MISMATCH",
    }
    return prefix if prefix in allowed else "UNCLASSIFIED_TRANSPORT_ERROR"


def _install_transport_diagnostics(mod):
    original_upload = mod.PythonAnywhereAPI.upload

    def upload(api, path, data):
        try:
            return original_upload(api, path, data)
        except Exception as exc:
            event = {
                "stage": "UPLOAD",
                "target": "remote_applier" if path == mod.REMOTE_APPLIER else "sandbox_file",
                "error_code": _transport_error_code(exc),
                "production_authorized": False,
            }
            print("TASK096_TRANSPORT_DIAGNOSTIC " + json.dumps(event, sort_keys=True), flush=True)
            try:
                mod.atomic_json(schema.recovery.OUT / "transport_diagnostic.json", event)
            except Exception:
                print("TASK096_TRANSPORT_DIAGNOSTIC_SAVE_FAILED", flush=True)
            # Retain the original error and every integrity/scope guard.
            raise

    mod.PythonAnywhereAPI.upload = upload


def load_fixed_legacy():
    mod = _original_loader()
    # PRICE_RE is also used against the full HTML preview. CSS legitimately
    # contains `margin`, which must not be treated as commercial data.
    pattern = getattr(getattr(mod, "PRICE_RE", None), "pattern", "")
    flags = getattr(getattr(mod, "PRICE_RE", None), "flags", re.I)
    if pattern:
        cleaned = pattern.replace("|margin|markup", "").replace("margin|markup|", "")
        mod.PRICE_RE = re.compile(cleaned, flags)

    # Preserve the existing business rule at candidate level.
    for name in ("validate_candidate", "validate_ai_candidate", "validate_facts"):
        fn = getattr(mod, name, None)
        if not callable(fn) or getattr(fn, "_task096_margin_wrapped", False):
            continue
        def wrapped(*args, __fn=fn, **kwargs):
            result = __fn(*args, **kwargs)
            for obj in list(args) + list(kwargs.values()) + [result]:
                if isinstance(obj, dict) and "facts" in obj:
                    _semantic_margin_guard(obj)
            return result
        wrapped._task096_margin_wrapped = True
        setattr(mod, name, wrapped)
    _install_transport_diagnostics(mod)
    return mod


schema.load_compatible_legacy = load_fixed_legacy
schema.recovery.load_legacy = load_fixed_legacy


def main():
    schema.selftest_actual_schema()
    if "--selftest" in sys.argv:
        return 0
    return schema.recovery.main()


if __name__ == "__main__":
    sys.exit(main())
