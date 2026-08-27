"""FERRY-PHASE1 — Ferry wording contextual transform engine.

Deterministic, structural, target-span text transform for the exact
RU/UK ferry-wording mapping based on the accepted TASK 047 tokenizer.
Adds the verified UA ART chip, stage, four-span and bilingual attributes.
No network, no file
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

FORM_CLASSIFICATION = {
    "status": "USER_FACING_STATUS",
    "long": "USER_FACING_LONG",
    "heading": "USER_FACING_HEADING",
    "short": "USER_FACING_SHORT_STAGE",
    "route_stage": "USER_FACING_ROUTE_STAGE",
    "route_heading": "USER_FACING_ROUTE_HEADING",
    "info": "USER_FACING_INFO",
}

TAG_RE = re.compile(r"<!--.*?-->|<!DOCTYPE[^>]*>|<[^>]+>", re.IGNORECASE | re.DOTALL)
TAGNAME_RE = re.compile(r"^</?\s*([a-zA-Z][a-zA-Z0-9:_-]*)")
CLASS_RE = re.compile(r"\bclass\s*=\s*\"([^\"]*)\"|\bclass\s*=\s*'([^']*)'", re.IGNORECASE)
LANG_RE = re.compile(r"\blang\s*=\s*\"([^\"]*)\"|\blang\s*=\s*'([^']*)'", re.IGNORECASE)
DATALANG_RE = re.compile(r"\bdata-lang\s*=\s*\"([^\"]*)\"|\bdata-lang\s*=\s*'([^']*)'", re.IGNORECASE)
DATA_ATTR_RE = re.compile(r"(?i)(data-(?:ru|uk))\s*=\s*(\"|')(.*?)\2")
EXACT_TEXT_MAP = {
    "В море · Корея → Грузия": ("На пароме · Корея → Грузия", "ru", "long"),
    "У морі · Корея → Грузія": ("На поромі · Корея → Грузія", "uk", "long"),
    "Море: Корея → Грузия": ("Паром: Корея → Грузия", "ru", "route_heading"),
    "Море: Корея → Грузія": ("Пором: Корея → Грузія", "uk", "route_heading"),
    "Море Корея → Грузия — около 60 дней": (
        "Паром Корея → Грузия — около 60 дней", "ru", "info",
    ),
    "Море Корея → Грузія — близько 60 днів": (
        "Пором Корея → Грузія — близько 60 днів", "uk", "info",
    ),
}


def _form_to_classification(form: Optional[str]) -> str:
    if form is None:
        return "AMBIGUOUS"
    return FORM_CLASSIFICATION.get(form, "AMBIGUOUS")


def _prefix_transform(value: str, old: str, new: str) -> Tuple[str, bool]:
    if value == old:
        return new, True
    if value.startswith(old):
        rest = value[len(old):]
        if rest.startswith(":") or rest.startswith(" ·"):
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
            if rest.startswith(" ·"):
                return "long"
    if stripped == SHORT_OLD:
        return "short"
    if stripped.startswith(SHORT_OLD + ":"):
        return "route_heading"
    if stripped in EXACT_TEXT_MAP and EXACT_TEXT_MAP[stripped][2] == "info":
        return "info"
    return None


def transform_value(value: str, context: str, lang: Optional[str]) -> Tuple[str, str, Optional[str]]:
    """Apply the ferry-wording mapping to a single string value.

    Returns (new_value, action, resolved_lang) where action is one of
    'applied', 'unchanged', 'ambiguous'.
    """
    stripped = value.strip()
    if stripped in EXACT_TEXT_MAP:
        mapped, mapped_lang, _form = EXACT_TEXT_MAP[stripped]
        if lang is None or lang == mapped_lang:
            return value.replace(stripped, mapped, 1), "applied", mapped_lang
    if context in ("status", "long", "heading", "route_stage"):
        new_ru, hit_ru = _prefix_transform(stripped, RU_STATUS_OLD, RU_STATUS_NEW)
        if hit_ru:
            return value.replace(stripped, new_ru, 1), "applied", "ru"
        new_uk, hit_uk = _prefix_transform(stripped, UK_STATUS_OLD, UK_STATUS_NEW)
        if hit_uk:
            return value.replace(stripped, new_uk, 1), "applied", "uk"
        if context in ("status", "route_stage") and stripped == SHORT_OLD:
            replacement = UK_SHORT_NEW if lang == "uk" else RU_SHORT_NEW
            resolved = "uk" if lang == "uk" else "ru"
            return value.replace(stripped, replacement, 1), "applied", resolved
        return value, "unchanged", lang
    if context == "route_heading" and stripped.startswith(SHORT_OLD + ":"):
        replacement = UK_SHORT_NEW if lang == "uk" else RU_SHORT_NEW
        resolved = "uk" if lang == "uk" else "ru"
        return value.replace(SHORT_OLD, replacement, 1), "applied", resolved
    if context == "info" and stripped in EXACT_TEXT_MAP:
        mapped, mapped_lang, _form = EXACT_TEXT_MAP[stripped]
        return value.replace(stripped, mapped, 1), "applied", mapped_lang
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
    if "chip" in classes:
        return "status"
    for c in classes:
        if "status" in c:
            return "status"
    if "etap" in classes:
        return "route_stage"
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


def _transform_four_span_sequences(text: str) -> Tuple[str, List[dict]]:
    """Replace the exact four direct sibling spans via a token stack.

    The second span is edited only after its parent closes and proves the
    exact Korea / Sea / Georgia / Kyiv child sequence. Raw script/style text,
    comments, attributes and unrelated text nodes are never searched.
    """
    tokens: List[Tuple[str, str]] = []
    last_end = 0
    for match in TAG_RE.finditer(text):
        if match.start() > last_end:
            tokens.append(("text", text[last_end:match.start()]))
        tokens.append(("tag", match.group(0)))
        last_end = match.end()
    if last_end < len(text):
        tokens.append(("text", text[last_end:]))

    out_parts: List[str] = []
    stack: List[dict] = []
    occurrences: List[dict] = []

    def close_top_frame() -> None:
        frame = stack.pop()
        children = frame["children"]
        if not frame["direct_text"] and len(children) == 4:
            names = [child["tag"] for child in children]
            values = [child["text"] for child in children]
            if names == ["span", "span", "span", "span"] and values == [
                "Корея", SHORT_OLD, "Грузия", "Киев",
            ]:
                target = children[1]
                text_index = target["text_index"]
                out_parts[text_index] = out_parts[text_index].replace(
                    SHORT_OLD, RU_SHORT_NEW, 1,
                )
                target["text"] = RU_SHORT_NEW
                occurrences.append({
                    "language": "ru", "form": "short",
                    "context": "FOUR_SPAN_SEQUENCE",
                    "before": SHORT_OLD, "after": RU_SHORT_NEW,
                    "anchor": "four-span-%d" % (len(occurrences) + 1),
                    "classification": FORM_CLASSIFICATION["short"],
                    "action": "APPLIED",
                })

        simple_text = None
        simple_index = None
        if not children and len(frame["direct_text"]) == 1:
            simple_text, simple_index = frame["direct_text"][0]
        if stack:
            stack[-1]["children"].append({
                "tag": frame["tag"], "text": simple_text,
                "text_index": simple_index,
            })

    for kind, chunk in tokens:
        if kind == "text":
            text_index = len(out_parts)
            out_parts.append(chunk)
            if stack and stack[-1]["tag"] not in RAW_TEXT_ELEMENTS and chunk.strip():
                stack[-1]["direct_text"].append((chunk.strip(), text_index))
            continue

        if stack and stack[-1]["tag"] in RAW_TEXT_ELEMENTS:
            close_match = re.match(r"^</\s*([a-zA-Z][a-zA-Z0-9:_-]*)", chunk)
            out_parts.append(chunk)
            if close_match and close_match.group(1).lower() == stack[-1]["tag"]:
                close_top_frame()
            continue

        out_parts.append(chunk)
        if chunk.startswith("<!--") or chunk.upper().startswith("<!DOCTYPE"):
            continue
        name_match = TAGNAME_RE.match(chunk)
        if not name_match:
            continue
        tag_name = name_match.group(1).lower()
        if chunk.startswith("</"):
            if stack and stack[-1]["tag"] == tag_name:
                close_top_frame()
            continue
        self_closing = chunk.rstrip().endswith("/>") or tag_name in VOID_ELEMENTS
        if self_closing:
            if stack:
                stack[-1]["children"].append({
                    "tag": tag_name, "text": None, "text_index": None,
                })
            continue
        stack.append({"tag": tag_name, "children": [], "direct_text": []})

    return "".join(out_parts), occurrences


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
    text, occurrences = _transform_four_span_sequences(text)
    pending_ambiguous: List[dict] = []
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
            stripped = chunk.strip()
            if stripped in EXACT_TEXT_MAP:
                mapped, mapped_lang, form = EXACT_TEXT_MAP[stripped]
                new_val = chunk.replace(stripped, mapped, 1)
                occurrences.append({
                    "language": mapped_lang, "form": form, "context": "TEXT_NODE",
                    "before": stripped, "after": mapped, "anchor": anchor,
                    "classification": _form_to_classification(form), "action": "APPLIED",
                })
                out_parts.append(new_val)
                continue
            if ctx is None:
                if stripped in (RU_STATUS_OLD, UK_STATUS_OLD, SHORT_OLD):
                    pending_ambiguous.append({
                        "language": None, "form": None, "context": "TEXT_NODE",
                        "before": stripped, "after": stripped, "anchor": anchor,
                        "classification": "AMBIGUOUS", "action": "AMBIGUOUS",
                    })
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

        # tag / comment / doctype token. Inside raw text, only the matching
        # script/style close tag is structural; tag-looking JS/CSS is opaque.
        if in_raw_text():
            raw_tag = stack[-1]["tag"] if stack else None
            raw_close = re.match(r"^</\s*([a-zA-Z][a-zA-Z0-9:_-]*)", chunk)
            if not raw_close or raw_close.group(1).lower() != raw_tag:
                out_parts.append(chunk)
                continue
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

    occurrences.extend(pending_ambiguous)
    return "".join(out_parts), occurrences
