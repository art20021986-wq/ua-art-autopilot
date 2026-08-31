#!/usr/bin/env python3
"""TASK 096 final sandbox recovery.

Fixes a false-positive UA0015_PREVIEW_LEAK caused by the word `margin` in
CSS while preserving an explicit semantic guard against internal margin /
markup data in extracted candidate facts.
"""
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


def load_fixed_legacy():
    mod = _original_loader()
    # PRICE_RE is also used against the full HTML preview. CSS legitimately
    # contains `margin`, which must not be treated as commercial data.
    pattern = getattr(getattr(mod, "PRICE_RE", None), "pattern", "")
    flags = getattr(getattr(mod, "PRICE_RE", None), "flags", re.I)
    if pattern:
        cleaned = pattern.replace("|margin|markup", "").replace("margin|markup|", "")
        mod.PRICE_RE = re.compile(cleaned, flags)

    # Preserve the business rule semantically at candidate level.
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
    return mod


# Install the fixed loader both on the schema module and on the recovery module
# that actually executes TASK 096.
schema.load_compatible_legacy = load_fixed_legacy
schema.recovery.load_legacy = load_fixed_legacy

if __name__ == "__main__":
    # Run the schema/safety self-test first, then execute the real recovery entrypoint.
    schema.selftest_actual_schema()
    sys.exit(schema.recovery.main())
