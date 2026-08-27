"""
TASK 050 transform module.

Implements ONLY proven, exact mappings for real UA ART snippets:
  - status chip: "В море" -> "На пароме"
  - etap/tut route heading: "Море: X -> Y" -> "Паром: X -> Y" (nested krug preserved)
  - four-stage progress sequence: Корея / Море / Грузия / Киев -> .../ Паром / ...
  - exact route phrases observed in real cards (RU/UK)

Anything else containing the word "Море" outside these proven contexts is
NEVER rewritten. It is preserved byte-for-byte and reported as AMBIGUOUS so a
human/owner can review it explicitly. This module never performs a blanket
"Море" -> "Паром" replacement.

Also provides secret scanning/redaction used before any report/receipt is
returned or serialized, covering both plain (key=value) and JSON
("key": "value") forms.

KNOWN LIMITATION: HTML matching here is regex-based against the exact proven
snippet shapes supplied by the owner/audit, not a full DOM parser. This is
intentional for TASK 050 scope (correction of TASK 047), not a general HTML
rewriter.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

# ---------------------------------------------------------------------------
# Secret scanning / redaction
# ---------------------------------------------------------------------------

_SECRET_KEY_RE = r'(?:token|api[-_]?key|password|secret)'
_SECRET_PATTERN = re.compile(
    r'(?i)"?\b(' + _SECRET_KEY_RE + r')\b"?\s*[:=]\s*"?([A-Za-z0-9_\-\./]{3,})"?'
)

_SAFE_KEYWORDS = {"status", "sha256", "sha", "container", "tracking", "id"}


def scan_for_secrets(text: str) -> bool:
    """Return True if text contains a plausible secret assignment, plain or
    JSON form (token=..., "token": "...", api-key : ..., password ...).
    Ordinary safe keys (status, sha256, container, tracking) never match."""
    for m in _SECRET_PATTERN.finditer(text):
        key = m.group(1).lower().replace("-", "").replace("_", "")
        if key in {"token", "apikey", "password", "secret"}:
            return True
    return False


def redact_secrets(text: str) -> str:
    """Redact detected secret values in text, preserving key names."""

    def _sub(m: "re.Match[str]") -> str:
        full = m.group(0)
        value = m.group(2)
        key = m.group(1).lower().replace("-", "").replace("_", "")
        if key not in {"token", "apikey", "password", "secret"}:
            return full
        return full.replace(value, "***REDACTED***")

    return _SECRET_PATTERN.sub(_sub, text)


# ---------------------------------------------------------------------------
# Occurrence record
# ---------------------------------------------------------------------------

@dataclass
class Occurrence:
    path: str
    sha256: str
    language: str          # "ru" | "uk" | "unknown" | "n/a"
    form: str              # chip | etap_tut | four_stage | route_phrase | plain_v_more | standalone | python_literal
    classification: str    # TARGET | AMBIGUOUS | LEGACY_INPUT_ALIAS | USER_FACING
    before: str
    after: str
    anchor: str
    context: str
    action: str             # REPLACE | PRESERVE


# ---------------------------------------------------------------------------
# Proven exact mappings (TASK 047 baseline + TASK 050 additions)
# ---------------------------------------------------------------------------

EXACT_PHRASE_MAP = {
    "ru": {
        "В море": "На пароме",
        "Море: Корея → Грузия": "Паром: Корея → Грузия",
        "Море Корея → Грузия — около 60 дней": "Паром Корея → Грузия — около 60 дней",
    },
    "uk": {
        "В морі": "На поромі",
        "Море: Корея → Грузія": "Пором: Корея → Грузія",
        "Море Корея → Грузія — близько 60 днів": "Пором Корея → Грузія — близько 60 днів",
    },
}

CHIP_RE = re.compile(r'(<div class="chip">)В море(\s*·[^<]*</div>)')
ETAP_TUT_RE = re.compile(
    r'(<div class="etap tut"><div class="krug">\d+</div>)Море(:[^<]*</div>)'
)
FOUR_STAGE_RE = re.compile(r'(Корея\s*/\s*)Море(\s*/\s*Грузия\s*/\s*Киев)')


def _bounded_context(s: str, start: int, end: int, radius: int = 40) -> str:
    lo = max(0, start - radius)
    hi = min(len(s), end + radius)
    return s[lo:hi]


def transform_html(html: str, path: str, sha256: str) -> Tuple[str, List[Occurrence]]:
    """Apply only proven mappings; anything else stays byte-identical and is
    reported as AMBIGUOUS."""
    occurrences: List[Occurrence] = []
    result = html

    def _chip_sub(m: "re.Match[str]") -> str:
        before = m.group(0)
        after = f'{m.group(1)}На пароме{m.group(2)}'
        occurrences.append(Occurrence(
            path=path, sha256=sha256, language="ru", form="chip",
            classification="TARGET", before=before, after=after,
            anchor="div.chip", context=_bounded_context(html, m.start(), m.end()),
            action="REPLACE",
        ))
        return after

    result = CHIP_RE.sub(_chip_sub, result)

    def _etap_sub(m: "re.Match[str]") -> str:
        before = m.group(0)
        after = f'{m.group(1)}Паром{m.group(2)}'
        occurrences.append(Occurrence(
            path=path, sha256=sha256, language="ru", form="etap_tut",
            classification="TARGET", before=before, after=after,
            anchor="div.etap.tut>div.krug", context=_bounded_context(html, m.start(), m.end()),
            action="REPLACE",
        ))
        return after

    result = ETAP_TUT_RE.sub(_etap_sub, result)

    def _stage_sub(m: "re.Match[str]") -> str:
        before = m.group(0)
        after = f'{m.group(1)}Паром{m.group(2)}'
        occurrences.append(Occurrence(
            path=path, sha256=sha256, language="ru", form="four_stage",
            classification="TARGET", before=before, after=after,
            anchor="progress-sequence", context=_bounded_context(html, m.start(), m.end()),
            action="REPLACE",
        ))
        return after

    result = FOUR_STAGE_RE.sub(_stage_sub, result)

    for lang, mapping in EXACT_PHRASE_MAP.items():
        for src, dst in mapping.items():
            if src in ("В море", "В морі"):
                continue
            idx = 0
            while True:
                pos = result.find(src, idx)
                if pos == -1:
                    break
                occurrences.append(Occurrence(
                    path=path, sha256=sha256, language=lang, form="route_phrase",
                    classification="TARGET", before=src, after=dst,
                    anchor="text-or-attr", context=_bounded_context(result, pos, pos + len(src)),
                    action="REPLACE",
                ))
                result = result[:pos] + dst + result[pos + len(src):]
                idx = pos + len(dst)

    idx = 0
    while True:
        pos = result.find("В море", idx)
        if pos == -1:
            break
        occurrences.append(Occurrence(
            path=path, sha256=sha256, language="ru", form="plain_v_more",
            classification="TARGET", before="В море", after="На пароме",
            anchor="text", context=_bounded_context(result, pos, pos + len("В море")),
            action="REPLACE",
        ))
        result = result[:pos] + "На пароме" + result[pos + len("В море"):]
        idx = pos + len("На пароме")

    idx = 0
    while True:
        pos = result.find("Море", idx)
        if pos == -1:
            break
        occurrences.append(Occurrence(
            path=path, sha256=sha256, language="unknown", form="standalone",
            classification="AMBIGUOUS", before="Море", after="Море",
            anchor="text", context=_bounded_context(result, pos, pos + len("Море")),
            action="PRESERVE",
        ))
        idx = pos + len("Море")

    return result, occurrences
