"""Build the CARD-FULLSCREEN-001 candidate: one new stylesheet and one line on each auction page.

video/order/lot-card.css (new): on a phone the opened lot card (dialog #kl-card) fills the screen, our buttons stay on top,
only the card scrolls. video/korea.html, video/japan.html: one <link> line before </head>; every other byte stays. No writer
rewrites these pages, so rollback restores them byte for byte. USA (video/usa.html) is the page of session 45.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
STYLE = 'video/order/lot-card.css'
PAGES = ('video/korea.html', 'video/japan.html')
LINE = '<link rel="stylesheet" href="/video/order/lot-card.css?v=card-fullscreen-1">'
DEPENDENCY_SHA256 = {}


def targets(root):
    """Existing files the candidate replaces (the stylesheet is added beside them)."""
    return PAGES


def page(html):
    """The page with the stylesheet line once, right before </head>."""
    if LINE in html:
        raise ValueError('CARD_FULLSCREEN_ALREADY_APPLIED')
    if html.count('</head>') != 1 or html.count('id="kl-card"') != 1:
        raise ValueError('CARD_FULLSCREEN_PAGE_SHAPE')
    return html.replace('</head>', LINE + '</head>')


def unpage(html):
    """The page with the line taken out (the exact page before the install)."""
    return html.replace(LINE, '', 1)


def build(source, dependencies):
    """{name: new bytes}."""
    result = {STYLE: (HERE/'lot-card.css').read_bytes()}
    for name in PAGES:
        result[name] = page(source[name].decode('utf-8')).encode('utf-8')
    return result


def is_page(name):
    return name.endswith('.html')
