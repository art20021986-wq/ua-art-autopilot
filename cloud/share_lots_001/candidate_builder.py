"""Build the SHARE-LOTS-001 candidate: one new file and one line on each auction page.

video/order/lot-share.js (new, the only code): the «Поділитися» button in the opened lot card (dialog #kl-card).
video/korea.html, video/japan.html: one <script> line before </body>; every other byte stays. No writer rewrites these
pages, so rollback restores them byte for byte. USA (video/usa.html) is the page of session 45: it adds the same line.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = 'video/order/lot-share.js'
PAGES = ('video/korea.html', 'video/japan.html')
LINE = '<script src="/video/order/lot-share.js?v=share-lots-1" defer></script>'
DEPENDENCY_SHA256 = {}


def targets(root):
    """Existing files the candidate replaces (the script is added beside them)."""
    return PAGES


def page(html):
    """The page with the share script line once, right before </body>."""
    if LINE in html:
        raise ValueError('SHARE_LOTS_ALREADY_APPLIED')
    if html.count('</body>') != 1 or html.count('id="kl-card"') != 1:
        raise ValueError('SHARE_LOTS_PAGE_SHAPE')
    return html.replace('</body>', LINE + '</body>')


def unpage(html):
    """The page with the line taken out (the exact page before the install)."""
    return html.replace(LINE, '', 1)


def build(source, dependencies):
    """{name: new bytes}."""
    result = {SCRIPT: (HERE/'lot-share.js').read_bytes()}
    for name in PAGES:
        result[name] = page(source[name].decode('utf-8')).encode('utf-8')
    return result


def is_page(name):
    return name.endswith('.html')
