"""Narrow, idempotent finalizer for every public car-page writer.

ensure_html performs no writes. write_lock coordinates the caller's final HTML
write using one dedicated lock. Only owned spec fragments are changed;
malformed ownership raises SpecMarkupError before publication.
"""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import fcntl
import html
from html.parser import HTMLParser
import logging
import os
from pathlib import Path, PurePath
import re
import stat
import threading
import time
from typing import Callable

START = "<!--UA099_ADD_SPEC_START-->"
END = "<!--UA099_ADD_SPEC_END-->"
STYLE_ID = "ua099-additional-spec-style"
SECTION_ID = "additional-specification"
ANCHOR = "<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:START -->"
EMPTY_TEXT = "Дополнительные характеристики пока не найдены."
_LOG = logging.getLogger(__name__)
_WRITE_LOCK_REGISTRY = {}
_WRITE_LOCK_REGISTRY_GUARD = threading.Lock()
_UNSAFE = re.compile(r"https?\s*:|www\.|javascript\s*:|data\s*:|//[\w.-]+\.[a-z]|carhistory\.kr|carvertical|carfax|doubleclick|googlesyndication", re.I)


class SpecMarkupError(ValueError):
    """An ambiguous or unsafe fragment must not replace a live page."""


def _require(value, reason):
    if not value:
        raise SpecMarkupError(reason)


def _uid(value):
    value = str(value)
    _require(bool(re.fullmatch(r"UA-\d{4,}", value)) and int(value[3:]) > 0,
             "INVALID_CARD_UID")
    return value


def card_uid_from_path(path) -> str | None:
    """Recognize only car HTML basenames, never catalog/diagnostic documents."""
    match = re.fullmatch(r"(UA-\d{4,})\.html", PurePath(str(path)).name)
    if match is None or int(match.group(1)[3:]) <= 0:
        return None
    return match.group(1)


@contextmanager
def write_lock(root="/home/Carix", timeout=30.0):
    """Coordinate final ensure→write with the background spec-only refresher.

    Reentrant in the same thread. Callers that also use existing CRM/publication
    locks acquire those first; this context never acquires any other lock.
    Creating this one task-owned lock file is the only helper filesystem write.
    """
    root = str(Path(root).resolve(strict=True))
    with _WRITE_LOCK_REGISTRY_GUARD:
        state = _WRITE_LOCK_REGISTRY.setdefault(root, {"lock": threading.RLock(), "depth": 0, "fd": None})
    deadline = time.monotonic() + timeout
    if not state["lock"].acquire(timeout=max(0.0, timeout)):
        raise TimeoutError("UA84_THREAD_WRITE_LOCK_BUSY")
    entered = False
    try:
        if state["depth"] == 0:
            flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(str(Path(root) / ".ua_spec84_write.lock"), flags, 0o600)
            try:
                _require(stat.S_ISREG(os.fstat(fd).st_mode), "UA84_WRITE_LOCK_NOT_REGULAR")
                while True:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("UA84_PROCESS_WRITE_LOCK_BUSY")
                        time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
            except BaseException:
                os.close(fd)
                raise
            state["fd"] = fd
        state["depth"] += 1
        entered = True
        yield
    finally:
        if entered:
            state["depth"] -= 1
            if state["depth"] == 0:
                fd, state["fd"] = state["fd"], None
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                finally:
                    os.close(fd)
        state["lock"].release()


