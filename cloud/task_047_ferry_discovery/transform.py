"""TASK 047 — Ferry wording contextual transform engine.

Deterministic, structural, target-span text transform for the exact
RU/UA ferry-wording mapping described in TASK 047. No network, no file
I/O, no execution of external code. Pure text-in/text-out.
"""

import re
from typing import Dict, List, Optional, Set, Tuple

VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
RAW_TEXT_ELEMENTS = {"script", "style"}

RU_STATUS_OLD = "В море"
RU_STATUS_NEW = "На пароме"
UK_STATUS_OLD = "У морі"
UK_STATUS_NEW = "На поромі"
SHORT_OLD = "Море"
RU_SHORT_NEW = "Паром"
UK_SHORT_NEW = "Пором"

SEPARATORS = (" ", "\u00b7", ":")  # space, middle dot (·), colon

FORM_CLASSIFICATION = {
    "status": "USER_FACING_STATUS",
    "long": "USER_FACING_LONG",
    "heading": "USER_FACING_HEADING",
    "short": "USER_FACING_SHORT_STAGE",
}

TAG_RE = re.compile(r"<!--.*?-->|<!DOCTYPE[^>]*>|<[^>]+>", re.IGNORECASE | re.DOTALL)
TAGNAME_RE = re.compile(r"^</?\s*([a-zA-Z][a-zA-Z0-9:_-]*)")
CLASS_RE = re.compile(r"\bclass\s*=\s*\"([^\"]*)\"|\bclass\s*=\s*'([^']*)'", re.IGNORECASE)
LANG_RE = re.compile(r"\blang\s*=\s*\"([^\"]*)\"|\blang\s*=\s*'([^']*)'", re.IGNORECASE)
DATALANG_RE = re.compile(r"\bdata-lang\s*=\s*\"([^\"]*)\"|\bdata-lang\s*=\s*'([^']*)'", re.IGNORECASE)
DATA_ATTR_RE = re.compile(r"(?i)(data-(?:ru|uk))\s*=\s*(\"|')(.*?)\2")


def _form_to_classification(form: Optional[str]) -> str:
    if form is None:
        return "AMBIGUOUS"
    return FORM_CLASSIFICATION.get(form, "AMBIGUOUS")


def _prefix_transform(value: str, old: str, new: str) -> Tuple[str, bool]:
    if value == old:
        return new, True
    if value.startswith(old):
        rest = value[len(old):]
        if rest and rest[0] in SEPARATORS:
            return value.replace(old, new, 1), True
    return value, False


def detect_form(value: str) -> Optional[str]:
    """Auto-detect the ferry-wording form from an attribute value's content.

    Used only for data-ru/data-uk attributes, whose language is already
    known from the attribute name itself.
    """
    stripped = value.strip()
    for old in (RU_STATUS_OLD, UK_STATUS_OLD):
        if stripped == old:
            return "status"
        if stripped.startswith(old):
            rest = stripped[len(old):]
            if rest[:1] == ":":
                return "heading"
            if rest[:1] in (" ", "\u00b7"):
                return "long"
    if stripped == SHORT_OLD:
        return "short"
    return None


def transform_value(value: str, context: str, lang: Optional[str]) -> Tuple[str, str, Optional[str]]:
    """Apply the ferry-wording mapping to a single string value.

    Returns (new_value, action, resolved_lang) where action is one of
    'applied', 'unchanged', 'ambiguous'.
    """
    stripped = value.strip()
    if context in ("status", "long", "heading"):
        new_ru, hit_ru = _prefix_transform(stripped, RU_STATUS_OLD, RU_STATUS_NEW)
        if hit_ru:
            return value.replace(stripped, new_ru, 1), "applied", "ru"
        new_uk, hit_uk = _prefix_transform(stripped, UK_STATUS_OLD, UK_STATUS_NEW)
        if hit_uk:
            return value.replace(stripped, new_uk, 1), "applied", "uk"
        return value, "unchanged", lang
    if context == "short":
        if stripped == SHORT_OLD:
            if lang == "ru":
                return value.replace(stripped, RU_SHORT_NEW, 1), "applied", "ru"
            if lang == "uk":
                return value.replace(stripped, UK_SHORT_NEW, 1), "applied", "uk"
            return value, "ambiguous", None
        return value, "unchanged", lang
    return value, "unchanged", lang


def classify_context(classes: Set[str]) -> Optional[str]:
    for c in classes:
        if "status" in c:
            return "status"
    for c in classes:
        if "heading" in c:
            return "heading"
    for c in classes:
        if "long" in c:
            return "long"
    for c in classes:
        if c in ("timeline-legend", "stage-step", "short") or "stage-step" in c or "timeline-legend" in c:
            return "short"
    return None


