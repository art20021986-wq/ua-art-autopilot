"""Canonical ferry/sea stage presentation mapping for UA ART.

This module is the single source of truth for rendering the sea/ferry
delivery stage across RU/UA, for the site, catalog, cards, timelines,
and CRM/bot surfaces. The internal stable key stays ``sea``. Nothing in
this module renames internal identifiers, filters, URLs, or database
enums.
"""

INTERNAL_KEY = "sea"

# Legacy display/input aliases that MUST still be ACCEPTED as input and
# normalized to INTERNAL_KEY, but must NEVER be rendered back to users.
LEGACY_ALIASES = [
    "в море", "в море:", "в море ·", "море", "море:",
    "у морі", "у морі:",
]

RU_LONG = "На пароме · Корея → Грузия"
RU_HEADING = "На пароме: Корея → Грузия"
RU_SHORT = "Паром"

UA_LONG = "На поромі · Корея → Грузія"
UA_HEADING = "На поромі: Корея → Грузія"
UA_SHORT = "Пором"

FORBIDDEN_RU = {"в море", "море"}
FORBIDDEN_UA = {"у морі"}

_ALIAS_NORMALIZED = {a.strip().strip(":· ").lower() for a in LEGACY_ALIASES}
_CANONICAL_NORMALIZED = {"на пароме", "паром", "на поромі", "пором"}


def normalize_alias(raw: str):
    """Normalize an accepted legacy alias (or already-canonical text) to
    the stable internal key when the raw text represents the sea/ferry
    stage. Returns INTERNAL_KEY on match, else returns the raw text
    unchanged (i.e. it is not this stage / not recognized).
    """
    if raw is None:
        return raw
    candidate = raw.strip().strip(":· ").lower()
    if candidate in _ALIAS_NORMALIZED or candidate in _CANONICAL_NORMALIZED:
        return INTERNAL_KEY
    return raw


def render(key: str, lang: str, form: str) -> str:
    """Render display text for a stage key.

    lang: 'ru' | 'ua'
    form: 'long' | 'heading' | 'short'
    """
    if key != INTERNAL_KEY:
        raise ValueError(f"render() called for non-sea key: {key!r}")
    table = {
        ("ru", "long"): RU_LONG,
        ("ru", "heading"): RU_HEADING,
        ("ru", "short"): RU_SHORT,
        ("ua", "long"): UA_LONG,
        ("ua", "heading"): UA_HEADING,
        ("ua", "short"): UA_SHORT,
    }
    try:
        return table[(lang, form)]
    except KeyError as exc:
        raise ValueError(f"Unknown lang/form combination: {lang}/{form}") from exc


def contains_forbidden(text, lang: str) -> bool:
    """Detect forbidden stale current-stage wording in visible output.

    This intentionally only flags the exact stale status/short labels
    ("в море" / "море" for RU, "у морі" for UA) and is not meant to
    censor unrelated legitimate prose containing the noun "море" in a
    different grammatical role; classification of ordinary prose is a
    human/discovery-stage responsibility documented in inventory.json.
    """
    if text is None:
        return False
    low = text.lower()
    forbidden = FORBIDDEN_RU if lang == "ru" else FORBIDDEN_UA
    for word in forbidden:
        if word in low:
            return True
    return False
