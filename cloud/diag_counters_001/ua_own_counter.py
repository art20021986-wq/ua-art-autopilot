"""The site's own counter (/ua/a.js, reports in the client bot «Аналитика») for public pages; no I/O.

The same line analitika_wsgi.STROKA has always added, right before </body>.
"""
MARK = '<!--UA-ANALIT-V1-->'
LINE = "<script src='/ua/a.js?v=1' defer></script>" + MARK


def apply(html):
    """The page with the counter before </body>; unchanged if it already counts or has no body end."""
    if not isinstance(html, str) or MARK in html:
        return html
    end = html.lower().rfind('</body>')
    if end < 0:
        return html
    return html[:end] + LINE + html[end:]
