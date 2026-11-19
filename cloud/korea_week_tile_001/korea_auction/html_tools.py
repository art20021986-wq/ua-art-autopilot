"""Small stdlib HTML helpers: visible text and table rows (cells with text, links, images)."""
import re
from html import unescape
from html.parser import HTMLParser

_TAGS = re.compile(r'(?s)<(script|style)\b.*?</\1>|<[^>]+>')


def text(html):
    """Visible text with collapsed whitespace."""
    return ' '.join(unescape(_TAGS.sub(' ', html)).split())


class _Rows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self._row, self._cell, self._depth = [], None, None, 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'table':
            self._depth += 1
        elif tag == 'tr' and self._depth == 1:
            self._row = []
        elif tag in ('td', 'th') and self._row is not None and self._depth == 1:
            self._cell = {'tag': tag, 'text': '', 'links': [], 'imgs': [], 'attrs': a}
            self._row.append(self._cell)
        elif self._cell is not None:
            if tag == 'a' and a.get('href'):
                self._cell['links'].append(a['href'])
            elif tag == 'img' and a.get('src'):
                self._cell['imgs'].append(a['src'])
            elif tag == 'br':
                self._cell['text'] += ' '

    def handle_endtag(self, tag):
        if tag == 'table':
            self._depth -= 1
        elif tag in ('td', 'th') and self._cell is not None and self._depth == 1:
            self._cell['text'] = ' '.join(self._cell['text'].split())
            self._cell = None
        elif tag == 'tr' and self._row is not None and self._depth == 1:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell['text'] += data


def table_rows(table_html):
    """Rows of one table (nested tables are skipped): list of lists of cells."""
    p = _Rows()
    p.feed(table_html)
    return p.rows


def table_containing(html, marker):
    """HTML of the innermost <table>...</table> that contains marker, or ''."""
    pos = html.find(marker)
    if pos < 0:
        return ''
    start = html.rfind('<table', 0, pos)
    end = html.find('</table>', pos)
    return html[start:end + len('</table>')] if start >= 0 and end >= 0 else ''
