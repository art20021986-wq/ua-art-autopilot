"""Pure, byte-preserving repairs of proven duplicate VIN markup.

No application imports, I/O, network, or HTML reserialization. Unknown VIN
layouts fail closed. ``visible`` means potentially visible HTML text: head,
script, style, template, hidden elements and explicit inline display:none /
visibility:hidden are excluded. Stylesheets are preserved, never interpreted.
"""
from __future__ import annotations

import hashlib
import json
from html import unescape
from html.parser import HTMLParser
import re


VIN = re.compile(r"(?<![A-Z0-9])[A-HJ-NPR-Z0-9]{17}(?![A-Z0-9])")
UID = re.compile(r"UA-[0-9]{4,6}\Z")
VIN_MARKERS = (
    ("<!-- UA-ART-VIN-GUARD-LITE-V1:START -->", "<!-- UA-ART-VIN-GUARD-LITE-V1:END -->"),
    ("<!--UA099_CLEAN_VIN_START-->", "<!--UA099_CLEAN_VIN_END-->"),
)
SPEC_MARKERS = ("<!--UA099_ADD_SPEC_START-->", "<!--UA099_ADD_SPEC_END-->")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
BLOCK = {"html", "body", "div", "p", "section", "article", "table", "tr", "td", "th", "li", "ul", "ol", "br", "h1", "h2", "h3", "summary"}
INVISIBLE = {"head", "script", "style", "template"}


class ShellError(RuntimeError):
    pass


class _Node:
    def __init__(self, tag, attrs, start, end, parent):
        self.tag, self.attrs, self.start, self.end = tag, dict(attrs), start, end
        self.duplicate_attrs = len(self.attrs) != len(attrs)
        self.parent, self.children = parent, []
        self.closed = tag in VOID or tag == "root"


class _Text:
    def __init__(self, text, start, end, parent):
        self.text, self.start, self.end, self.parent = text, start, end, parent


