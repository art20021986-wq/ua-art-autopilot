"""Isolated Stage A parser only; no CRM runtime is imported.
_Anchors is an exact text extraction from the source named in provenance.json.
This module deliberately provides no publication or CRM worker interfaces.
"""
from html.parser import HTMLParser
import re

class SyncError(RuntimeError):
    pass

class _Anchors(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.lines = [0]
        self.lines.extend(m.end() for m in re.finditer("\n", source))
        self.opened = None
        self.anchors = []
        self.article_opened = None
        self.articles = []
        self.feed(source)
        self.close()
        if self.opened is not None or self.article_opened is not None:
            raise SyncError("UNCLOSED_CATALOG_ANCHOR")

    def source_offset(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        if tag == "article":
            if self.article_opened is not None:
                raise SyncError("NESTED_CATALOG_ARTICLE")
            self.article_opened = self.source_offset()
        if tag == "a":
            if self.opened is not None:
                raise SyncError("NESTED_CATALOG_ANCHOR")
            self.opened = (self.source_offset(), dict(attrs).get("href", ""))

    def handle_endtag(self, tag):
        if tag == "article":
            if self.article_opened is None:
                raise SyncError("UNMATCHED_CATALOG_ARTICLE")
            self.articles.append((self.article_opened, self.source.find(">", self.source_offset()) + 1))
            self.article_opened = None
        if tag == "a":
            if self.opened is None:
                raise SyncError("UNMATCHED_CATALOG_ANCHOR")
            start, href = self.opened
            end = self.source.find(">", self.source_offset()) + 1
            self.anchors.append((start, end, href))
            self.opened = None