def parse_attrs_for_tag(tag_text: str) -> Tuple[Set[str], Optional[str]]:
    classes: Set[str] = set()
    m = CLASS_RE.search(tag_text)
    if m:
        val = m.group(1) if m.group(1) is not None else m.group(2)
        classes = set(val.lower().split())
    lang: Optional[str] = None
    m2 = LANG_RE.search(tag_text)
    if m2:
        v = (m2.group(1) or m2.group(2) or "").lower()
        if v in ("ru", "uk"):
            lang = v
    if lang is None:
        m3 = DATALANG_RE.search(tag_text)
        if m3:
            v = (m3.group(1) or m3.group(2) or "").lower()
            if v in ("ru", "uk"):
                lang = v
    if lang is None:
        if "lang-ru" in classes:
            lang = "ru"
        elif "lang-uk" in classes:
            lang = "uk"
    return classes, lang


def transform_document(text: str) -> Tuple[str, List[dict]]:
    """Transform an HTML-like document and return (new_text, occurrences).

    Each occurrence dict: language, form, context, before, after, anchor,
    classification, action.
    """
    occurrences: List[dict] = []
    tokens: List[Tuple[str, str]] = []
    last_end = 0
    for m in TAG_RE.finditer(text):
        if m.start() > last_end:
            tokens.append(("text", text[last_end:m.start()]))
        tokens.append(("tag", m.group(0)))
        last_end = m.end()
    if last_end < len(text):
        tokens.append(("text", text[last_end:]))

    stack: List[Dict[str, Optional[str]]] = []

    def in_raw_text() -> bool:
        return any(f["tag"] in RAW_TEXT_ELEMENTS for f in stack)

    def current_context_lang() -> Tuple[Optional[str], Optional[str]]:
        ctx = None
        lang = None
        for frame in reversed(stack):
            if ctx is None and frame.get("context"):
                ctx = frame["context"]
            if lang is None and frame.get("lang"):
                lang = frame["lang"]
            if ctx and lang:
                break
        return ctx, lang

    out_parts: List[str] = []
    idx = 0
    for kind, chunk in tokens:
        idx += 1
        anchor = "token-%d" % idx
        if kind == "text":
            if in_raw_text() or not chunk.strip():
                out_parts.append(chunk)
                continue
            ctx, lang = current_context_lang()
            if ctx is None:
                out_parts.append(chunk)
                continue
            new_val, action, resolved = transform_value(chunk, ctx, lang)
            if action == "applied":
                occurrences.append({
                    "language": resolved, "form": ctx, "context": "TEXT_NODE",
                    "before": chunk.strip(), "after": new_val.strip(),
                    "anchor": anchor, "classification": _form_to_classification(ctx),
                    "action": "APPLIED",
                })
                out_parts.append(new_val)
            elif action == "ambiguous":
                occurrences.append({
                    "language": None, "form": ctx, "context": "TEXT_NODE",
                    "before": chunk.strip(), "after": chunk.strip(),
                    "anchor": anchor, "classification": "AMBIGUOUS",
                    "action": "AMBIGUOUS",
                })
                out_parts.append(chunk)
            else:
                out_parts.append(chunk)
            continue

        # tag / comment / doctype token
        if chunk.startswith("<!--") or chunk.upper().startswith("<!DOCTYPE"):
            out_parts.append(chunk)
            continue

        is_end = chunk.startswith("</")
        name_m = TAGNAME_RE.match(chunk)
        tag_name = name_m.group(1).lower() if name_m else None
        new_chunk = chunk

        def _attr_repl(am: "re.Match", _anchor: str = anchor) -> str:
            attr_name = am.group(1)
            quote = am.group(2)
            value = am.group(3)
            lang_key = attr_name.lower().split("-")[1]
            form = detect_form(value)
            if form is None:
                return am.group(0)
            new_val, action, resolved = transform_value(value, form, lang_key)
            if action == "applied":
                occurrences.append({
                    "language": lang_key, "form": form,
                    "context": "ATTR_" + attr_name.upper(),
                    "before": value, "after": new_val, "anchor": _anchor,
                    "classification": _form_to_classification(form),
                    "action": "APPLIED",
                })
                return attr_name + "=" + quote + new_val + quote
            return am.group(0)

        if not is_end:
            new_chunk = DATA_ATTR_RE.sub(_attr_repl, chunk)
        out_parts.append(new_chunk)

        if is_end:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i]["tag"] == tag_name:
                    del stack[i:]
                    break
            continue

        self_closing = chunk.rstrip().endswith("/>")
        if tag_name and tag_name not in VOID_ELEMENTS and not self_closing:
            classes, lang = parse_attrs_for_tag(chunk)
            context = classify_context(classes)
            stack.append({"tag": tag_name, "context": context, "lang": lang})

    return "".join(out_parts), occurrences