def _hidden(node):
    style = node.attrs.get("style", "") or ""
    return (node.tag in INVISIBLE or "hidden" in node.attrs or
            bool(re.search(r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*(?:hidden|collapse))\s*(?:!important\s*)?(?:;|$)", style, re.I)))


def _text(node, *, visible=False):
    if isinstance(node, _Text):
        return node.text
    if visible and _hidden(node):
        return ""
    result = "".join(_text(child, visible=visible) for child in node.children)
    return " " + result + " " if visible and node.tag in BLOCK else result


def _is_visible(node):
    while node is not None:
        if isinstance(node, _Node) and _hidden(node):
            return False
        node = node.parent
    return True


class _Page(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.lines = [0] + [match.end() for match in re.finditer("\n", source)]
        self.root = _Node("root", [], 0, len(source), None)
        self.stack, self.nodes, self.texts, self.comments = [self.root], [], [], []
        self.feed(source)
        self.close()

    def _offset(self):
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        start = self._offset()
        node = _Node(tag, attrs, start, start + len(self.get_starttag_text()), self.stack[-1])
        self.stack[-1].children.append(node)
        self.nodes.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop().closed = True

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                node = self.stack[index]
                node.end = self.source.find(">", self._offset()) + 1
                node.closed = index == len(self.stack) - 1
                del self.stack[index:]
                return

    def _add_text(self, text, raw):
        start = self._offset()
        node = _Text(text, start, start + len(raw), self.stack[-1])
        self.stack[-1].children.append(node)
        self.texts.append(node)

    def handle_data(self, data):
        self._add_text(data, data)

    def handle_entityref(self, name):
        raw = "&" + name + ";"
        self._add_text(unescape(raw), raw)

    def handle_charref(self, name):
        raw = "&#" + name + ";"
        self._add_text(unescape(raw), raw)

    def handle_comment(self, data):
        start = self._offset()
        end = self.source.find("-->", start)
        if end < 0:
            raise ShellError("SHELL_UNCLOSED_COMMENT")
        self.comments.append((self.source[start:end + 3], start, end + 3))


def _children(node):
    return [child for child in node.children if not isinstance(child, _Text) or child.text.strip()]


def _main_vin(page, card_uid):
    if not isinstance(card_uid, str) or not UID.fullmatch(card_uid):
        raise ShellError("SHELL_INVALID_CARD_UID")
    rows = []
    for row in page.nodes:
        if row.tag != "tr":
            continue
        cells = _children(row)
        if cells and isinstance(cells[0], _Node) and _text(cells[0]).strip().upper() == "VIN":
            if (len(cells) != 2 or any(not isinstance(cell, _Node) or cell.tag != "td" or not cell.closed for cell in cells)
                    or cells[0].attrs != {"class": "k"} or cells[1].attrs
                    or not row.closed or not row.parent or row.parent.tag not in {"table", "tbody"}
                    or any(isinstance(child, _Node) for cell in cells for child in cell.children)
                    or not _is_visible(row) or any(cell.duplicate_attrs for cell in cells)):
                raise ShellError("SHELL_UNKNOWN_MAIN_VIN_MARKUP")
            rows.append((row, _text(cells[1]).strip()))
    if len(rows) != 1 or not VIN.fullmatch(rows[0][1]):
        raise ShellError("SHELL_MAIN_VIN_MISSING_DUPLICATE_OR_INVALID")
    return rows[0]


def _marked_span(page, markers):
    starts = [item for item in page.comments if item[0] == markers[0]]
    ends = [item for item in page.comments if item[0] == markers[1]]
    if not starts and not ends:
        return None
    if len(starts) != 1 or len(ends) != 1 or starts[0][2] > ends[0][1]:
        raise ShellError("SHELL_MALFORMED_MARKERS")
    return starts[0][1], ends[0][2], starts[0][2], ends[0][1]


def _duplicate_range(page, card_uid, vin):
    spans = [span for markers in VIN_MARKERS if (span := _marked_span(page, markers)) is not None]
    if len(spans) > 1:
        raise ShellError("SHELL_MULTIPLE_DUPLICATE_BLOCKS")
    marked_nodes = [node for node in page.nodes if "ua-clean-vin" in (node.attrs.get("class", "") or "").split()
                    or "data-ua-clean-vin" in node.attrs]
    value_nodes = [node for node in page.nodes if "ua-vin-value" in (node.attrs.get("class", "") or "").split()]
    if not spans:
        if marked_nodes or value_nodes:
            raise ShellError("SHELL_UNMARKED_DUPLICATE_VIN")
        return []
    start, end, inner_start, inner_end = spans[0]
    if len(marked_nodes) != 1 or len(value_nodes) != 1:
        raise ShellError("SHELL_UNKNOWN_DUPLICATE_VIN_MARKUP")
    node = marked_nodes[0]
    children = _children(node)
    attrs = node.attrs
    expected = {"class", "data-ua-clean-vin", "data-ua-card", "data-ua-stage", "data-ua-video-count"}
    if (node.tag != "div" or not node.closed or node.duplicate_attrs or set(attrs) != expected
            or attrs["class"] != "blok ua-clean-vin" or attrs["data-ua-clean-vin"] != "1"
            or attrs["data-ua-card"] != card_uid or attrs["data-ua-stage"] not in {"1", "2", "3", "4"}
            or not re.fullmatch(r"0|[1-9][0-9]*", attrs["data-ua-video-count"] or "")
            or node.start < inner_start or node.end > inner_end
            or page.source[inner_start:node.start].strip() or page.source[node.end:inner_end].strip()
            or any(inner_start <= pos < inner_end for _, pos, _ in page.comments)
            or len(children) != 2):
        raise ShellError("SHELL_UNKNOWN_DUPLICATE_VIN_MARKUP")
    for child, cls, value in zip(children, ("zag", "ua-vin-value"), ("VIN", vin)):
        if (not isinstance(child, _Node) or child.tag != "div" or not child.closed or child.duplicate_attrs
                or child.attrs != {"class": cls} or _text(child) != value
                or any(isinstance(item, _Node) for item in child.children)):
            raise ShellError("SHELL_DUPLICATE_VIN_CONTENT_MISMATCH")
    return [(start, end, "marked_duplicate_vin_block")]


def _description_ranges(page, vin):
    """Only the three exact redundant forms proven in the cached primary pages."""
    ranges = []
    for node in page.texts:
        if vin not in node.text or not _is_visible(node):
            continue
        parent = node.parent
        siblings = parent.children
        index = siblings.index(node)
        if (parent.tag == "div" and parent.attrs == {"class": "tehtekst"}
                and not parent.duplicate_attrs and parent.closed
                and node.text == "VIN: " + vin and 0 < index < len(siblings) - 1
                and all(isinstance(item, _Node) and item.tag == "br" and not item.attrs and not item.duplicate_attrs
                        for item in (siblings[index - 1], siblings[index + 1]))):
            ranges.append((node.start, siblings[index + 1].end, "description_vin_br_line"))
            continue
        row = parent.parent
        if (parent.tag != "div" or parent.attrs or parent.duplicate_attrs or not parent.closed
                or len(parent.children) != 1 or row is None or row.duplicate_attrs
                or row.tag != "div" or row.attrs != {"class": "tehstr"} or not row.closed):
            continue
        children = _children(row)
        if (len(children) != 2 or children[1] is not parent or not isinstance(children[0], _Node)
                or children[0].tag != "div" or children[0].attrs != {"class": "m"}
                or children[0].duplicate_attrs or not children[0].closed
                or any(isinstance(item, _Node) for item in children[0].children)
                or _text(children[0]) != "•"
                or any(row.start <= pos < row.end for _, pos, _ in page.comments)):
            continue
        if node.text == "VIN: " + vin:
            ranges.append((row.start, row.end, "description_vin_bullet"))
        else:
            prefix = "Автомобиль уже выкуплен и отправлен паромом. "
            phrase = "VIN проверен: " + vin + ". "
            suffix = "По данным карточки, пробег составляет всего 342 км."
            if node.text == prefix + phrase + suffix and page.source[node.start:node.end] == node.text:
                start = node.start + len(prefix)
                ranges.append((start, start + len(phrase), "description_redundant_vin_clause"))
    return ranges


def _plan(source, card_uid):
    if not isinstance(source, str) or len(source.encode("utf-8")) > 4 * 1024 * 1024:
        raise ShellError("SHELL_INVALID_HTML_INPUT")
    page = _Page(source)
    _, vin = _main_vin(page, card_uid)
    ranges = sorted(_duplicate_range(page, card_uid, vin) + _description_ranges(page, vin))
    if any(left[1] > right[0] for left, right in zip(ranges, ranges[1:])):
        raise ShellError("SHELL_OVERLAPPING_REMOVALS")
    result = source
    for start, end, _ in reversed(ranges):
        result = result[:start] + result[end:]
    validate_one_visible_vin(result, card_uid)
    return result, ranges


def normalize_html(source, card_uid):
    """Remove proven visible duplicates, preserving every other source byte."""
    return _plan(source, card_uid)[0]


def validate_one_visible_vin(source, card_uid):
    """Reject duplicate/foreign VIN text and malformed or leftover VIN panels."""
    page = _Page(source)
    _, vin = _main_vin(page, card_uid)
    if _duplicate_range(page, card_uid, vin):
        raise ShellError("SHELL_DUPLICATE_VIN_REMAINS")
    tokens = VIN.findall(_text(page.root, visible=True))
    if tokens != [vin]:
        raise ShellError("SHELL_VISIBLE_VIN_COUNT_OR_IDENTITY")
    return {"status": "PASS", "visible_vin_count": 1, "main_technical_vin_preserved": True}


def _without_spec(source):
    span = _marked_span(_Page(source), SPEC_MARKERS)
    return source if span is None else source[:span[0]] + source[span[1]:]


def permitted_delta(before, after, card_uid):
    """Assert only canonical spec replacement and proven VIN removal occurred.

    The caller separately validates the canonical specification. This contract
    never authorizes changes to prices, descriptions, main values, stage, CTA,
    photos, scripts, schema, or styles outside that exact specification span.
    """
    original = _without_spec(before)
    expected, ranges = _plan(original, card_uid)
    actual = _without_spec(after)
    validate_one_visible_vin(actual, card_uid)
    if actual != expected:
        raise ShellError("SHELL_UNAUTHORIZED_NON_SPEC_CHANGE")
    return {"status": "PASS", "visible_vin_count": 1,
            "permitted_removals": [{"reason": reason, "characters": end - start,
                                    "utf8_bytes": len(original[start:end].encode("utf-8"))}
                                   for start, end, reason in ranges],
            "remaining_shell_sha256": hashlib.sha256(actual.encode("utf-8")).hexdigest(),
            "outside_permitted_regions_byte_changes": 0}


def _shell_assets(source):
    source = _without_spec(source)
    assets = []
    for node in _Page(source).nodes:
        is_stylesheet = (node.tag == "link" and "stylesheet" in (node.attrs.get("rel", "") or "").lower().split())
        if node.tag == "style" or is_stylesheet or (node.tag == "script" and "src" in node.attrs):
            if not node.closed or node.duplicate_attrs:
                raise ShellError("SHELL_MALFORMED_STATIC_ASSET")
            assets.append((node.tag, source[node.start:node.end]))
    if not any(tag in {"style", "link"} for tag, _ in assets):
        raise ShellError("SHELL_MISSING_ASSET_BASELINE")
    return assets


def validate_shell_assets(before, after):
    """Preserve exact ordered styles, stylesheet links and external scripts.

    The canonical specification's own region is excluded. This permits normal
    vehicle values and gallery data to change during a separately validated
    CRUD rebuild; it does not authorize changes to inline executable scripts,
    header/footer structure, inline style attributes, or other shell content.
    Full specification-only repairs must also pass ``permitted_delta``.
    """
    original, current = _shell_assets(before), _shell_assets(after)
    if current != original:
        raise ShellError("SHELL_STATIC_ASSETS_CHANGED")
    serialized = json.dumps(current, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return {"status": "PASS", "static_asset_count": len(current),
            "style_count": sum(tag == "style" for tag, _ in current),
            "stylesheet_link_count": sum(tag == "link" for tag, _ in current),
            "external_script_count": sum(tag == "script" for tag, _ in current),
            "ordered_static_assets_sha256": hashlib.sha256(serialized).hexdigest()}
