"""Pure initial migration of existing HTML price slots. Never regenerate pages.

Caller must bind source byte hashes, obtain all writer/CRM locks, backup and
publish atomically. No I/O, live modules or CRM are imported here.
"""

from dataclasses import dataclass, field
from hashlib import sha256
from html.parser import HTMLParser
import re
from urllib.parse import parse_qs, urlsplit

from uaart_market_prices import END, START, normalized_usd, render_market_prices, replace_catalog_price_slot


@dataclass
class Element:
    tag: str
    attrs: dict
    start: int
    opening_end: int
    parent: object
    children: list = field(default_factory=list)
    end: int | None = None


class Structure(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.source = text
        # HTMLParser advances line numbers only on LF, not every Unicode line
        # separator accepted by str.splitlines(). Preserve exact source offsets.
        self.offsets = [0] + [match.end() for match in re.finditer("\n", text)]
        self.elements, self.stack = [], []
        self.feed(text)
        self.close()
        if self.stack:
            raise ValueError("PRICE_DOM_UNCLOSED_CONTAINER")

    def char_position(self):
        line, column = self.getpos()
        return self.offsets[line - 1] + column

    def handle_starttag(self, tag, attrs):
        if tag not in ("div", "article", "b"):
            return
        start = self.char_position()
        parent = self.stack[-1] if self.stack else None
        node = Element(tag, dict(attrs), start, start + len(self.get_starttag_text()), parent)
        if parent is not None:
            parent.children.append(node)
        self.elements.append(node)
        self.stack.append(node)

    def handle_endtag(self, tag):
        if tag not in ("div", "article", "b"):
            return
        if not self.stack or self.stack[-1].tag != tag:
            raise ValueError("PRICE_DOM_CONTAINER_MISMATCH")
        node = self.stack.pop()
        end = self.source.find(">", self.char_position())
        if end < 0:
            raise ValueError("PRICE_DOM_CLOSING_TAG_INVALID")
        node.end = end + 1


class Text(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.tags = []
        self.feed(source)

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def _classes(node):
    return set(node.attrs.get("class", "").split())


def _one(items, reason):
    if len(items) != 1:
        raise ValueError(reason)
    return items[0]


def _verify_old_ua(source, row):
    visible = "".join(Text(source).parts).strip()
    match = re.fullmatch(r"([0-9][0-9 \u00a0\u202f]*(?:\.[0-9]{1,2})?)\s*(?:\$|USD)", visible)
    expected = normalized_usd(row.get("price_uah"))
    if match:
        old = normalized_usd(re.sub(r"[ \u00a0\u202f]", "", match.group(1)))
    elif visible.casefold() in ("цена уточняется", "цена по запросу", "ціна уточнюється", "ціна за запитом", ""):
        old = ""
    else:
        raise ValueError("INITIAL_UA_PRICE_UNRECOGNIZED")
    if old != expected:
        raise ValueError("INITIAL_UA_PRICE_CRM_MISMATCH")


def _verify_old_caption(source):
    parsed = Text(source)
    if sum(tag == "div" for tag, _ in parsed.tags) != 1:
        raise ValueError("INITIAL_PRICE_CAPTION_EXTRA_MARKUP")
    allowed = {"class", "style", "data-ru", "data-ua", "data-uk", "data-ge", "data-ka"}
    if any(tag not in {"div", "span", "br"} or set(attrs) - allowed for tag, attrs in parsed.tags):
        raise ValueError("INITIAL_PRICE_CAPTION_EXTRA_MARKUP")
    visible = re.sub(r"[\s·.]+", " ", " ".join(parsed.parts)).strip()
    approved_legacy = {
        "Под ключ в Киеве доплат нет",
        "Під ключ у Києві доплат немає",
        "Под ключ в Киеве Выкуп на аукционе, доставка, растаможка и сертификат — доплат нет",
        "Під ключ у Києві Викуп на аукціоні, доставка, розмитнення та сертифікат — доплат немає",
    }
    if visible not in approved_legacy:
        raise ValueError("INITIAL_PRICE_CAPTION_CONTENT_UNKNOWN")


def _identity(source, row):
    component = render_market_prices(row, require_car_id=True)
    if START in source or END in source:
        raise ValueError("INITIAL_PRICE_MARKER_ALREADY_PRESENT")
    if set(re.findall(r"UA-[0-9]{4,}", source)) != {row["auto_number"]}:
        raise ValueError("INITIAL_PRICE_CAR_ID_MISMATCH")
    return component


def migrate_card(source, row):
    """Insert two market blocks in the known existing card price container only."""
    component = _identity(source, row)
    structure = Structure(source)
    amount = _one([node for node in structure.elements if node.tag == "div" and _classes(node) & {"cn_b", "cena"}], "INITIAL_CARD_PRICE_NODE_COUNT")
    _verify_old_ua(source[amount.start:amount.end], row)
    if "cn_b" in _classes(amount):
        container = amount.parent
        if container is None or container.tag != "div":
            raise ValueError("INITIAL_CARD_PRICE_PARENT")
        caption = _one([node for node in container.children if node.tag == "div" and "cn_p" in _classes(node)], "INITIAL_CARD_CAPTION_NODE_COUNT")
        if container.children != [amount, caption]:
            raise ValueError("INITIAL_CARD_PRICE_PARENT_EXTRA_CONTENT")
        if (source[container.opening_end:amount.start].strip()
                or source[amount.end:caption.start].strip()
                or not re.fullmatch(r"\s*</div\s*>\s*", source[caption.end:container.end], re.I)):
            raise ValueError("INITIAL_CARD_PRICE_PARENT_EXTRA_CONTENT")
        start, end = container.start, container.end
    else:
        siblings = amount.parent.children if amount.parent else []
        index = siblings.index(amount)
        if index + 1 >= len(siblings):
            raise ValueError("INITIAL_CARD_CAPTION_MISSING")
        caption = siblings[index + 1]
        if caption.tag != "div" or not (_classes(caption) & {"tihо", "tiho"}):
            raise ValueError("INITIAL_CARD_CAPTION_MISMATCH")
        if source[amount.end:caption.start].strip():
            raise ValueError("INITIAL_CARD_PRICE_SPAN_EXTRA_CONTENT")
        start, end = amount.start, caption.end
    _verify_old_caption(source[caption.start:caption.end])
    candidate = source[:start] + component + source[end:]
    if candidate[:start] != source[:start] or candidate[start + len(component):] != source[end:]:
        raise AssertionError("INITIAL_CARD_OUTSIDE_PRICE_CHANGED")
    return candidate, {
        "card": row["auto_number"], "price_regions_changed": 1,
        "before_sha256": sha256(source.encode()).hexdigest(),
        "after_sha256": sha256(candidate.encode()).hexdigest(),
        "outside_price_unchanged": True,
    }


def migrate_catalog(source, rows):
    """Patch all current modern catalog article price slots, preserving its shell."""
    if START in source or END in source:
        raise ValueError("INITIAL_PRICE_MARKER_ALREADY_PRESENT")
    row_map = {}
    for row in rows:
        render_market_prices(row, require_car_id=True)
        code = row["auto_number"]
        if code in row_map:
            raise ValueError("INITIAL_CATALOG_DUPLICATE_CRM_ID")
        row_map[code] = row
    if not row_map and HomeInventory(source).car_price_surface:
        raise ValueError("INITIAL_EMPTY_CATALOG_CAR_SURFACE")
    structure = Structure(source)
    articles = [node for node in structure.elements if node.tag == "article" and "catalog-card" in _classes(node)]
    seen, replacements = set(), []
    for node in articles:
        article = source[node.start:node.end]
        code = _one(sorted(set(re.findall(r"UA-[0-9]{4,}", article))), "INITIAL_CATALOG_ARTICLE_ID")
        if code not in row_map or code in seen:
            raise ValueError("INITIAL_CATALOG_CARD_SET_MISMATCH")
        seen.add(code)
        top = _one([child for child in structure.elements if child.tag == "div" and "catalog-top" in _classes(child) and node.start < child.start < node.end], "INITIAL_CATALOG_PRICE_TOP_COUNT")
        old_price = _one([child for child in top.children if child.tag == "b"], "INITIAL_CATALOG_PRICE_NODE_COUNT")
        _verify_old_ua(source[old_price.start:old_price.end], row_map[code])
        changed = replace_catalog_price_slot(article, row_map[code])
        component = render_market_prices(row_map[code], compact=True, require_car_id=True)
        local_start, local_end = old_price.start - node.start, old_price.end - node.start
        if changed != article[:local_start] + component + article[local_end:]:
            raise AssertionError("INITIAL_CATALOG_OUTSIDE_PRICE_CHANGED")
        replacements.append((old_price.start, old_price.end, component))
    if seen != set(row_map):
        raise ValueError("INITIAL_CATALOG_CARD_SET_MISMATCH")
    candidate = source
    for start, end, fragment in sorted(replacements, reverse=True):
        candidate = candidate[:start] + fragment + candidate[end:]
    return candidate, {
        "cards": sorted(seen), "price_regions_changed": len(replacements),
        "before_sha256": sha256(source.encode()).hexdigest(),
        "after_sha256": sha256(candidate.encode()).hexdigest(),
        "outside_price_unchanged": True,
    }


class HomeInventory(HTMLParser):
    """Inspect homepage links without interpreting/executing scripts."""
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.anchors = []
        self.car_price_surface = False
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(attrs.get("class", "").split())
        if tag == "a":
            self.anchors.append(attrs)
            if re.search(r"(?:^|/)UA-[0-9]{4,}(?:\.html)?(?:[?#]|$)", attrs.get("href", ""), re.I):
                self.car_price_surface = True
        if (classes & {"catalog-card", "plitka", "ua-stage-card-v2", "ua-market-prices-v1", "cn", "cn_b", "cena"}
                or "data-ua-car" in attrs or "data-ua-market" in attrs):
            self.car_price_surface = True


def _catalog_link(attrs):
    parsed = urlsplit(attrs.get("href", ""))
    if parsed.scheme not in ("", "https") or parsed.netloc not in ("", "uaart.com.ua", "www.uaart.com.ua"):
        raise ValueError("INITIAL_HOME_CATALOG_LINK_UNKNOWN")
    if parsed.path not in ("katalog.html", "./katalog.html", "/video/katalog.html", "/katalog.html"):
        raise ValueError("INITIAL_HOME_CATALOG_LINK_UNKNOWN")
    return parsed


def migrate_home(source, rows):
    """Preserve the confirmed stage-only home; never price a representative car.

    A homepage with individual car previews requires an explicit supported
    migration. Unknown or newly introduced price surfaces fail closed. The
    existing stranica individual-car homepage generator already renders compact
    dual-price fragments directly; it is not the current live homepage route.
    """
    codes = set()
    for row in rows:
        render_market_prices(row, require_car_id=True)
        code = row["auto_number"]
        if code in codes:
            raise ValueError("INITIAL_HOME_DUPLICATE_CRM_ID")
        codes.add(code)
    if START in source or END in source:
        raise ValueError("INITIAL_HOME_MARKED_PRICE_SURFACE_REQUIRES_MIGRATION")
    inventory = HomeInventory(source)
    if inventory.car_price_surface:
        raise ValueError("INITIAL_HOME_CAR_PRICE_SURFACE_REQUIRES_MIGRATION")
    stages = [attrs for attrs in inventory.anchors if "stage-card" in attrs.get("class", "").split()]
    expected = {"kiev", "georgia", "sea", "korea"}
    if len(stages) != 4 or {attrs.get("data-stage") for attrs in stages} != expected:
        raise ValueError("INITIAL_HOME_STAGE_TOPOLOGY_UNKNOWN")
    for attrs in stages:
        query = parse_qs(_catalog_link(attrs).query)
        if query.get("f") != [attrs["data-stage"]]:
            raise ValueError("INITIAL_HOME_STAGE_LINK_MISMATCH")
    calls = [attrs for attrs in inventory.anchors if "outline-cta" in attrs.get("class", "").split()]
    if len(calls) != 1:
        raise ValueError("INITIAL_HOME_CATALOG_CTA_UNKNOWN")
    if _catalog_link(calls[0]).query:
        raise ValueError("INITIAL_HOME_CATALOG_CTA_FILTERED")
    source_hash = sha256(source.encode("utf-8")).hexdigest()
    return source, {
        "surface": "HOME", "topology": "STAGE_ONLY", "no_car_price_surfaces": True,
        "price_regions_changed": 0, "stage_links": 4, "published_count": len(codes),
        "before_sha256": source_hash, "after_sha256": source_hash,
        "outside_price_unchanged": True, "all_bytes_unchanged": True,
    }
