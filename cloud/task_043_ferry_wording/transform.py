"""TASK 043 — Contextual ferry-wording transform.

This module replaces the rejected TASK 042 global-regex transform. It only
changes text that exactly matches an approved anchor phrase after
whitespace-stripping (plain text mode), or visible text nodes / approved
presentation attributes inside HTML (structural mode). It never rewrites
script bodies, style bodies, arbitrary embedded substrings inside longer
prose, or legacy input aliases.

No third-party dependency. Standard library only.
"""

from html.parser import HTMLParser

# Exact anchor phrases -> approved replacement. Longer/compound phrases are
# listed alongside the short form; matching is always against the FULL
# stripped text of a node/string, never a substring inside a longer sentence.
ANCHOR_MAP = {
    "ru": {
        "В море · Корея → Грузия": "На пароме · Корея → Грузия",
        "В море: Корея → Грузия": "На пароме: Корея → Грузия",
        "В море": "Паром",
    },
    "uk": {
        "У морі · Корея → Грузія": "На поромі · Корея → Грузія",
        "У морі: Корея → Грузія": "На поромі: Корея → Грузія",
        "У морі": "Пором",
    },
}

# Legacy input aliases that MUST remain accepted/preserved wherever they
# appear as raw script/config/history literals (never rewritten there).
LEGACY_ALIASES = {"ru": "В море", "uk": "У морі"}

SHORT_FORMS = {"Паром", "Пором"}

# Presentation attributes that are allowed to carry translated display text.
APPROVED_ATTRS = {"data-ru", "data-uk"}

# Tags whose contents are never touched by this transform.
SKIP_TAGS = {"script", "style"}


def classify_text(text):
    """Classify a standalone string (line, attribute value, or text node).

    This classification is context-free: callers that need to distinguish
    a *rendered visible label* from a *literal inside a script/JSON table*
    must apply the surrounding-context rule themselves (transform_html does
    this by skipping script/style tags; discover.py records file-section
    context separately).
    """
    stripped = text.strip()
    if not stripped:
        return "ORDINARY_PROSE"
    for mapping in ANCHOR_MAP.values():
        if stripped in mapping:
            return "USER_FACING_SHORT_STAGE" if mapping[stripped] in SHORT_FORMS else "USER_FACING_STATUS"
    for alias in LEGACY_ALIASES.values():
        if stripped == alias:
            return "LEGACY_INPUT_ALIAS_CANDIDATE"
    return "ORDINARY_PROSE"


def apply_transform(text, lang="ru"):
    """Transform a standalone plain-text string.

    Only the *entire stripped string* being an exact registered anchor
    triggers a change. Anchor phrases embedded inside longer ordinary
    prose are left completely untouched, which is what fixes TASK 042
    defects 1 and 2 (grammar corruption / prose corruption).
    """
    mapping = ANCHOR_MAP.get(lang, {})
    stripped = text.strip()
    if stripped not in mapping:
        return text
    lead = len(text) - len(text.lstrip())
    trail = len(text) - len(text.rstrip())
    prefix = text[:lead]
    suffix = text[len(text) - trail:] if trail else ""
    return prefix + mapping[stripped] + suffix


class _ReconstructingParser(HTMLParser):
    """Rebuilds HTML byte-for-byte except for approved, targeted edits.

    Uses convert_charrefs=False and explicit handlers for every event type
    so that untouched regions (including script/style bodies, entities,
    comments, doctypes, and processing instructions) are re-emitted
    verbatim.
    """

    def __init__(self, lang):
        super().__init__(convert_charrefs=False)
        self.lang = lang
        self.out = []
        self.skip_stack = []
        self.occurrences = []

    def handle_starttag(self, tag, attrs):
        raw = self.get_starttag_text() or ""
        new_raw = raw
        mapping = ANCHOR_MAP.get(self.lang, {})
        if tag.lower() not in SKIP_TAGS:
            for name, value in attrs:
                if name in APPROVED_ATTRS and value is not None:
                    stripped = value.strip()
                    if stripped in mapping:
                        replacement = mapping[stripped]
                        old_attr = '%s="%s"' % (name, value)
                        if old_attr in new_raw:
                            new_value = value.replace(stripped, replacement)
                            new_attr = '%s="%s"' % (name, new_value)
                            new_raw = new_raw.replace(old_attr, new_attr)
                            self.occurrences.append({
                                "type": "ATTR", "name": name,
                                "before": stripped, "after": replacement,
                            })
        self.out.append(new_raw)
        self.skip_stack.append(tag.lower() in SKIP_TAGS)

    def handle_startendtag(self, tag, attrs):
        self.out.append(self.get_starttag_text() or "")

    def handle_endtag(self, tag):
        self.out.append("</%s>" % tag)
        if self.skip_stack:
            self.skip_stack.pop()

    def handle_data(self, data):
        skip = self.skip_stack[-1] if self.skip_stack else False
        if skip:
            self.out.append(data)
            return
        mapping = ANCHOR_MAP.get(self.lang, {})
        stripped = data.strip()
        if stripped in mapping:
            replacement = mapping[stripped]
            self.out.append(data.replace(stripped, replacement))
            self.occurrences.append({
                "type": "TEXT", "name": None,
                "before": stripped, "after": replacement,
            })
        else:
            self.out.append(data)

    def handle_comment(self, data):
        self.out.append("<!--%s-->" % data)

    def handle_decl(self, decl):
        self.out.append("<!%s>" % decl)

    def handle_pi(self, data):
        self.out.append("<?%s>" % data)

    def handle_entityref(self, name):
        self.out.append("&%s;" % name)

    def handle_charref(self, name):
        self.out.append("&#%s;" % name)


def transform_html(html_str, lang="ru"):
    """Return (new_html, occurrences) for a candidate HTML source string.

    Only visible text nodes and approved presentation attributes are ever
    changed. Script/style bodies, tag structure, other attributes
    (including data-stage, ids, hrefs, tracking params) and unmatched text
    are reproduced exactly.
    """
    parser = _ReconstructingParser(lang)
    parser.feed(html_str)
    parser.close()
    return "".join(parser.out), parser.occurrences
