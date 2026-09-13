"""Read-only grouping by the completed catalog HTML, never publication intent.

The integration must supply the complete authorized CRM list and the catalog
bytes from its existing committed local publication path. This module performs
no database, filesystem, HTTP, publication, or status writes.
"""
from html.parser import HTMLParser
import re
from typing import Any, Iterable, Mapping


_CAR_NUMBER = re.compile(r"UA-[0-9]{4,}\Z")
_BRAND = re.compile(r"\bUA\s+ART\b", re.IGNORECASE)
_STRUCTURAL = frozenset(("html", "head", "body", "title"))


class CatalogSnapshotError(ValueError):
    """The supplied catalog/CRM snapshot cannot be classified unambiguously."""


def _valid_number(value: Any) -> bool:
    return isinstance(value, str) and _CAR_NUMBER.fullmatch(value) is not None


class _CatalogParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.seen = set()
        self.closed_html = False
        self.title_parts = []
        self.numbers = set()

    def handle_starttag(self, tag, attrs):
        if tag == "html":
            if self.stack or "html" in self.seen or self.closed_html:
                raise CatalogSnapshotError("Catalog must contain exactly one HTML document")
        elif not self.stack or self.closed_html:
            raise CatalogSnapshotError("Element outside the catalog HTML document")
        if tag in _STRUCTURAL:
            if tag in self.seen:
                raise CatalogSnapshotError("Duplicate catalog structural element: " + tag)
            if tag in ("head", "body") and self.stack != ["html"]:
                raise CatalogSnapshotError("Invalid catalog structural nesting")
            if tag == "head" and "body" in self.seen:
                raise CatalogSnapshotError("Catalog head follows body")
            if tag == "title" and self.stack not in (["html"], ["html", "head"]):
                raise CatalogSnapshotError("Invalid catalog title location")
            self.stack.append(tag)
            self.seen.add(tag)
        if "title" in self.stack and tag != "title":
            raise CatalogSnapshotError("Markup inside catalog title")
        markers = [value for key, value in attrs if key == "data-ua-card"]
        if len(markers) > 1:
            raise CatalogSnapshotError("Duplicate data-ua-card attribute")
        if markers:
            number = markers[0]
            if not _valid_number(number):
                raise CatalogSnapshotError("Invalid catalog car number")
            if number in self.numbers:
                raise CatalogSnapshotError("Duplicate catalog car number: " + number)
            self.numbers.add(number)

    def handle_endtag(self, tag):
        if not self.stack or self.closed_html:
            raise CatalogSnapshotError("Closing element outside catalog HTML")
        if tag in _STRUCTURAL:
            if self.stack[-1] != tag:
                raise CatalogSnapshotError("Incomplete or misnested catalog document")
            self.stack.pop()
            if tag == "html":
                self.closed_html = True

    def handle_startendtag(self, tag, attrs):
        if tag in _STRUCTURAL:
            raise CatalogSnapshotError("Self-closing catalog structural element")
        self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        if (not self.stack or self.closed_html) and data.strip():
            raise CatalogSnapshotError("Text outside catalog HTML document")
        if self.stack and self.stack[-1] == "title":
            self.title_parts.append(data)

    def result(self) -> frozenset[str]:
        if not self.closed_html or self.stack or "title" not in self.seen:
            raise CatalogSnapshotError("Incomplete catalog HTML document")
        if _BRAND.search("".join(self.title_parts)) is None:
            raise CatalogSnapshotError("Catalog title does not identify UA ART")
        return frozenset(self.numbers)


def parse_catalog(source: str) -> frozenset[str]:
    """Extract unique canonical numbers from a complete UA ART HTML document."""
    if not isinstance(source, str) or not source.strip():
        raise CatalogSnapshotError("Missing catalog HTML")
    parser = _CatalogParser()
    try:
        parser.feed(source)
        parser.close()
    except CatalogSnapshotError:
        raise
    except (ValueError, AssertionError) as exc:
        raise CatalogSnapshotError("Malformed catalog HTML") from exc
    return parser.result()


def partition_by_catalog(
    cards: Iterable[Mapping[str, Any]], ids: Iterable[str]
) -> dict[str, list[Mapping[str, Any]]]:
    """Keep original rows and order; catalog membership wins over CRM intent."""
    catalog_ids = set()
    for number in ids:
        if not _valid_number(number) or number in catalog_ids:
            raise CatalogSnapshotError("Invalid or duplicate catalog identifier")
        catalog_ids.add(number)
    groups = {"catalog": [], "unpublished": []}
    seen_ids = set()
    seen_numbers = set()
    for card in cards:
        if not isinstance(card, Mapping):
            raise CatalogSnapshotError("Invalid CRM car record")
        cid = card.get("id")
        number = card.get("auto_number")
        if type(cid) is not int or cid <= 0 or cid in seen_ids:
            raise CatalogSnapshotError("Missing, invalid or duplicate CRM car id")
        if not _valid_number(number) or number in seen_numbers:
            raise CatalogSnapshotError("Missing, invalid or duplicate CRM car number")
        seen_ids.add(cid)
        seen_numbers.add(number)
        key = "catalog" if number in catalog_ids else "unpublished"
        groups[key].append(card)
    if catalog_ids - seen_numbers:
        raise CatalogSnapshotError("Catalog contains car numbers absent from the CRM snapshot")
    return groups