class _BlockParser(HTMLParser):
    TAGS = {"details", "summary", "span", "small", "div", "section", "h3", "dl", "dt", "dd", "p"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.cells = [], []
        self.tags = Counter()
        self.current = None

    def handle_starttag(self, tag, attrs):
        _require(tag in self.TAGS, "UNSAFE_SPEC_TAG:" + tag)
        values = dict(attrs)
        _require(len(values) == len(attrs), "DUPLICATE_SPEC_ATTRIBUTE")
        _require(set(values) <= {"class", "data-ua-additional-spec", "id"}, "UNSAFE_SPEC_ATTRIBUTE")
        if "id" in values:
            _require(tag == "details" and values["id"] == SECTION_ID, "FOREIGN_SPEC_ID")
        if tag == "details":
            _require(not self.stack and values.get("data-ua-additional-spec") == "1", "SPEC_DETAILS_ROOT")
            _require("ua-additional-spec" in values.get("class", "").split(), "SPEC_DETAILS_CLASS")
        elif tag == "summary":
            _require(self.stack == ["details"] and self.tags["summary"] == 0, "SPEC_SUMMARY_POSITION")
        self.tags[tag] += 1
        self.stack.append(tag)
        if tag in {"dt", "dd"}:
            _require(self.current is None, "NESTED_SPEC_CELL")
            self.current = [tag, ""]

    def handle_endtag(self, tag):
        _require(bool(self.stack) and self.stack[-1] == tag, "UNBALANCED_SPEC_TAG:" + tag)
        self.stack.pop()
        if tag in {"dt", "dd"}:
            _require(self.current is not None and self.current[0] == tag, "SPEC_CELL_MISMATCH")
            self.cells.append(tuple(self.current))
            self.current = None

    def handle_data(self, data):
        _require(bool(self.stack) or not data.strip(), "TEXT_OUTSIDE_SPEC")
        if self.current is not None:
            self.current[1] += data

    def handle_comment(self, data):
        raise SpecMarkupError("UNEXPECTED_SPEC_COMMENT")

    def handle_startendtag(self, tag, attrs):
        raise SpecMarkupError("UNEXPECTED_SPEC_SELFCLOSING_TAG")


def validate_block(block: str) -> list[tuple[str, str]]:
    _require(isinstance(block, str) and block.startswith(START) and block.endswith(END), "SPEC_MARKERS")
    _require(block.count(START) == block.count(END) == 1, "AMBIGUOUS_SPEC_MARKERS")
    _require(not _UNSAFE.search(html.unescape(block)), "SPEC_AD_OR_EXTERNAL_REFERENCE")
    parser = _BlockParser()
    parser.feed(block[len(START):-len(END)])
    parser.close()
    _require(not parser.stack and parser.current is None, "UNCLOSED_SPEC")
    _require(parser.tags["details"] == parser.tags["summary"] == 1, "SPEC_CONTROL_COUNT")
    _require(parser.tags["dt"] == parser.tags["dd"], "SPEC_ROW_PAIR_COUNT")
    _require(all(tag == ("dt" if i % 2 == 0 else "dd") for i, (tag, _) in enumerate(parser.cells)), "SPEC_ROW_ORDER")
    return [(parser.cells[i][1], parser.cells[i + 1][1]) for i in range(0, len(parser.cells), 2)]


def _identified(block):
    validate_block(block)
    if not re.search(r"\bid\s*=", block, re.I):
        block = block.replace("<details ", "<details id='" + SECTION_ID + "' ", 1)
    block = block.replace("Подтверждённые дополнительные характеристики пока не найдены.", EMPTY_TEXT)
    validate_block(block)
    return block


def empty_block():
    return (START + "<details id='" + SECTION_ID + "' class='blok ua-additional-spec' data-ua-additional-spec='1'>"
            "<summary><span>Дополнительная спецификация</span><small>0 параметров</small></summary>"
            "<div class='ua-addspec-body'><p class='ua-addspec-empty'>" + EMPTY_TEXT + "</p></div></details>" + END)


def owned_spans(source: str):
    """Accept one complete owned block/style; reject ambiguous duplicates."""
    spans = []
    _require(source.count(START) == source.count(END) <= 1, "AMBIGUOUS_LEGACY_SPEC_MARKERS")
    if START in source:
        left, right = source.index(START), source.index(END) + len(END)
        _require(left < right - len(END), "REVERSED_LEGACY_SPEC_MARKERS")
        validate_block(source[left:right])
        spans.append((left, right, "block"))
    for match in re.finditer(r"<style\b[^>]*>", source, re.I):
        if re.search(r"\bid\s*=\s*(['\"])" + STYLE_ID + r"\1", match.group(), re.I):
            close = re.search(r"</style\s*>", source[match.end():], re.I)
            _require(close is not None, "UNCLOSED_SPEC_STYLE")
            spans.append((match.start(), match.end() + close.end(), "style"))
    _require(sum(kind == "style" for _, _, kind in spans) <= 1, "DUPLICATE_SPEC_STYLE")
    ordered = sorted(spans)
    _require(all(ordered[i][1] <= ordered[i + 1][0] for i in range(len(ordered) - 1)), "OVERLAPPING_SPEC_OWNERSHIP")
    protected = source
    for left, right, _ in sorted(spans, reverse=True):
        protected = protected[:left] + protected[right:]
    _require(not re.search(r"UA099_ADD_SPEC|ua-additional-spec|ua-addspec-|ua099-additional-spec-style|data-ua-additional-spec|\bid=['\"]additional-specification['\"]", protected, re.I), "UNOWNED_SPEC_REMNANT")
    return spans, protected


def _safe_css(css, *, preserve_vin=False):
    _require(isinstance(css, str), "SPEC_STYLE_REQUIRED")
    css = css.strip()
    _require(bool(re.fullmatch(r"<style\s+id=['\"]" + STYLE_ID + r"['\"]\s*>[\s\S]*</style>", css)), "SPEC_STYLE_WRAPPER")
    # The legacy CSS helper also includes two VIN rules. They are unrelated to
    # this component and are deliberately not installed by this narrow module.
    if not preserve_vin:
        css = re.sub(r"\.ua-clean-vin\s+\.ua-vin-(?:value|note)\{[^{}]*\}", "", css)
    _require(not re.search(r"url\s*\(|@import|https?\s*:|expression\s*\(|javascript|</style>[\s\S]+", css, re.I), "SPEC_STYLE_EXTERNAL_OR_EXECUTABLE")
    _require(css.count("<style") == css.count("</style>") == 1, "SPEC_STYLE_COUNT")
    body = css[css.index(">") + 1:css.rindex("</style>")]
    for selector in re.findall(r"([^{}]+)\{", body):
        selector = selector.strip()
        _require(selector.startswith((".ua-additional-spec", ".ua-addspec-", "@media("))
                 or (preserve_vin and selector.startswith((".ua-clean-vin .ua-vin-value", ".ua-clean-vin .ua-vin-note"))),
                 "UNRELATED_STYLE_SELECTOR")
    return css


def _renderer_functions():
    import ua_additional_spec as legacy
    def render(uid):
        # A retained old block is safe only after current vehicle identity was
        # positively checked. Unknown identity is an empty view, never old facts.
        try:
            from ua_spec84_runtime import fact_binding_matches
            identity_matches = fact_binding_matches(uid)
        except Exception as exc:
            _LOG.warning("spec identity unavailable for %s (%s)", uid, type(exc).__name__)
            return empty_block()
        if not identity_matches:
            return empty_block()
        # Legacy fetch_specs silently returns [] when its existence guard is
        # false. A missing data store is a read failure, not authoritative zero.
        for name in ("DB_PATH", "_UA110_SPEC_DB_PATH"):
            path = getattr(legacy, name, None)
            if path is not None and not path.is_file():
                raise OSError("SPEC_STORE_UNAVAILABLE")
        return legacy.render_public_block(uid)
    return render, legacy._css


def ensure_html(source: str, uid: str, *, renderer: Callable[[str], str] | None = None,
                css: str | Callable[[], str] | None = None) -> str:
    """Return HTML with exactly one native, always available spec control.

    renderer(uid) must return the existing renderer's marked block. A successful
    result is authoritative for visibility/manual edits; a read exception keeps
    the validated current block, or produces an honest empty block on a new page.
    The default only lazily imports render_public_block/_css, never the injector.
    This function performs no file writes and preserves all unowned bytes.
    """
    _require(isinstance(source, str) and bool(source), "HTML_SOURCE_REQUIRED")
    uid = _uid(uid)
    spans, protected = owned_spans(source)
    if renderer is None or css is None:
        default_renderer, default_css = _renderer_functions()
        renderer = renderer or default_renderer
        css = default_css if css is None else css
    style = _safe_css(css() if callable(css) else css)
    # Some previously rendered pages have legacy VIN rules in this style block.
    # Keep that existing style exactly so this spec-only update cannot alter VIN
    # presentation. New styles contain only specification selectors.
    for left, right, kind in spans:
        if kind == "style":
            style = _safe_css(source[left:right], preserve_vin=True)
    try:
        block = _identified(renderer(uid))
    except Exception as exc:
        # Invalid or untrusted output is never copied. Existing validated facts
        # survive a read failure. Do not expose exception text/customer data.
        _LOG.warning("spec render fallback for %s (%s)", uid, type(exc).__name__)
        old = next((source[left:right] for left, right, kind in spans if kind == "block"), None)
        block = _identified(old) if old is not None else empty_block()
    page = source
    for left, right, kind in sorted(spans, reverse=True):
        page = page[:left] + (block if kind == "block" else style) + page[right:]
    kinds = {kind for _, _, kind in spans}
    if "block" not in kinds:
        _require(page.count(ANCHOR) <= 1, "DELIVERY_ANCHOR_AMBIGUOUS")
        if ANCHOR in page:
            index = page.index(ANCHOR)
        else:
            closers = list(re.finditer(r"</main\s*>", page, re.I))
            if len(closers) != 1:
                closers = list(re.finditer(r"</body\s*>", page, re.I))
            _require(len(closers) == 1, "SPEC_INSERTION_ANCHOR_AMBIGUOUS")
            index = closers[0].start()
        page = page[:index] + block + page[index:]
    if "style" not in kinds:
        heads = list(re.finditer(r"</head\s*>", page, re.I))
        _require(len(heads) == 1, "HEAD_ANCHOR_AMBIGUOUS")
        page = page[:heads[0].start()] + style + page[heads[0].start():]
    _, after_protected = owned_spans(page)
    _require(protected.encode("utf-8") == after_protected.encode("utf-8"), "PROTECTED_BYTES_CHANGED")
    _require(page.count(block) == page.count(style) == 1, "SPEC_FINAL_FRAGMENT_COUNT")
    return page
