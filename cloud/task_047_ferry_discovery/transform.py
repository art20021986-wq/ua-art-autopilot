"""
transform.py -- TASK 052 baseline-restored structural transform for ferry
status text.

This restores the TASK 047 tokenizer discipline (script/style/comment
protected, no global find/replace over arbitrary HTML) and adds the TASK 050
real UI contexts precisely, correcting every false-green regression listed in
the TASK 052 audit:

  1. Ordinary prose containing the target words as a *substring* is never
     touched (only whole, trimmed text nodes / attribute values are matched).
  2. <script>/<style> contents are copied verbatim, never scanned.
  3. data-ru and data-uk are corrected independently, in the same pass.
  4. The exact four-sibling-span pattern (Korea / More / Georgia / Kiev) is
     recognised structurally and resolved, instead of being left ambiguous.
  5. The Ukrainian mapping uses the real "\u0423 \u043c\u043e\u0440\u0456" source phrase, never a fabricated
     "\u0412 \u043c\u043e\u0440\u0456".

No global regex/`str.find` sweep over the whole document is ever used.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Optional

RAW_TEXT_TAGS = {"script", "style"}
VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}

_COMPLEX = object()  # sentinel: element does not have a single simple text leaf


def _map_ru_text(value: str) -> Optional[str]:
    """Full-value RU mapping. Only used against an entire trimmed string
    (attribute value or leaf text node) -- never a substring search."""
    if value == "\u0412 \u043c\u043e\u0440\u0435":
        return "\u041d\u0430 \u043f\u0430\u0440\u043e\u043c\u0435"
    if value.startswith("\u0412 \u043c\u043e\u0440\u0435 \u00b7 "):
        return "\u041d\u0430 \u043f\u0430\u0440\u043e\u043c\u0435" + value[len("\u0412 \u043c\u043e\u0440\u0435"):]
    if value.startswith("\u0412 \u043c\u043e\u0440\u0435:"):
        return "\u041d\u0430 \u043f\u0430\u0440\u043e\u043c\u0435:" + value[len("\u0412 \u043c\u043e\u0440\u0435:"):]
    if value.startswith("\u041c\u043e\u0440\u0435:") and "\u2192" in value:
        return "\u041f\u0430\u0440\u043e\u043c:" + value[len("\u041c\u043e\u0440\u0435:"):]
    if value.startswith("\u041c\u043e\u0440\u0435 ") and "\u2192" in value and "\u0434\u043d\u0435\u0439" in value:
        return "\u041f\u0430\u0440\u043e\u043c " + value[len("\u041c\u043e\u0440\u0435 "):]
    if value == "\u041c\u043e\u0440\u0435":
        return "\u041f\u0430\u0440\u043e\u043c"
    return None


def _map_uk_text(value: str) -> Optional[str]:
    if value == "\u0423 \u043c\u043e\u0440\u0456":
        return "\u041d\u0430 \u043f\u043e\u0440\u043e\u043c\u0456"
    if value == "\u041c\u043e\u0440\u0435":
        return "\u041f\u043e\u0440\u043e\u043c"
    return None


def _map_generic_text(value: str) -> Optional[str]:
    """Arrow/colon anchored exact-phrase patterns that apply regardless of
    surrounding class context, matched only against the *entire* trimmed
    text node -- never a substring of longer prose."""
    if value.startswith("\u0412 \u043c\u043e\u0440\u0435 \u00b7 ") and "\u2192" in value:
        return "\u041d\u0430 \u043f\u0430\u0440\u043e\u043c\u0435" + value[len("\u0412 \u043c\u043e\u0440\u0435"):]
    if value.startswith("\u0412 \u043c\u043e\u0440\u0435:"):
        return "\u041d\u0430 \u043f\u0430\u0440\u043e\u043c\u0435:" + value[len("\u0412 \u043c\u043e\u0440\u0435:"):]
    if value.startswith("\u041c\u043e\u0440\u0435:") and "\u2192" in value:
        return "\u041f\u0430\u0440\u043e\u043c:" + value[len("\u041c\u043e\u0440\u0435:"):]
    if value.startswith("\u041c\u043e\u0440\u0435 ") and "\u2192" in value and "\u0434\u043d\u0435\u0439" in value:
        return "\u041f\u0430\u0440\u043e\u043c " + value[len("\u041c\u043e\u0440\u0435 "):]
    return None


_ATTR_PATTERN_CACHE = {}


def _rewrite_attr(raw_tag: str, name: str, new_value: str) -> str:
    pattern = _ATTR_PATTERN_CACHE.get(name)
    if pattern is None:
        pattern = re.compile(r'(' + re.escape(name) + r'\s*=\s*)(["\'])(.*?)\2', re.IGNORECASE)
        _ATTR_PATTERN_CACHE[name] = pattern

    def _sub(m):
        return m.group(1) + m.group(2) + new_value + m.group(2)

    return pattern.sub(_sub, raw_tag, count=1)


def _set_leaf_text(frame, value):
    if frame.own_text is None:
        frame.own_text = value
    else:
        frame.own_text = _COMPLEX


class _Frame:
    __slots__ = (
        "tag", "chip", "pill", "etaptut", "krug", "has_data_attr",
        "own_text", "children_seq", "holder",
    )

    def __init__(self, tag, chip, pill, etaptut, krug, has_data_attr):
        self.tag = tag
        self.chip = chip
        self.pill = pill
        self.etaptut = etaptut
        self.krug = krug
        self.has_data_attr = has_data_attr
        self.own_text = None
        self.children_seq = []
        self.holder = None

    @property
    def allowed_short(self):
        return self.chip or self.pill or (self.etaptut and self.krug) or self.has_data_attr


class _FerryTransformer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.out = []
        self.stack = []
        self.changes = []
        self.ambiguous = []

    def _current_frame(self):
        return self.stack[-1] if self.stack else None

    def _record_child(self, tag, text_value, holder):
        parent = self._current_frame()
        if parent is not None:
            parent.children_seq.append((tag, text_value, holder))
            parent.own_text = _COMPLEX

    def _process_starttag_common(self, tag, attrs, raw):
        attrs_dict = {k: (v if v is not None else "") for k, v in attrs}
        classes = set(attrs_dict.get("class", "").split())
        is_chip = "chip" in classes
        is_pill = "status-pill" in classes
        is_etaptut = {"etap", "tut"} <= classes
        is_krug = "krug" in classes
        has_data_attr = "data-ru" in attrs_dict or "data-uk" in attrs_dict

        parent = self._current_frame()
        inherited_chip = parent.chip if parent else False
        inherited_pill = parent.pill if parent else False
        inherited_etaptut = parent.etaptut if parent else False

        chip = inherited_chip or is_chip
        pill = inherited_pill or is_pill
        etaptut = inherited_etaptut or is_etaptut
        krug = is_krug

        new_raw = raw
        if "data-ru" in attrs_dict:
            new_val = _map_ru_text(attrs_dict["data-ru"])
            if new_val is not None:
                new_raw = _rewrite_attr(new_raw, "data-ru", new_val)
                self.changes.append({"kind": "attr", "attr": "data-ru"})
        if "data-uk" in attrs_dict:
            new_val = _map_uk_text(attrs_dict["data-uk"])
            if new_val is not None:
                new_raw = _rewrite_attr(new_raw, "data-uk", new_val)
                self.changes.append({"kind": "attr", "attr": "data-uk"})

        self.out.append(new_raw)
        return chip, pill, etaptut, krug, has_data_attr

    def handle_starttag(self, tag, attrs):
        raw = self.get_starttag_text() or ""
        if tag in VOID_ELEMENTS:
            self._process_starttag_common(tag, attrs, raw)
            self._record_child(tag, None, None)
            return
        chip, pill, etaptut, krug, has_data_attr = self._process_starttag_common(tag, attrs, raw)
        frame = _Frame(tag, chip, pill, etaptut, krug, has_data_attr)
        self.stack.append(frame)

    def handle_startendtag(self, tag, attrs):
        raw = self.get_starttag_text() or ""
        self._process_starttag_common(tag, attrs, raw)
        self._record_child(tag, None, None)

    def handle_endtag(self, tag):
        if not self.stack:
            return
        frame = self.stack.pop()
        self.out.append(f"</{tag}>")

        seq = frame.children_seq
        if len(seq) == 4 and all(t == "span" for t, _, _ in seq):
            texts = [tx for _, tx, _ in seq]
            if texts == ["\u041a\u043e\u0440\u0435\u044f", "\u041c\u043e\u0440\u0435", "\u0413\u0440\u0443\u0437\u0438\u044f", "\u041a\u0438\u0435\u0432"]:
                for t, tx, holder in seq:
                    if tx == "\u041c\u043e\u0440\u0435" and holder is not None:
                        holder[0] = holder[0].replace("\u041c\u043e\u0440\u0435", "\u041f\u0430\u0440\u043e\u043c", 1)
                        self.changes.append({"kind": "text", "pattern": "four_span"})

        text_value = frame.own_text
        if text_value is _COMPLEX:
            text_value = None
        self._record_child(frame.tag, text_value, frame.holder)

    def handle_data(self, data):
        frame = self._current_frame()
        if frame is not None and frame.tag in RAW_TEXT_TAGS:
            self.out.append(data)
            return
        if frame is None:
            self.out.append(data)
            return

        stripped = data.strip()
        if not stripped:
            self.out.append(data)
            return

        lead = data[: len(data) - len(data.lstrip())]
        trail = data[len(data.rstrip()):]

        generic = _map_generic_text(stripped)
        if generic is not None:
            self.out.append(lead + generic + trail)
            self.changes.append({"kind": "text", "pattern": "generic"})
            _set_leaf_text(frame, stripped)
            return

        if stripped in ("\u0412 \u043c\u043e\u0440\u0435", "\u0423 \u043c\u043e\u0440\u0456") and frame.allowed_short:
            mapped = _map_ru_text(stripped) if stripped == "\u0412 \u043c\u043e\u0440\u0435" else _map_uk_text(stripped)
            self.out.append(lead + mapped + trail)
            self.changes.append({"kind": "text", "pattern": "short_status"})
            _set_leaf_text(frame, stripped)
            return

        if stripped == "\u041c\u043e\u0440\u0435":
            if frame.allowed_short:
                mapped = _map_ru_text(stripped)
                self.out.append(lead + mapped + trail)
                self.changes.append({"kind": "text", "pattern": "short_word"})
                _set_leaf_text(frame, stripped)
                return
            holder = [lead + stripped + trail]
            self.out.append(holder)
            _set_leaf_text(frame, stripped)
            frame.holder = holder
            self.ambiguous.append({"holder": holder, "text": stripped})
            return

        self.out.append(data)
        _set_leaf_text(frame, stripped)

    def handle_comment(self, data):
        self.out.append(f"<!--{data}-->")

    def handle_decl(self, decl):
        self.out.append(f"<!{decl}>")

    def handle_pi(self, data):
        self.out.append(f"<?{data}>")

    def handle_entityref(self, name):
        self.out.append(f"&{name};")

    def handle_charref(self, name):
        self.out.append(f"&#{name};")

    def get_report(self):
        unresolved = [a for a in self.ambiguous if a["holder"][0].strip() == a["text"]]
        return {"changes": self.changes, "ambiguous": unresolved}

    def finalize(self):
        pieces = []
        for p in self.out:
            if isinstance(p, list):
                pieces.append(p[0])
            else:
                pieces.append(p)
        return "".join(pieces)


def transform_html(html_text: str):
    """Structural, non-global transform. Returns (new_html, report).

    report = {"changes": [...], "ambiguous": [...]}
    """
    parser = _FerryTransformer()
    parser.feed(html_text)
    parser.close()
    new_html = parser.finalize()
    report = parser.get_report()
    return new_html, report
