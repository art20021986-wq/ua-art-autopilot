"""One marked block in <head> (PERF-CWV-001): styles that must apply before the page is first drawn.

put(html, mark, block) replaces the block between <!--mark--> and <!--/mark--> in place when it is already in <head>;
otherwise it takes out an earlier copy wherever it stands and puts the given one just before the first </head>. A page
without </head> is returned unchanged. take(html, mark) removes the block (rollback of a page another writer rewrote
since).
"""


def _bounds(mark):
    return '<!--%s-->' % mark, '<!--/%s-->' % mark


def take(html, mark):
    start_mark, end_mark = _bounds(mark)
    start = html.find(start_mark)
    if start < 0:
        return html
    end = html.find(end_mark, start)
    if end < 0:
        return html
    return html[:start] + html[end + len(end_mark):]


def put(html, mark, block):
    if not isinstance(html, str) or '</head>' not in html:
        return html
    start_mark, end_mark = _bounds(mark)
    start = html.find(start_mark)
    end = html.find(end_mark, start) if start >= 0 else -1
    if 0 <= start < end < html.find('</head>'):
        return html[:start] + start_mark + block + html[end:]
    html = take(html, mark)
    at = html.find('</head>')
    return html[:at] + start_mark + block + end_mark + html[at:]
