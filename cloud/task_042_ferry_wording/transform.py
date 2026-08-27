"""Deterministic, idempotent candidate transform for TASK 042.

Applies the canonical ferry-wording replacement to arbitrary source
text while preserving internal identifiers such as ``sea``,
``data-stage="sea"`` and ``?f=sea``.
"""
import re

RU_RULES = [
    (re.compile(r"В\s*море\s*·", re.IGNORECASE), "На пароме ·"),
    (re.compile(r"В\s*море\s*:", re.IGNORECASE), "На пароме:"),
    (re.compile(r"(?<![А-Яа-яЁёІіЇїЄє])В\s*море(?![А-Яа-яЁёІіЇїЄє])", re.IGNORECASE), "На пароме"),
    (re.compile(r"(?<![А-Яа-яЁёІіЇїЄє])Море(?![А-Яа-яЁёІіЇїЄє])"), "Паром"),
]

UA_RULES = [
    (re.compile(r"У\s*морі\s*:", re.IGNORECASE), "На поромі:"),
    (re.compile(r"(?<![А-Яа-яЁёІіЇїЄє])У\s*морі(?![А-Яа-яЁёІіЇїЄє])", re.IGNORECASE), "На поромі"),
]

# Identifiers this transform must never alter (asserted by tests too).
PROTECTED_MARKERS = [
    'data-stage="sea"',
    "?f=sea",
]


def apply_transform(text):
    """Apply the deterministic, idempotent replacement of stale ferry
    wording in visible text while preserving internal identifiers.
    """
    if text is None:
        return text
    result = text
    for pattern, repl in RU_RULES:
        result = pattern.sub(repl, result)
    for pattern, repl in UA_RULES:
        result = pattern.sub(repl, result)
    return result


def is_idempotent(text) -> bool:
    once = apply_transform(text)
    twice = apply_transform(once)
    return once == twice


def protected_markers_preserved(before: str, after: str) -> bool:
    for marker in PROTECTED_MARKERS:
        if marker in before and marker not in after:
            return False
    return True
