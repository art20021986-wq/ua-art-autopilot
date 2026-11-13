"""The logo as a clear way back to the home page (owner 2026-11-13, CHAT-BRAND-001).

The site headers already link the logo to the home page: a.brand (span.brand-mark + span.brand-copy) on the home,
catalogue, Korea and landing pages; .shapka .logo (div.znak + text) on the order, terms and car card pages.
apply(html) adds one style block before </body> that only decorates them: a thin gold ring around the «UA» mark and,
under «UA ART COMPANY · автомобілі з різних країн», a small gold-outlined caption «← На головну» (ru/ka by the page
language). The home page itself gets the ring only. Links and markup stay as they are. A page that already has the
block gets the current one in its place; a page without </body> is returned unchanged.
"""
import re

MARK = '<!--UA-BRAND-HOME-V1-->'
END = '<!--/UA-BRAND-HOME-V1-->'
GOLD = '#e8c87d'
# The «UA» mark and the text column under which the caption goes, for both header kinds.
_MARKS = ('a.brand .brand-mark', '.shapka .logo .znak')
_COPIES = ('a.brand .brand-copy', '.shapka .logo > div:not(.znak)')
_LABELS = (('', 'На головну'), ('ru', 'На главную'), ('ka', 'მთავარ გვერდზე'))
_HOME = re.compile(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\'][^"\']*/video/(?:index\.html)?["\']', re.I)


def _all(selectors, suffix='', lang=''):
    root = 'html[lang^="%s"] ' % lang if lang else ''
    return ','.join(root + s + suffix for s in selectors)


RING = _all(_MARKS) + '{outline:1.5px solid ' + GOLD + '!important;outline-offset:3px!important}'
CAPTION = (
    _all(_COPIES, '::after') + '{display:block!important;width:max-content!important;margin-top:7px!important;'
    'padding:3px 11px!important;border:1px solid rgba(232,200,125,.6)!important;border-radius:999px!important;'
    'color:' + GOLD + '!important;font:500 11px/1.3 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif!important;'
    'letter-spacing:.04em!important;text-transform:none!important}'
    + ''.join(_all(_COPIES, '::after', lang) + '{content:"\\2190\\00a0%s"!important}' % text for lang, text in _LABELS)
)


def block(home=False):
    return MARK + '<style id="ua-brand-home">' + RING + ('' if home else CAPTION) + '</style>' + END


def is_home(html):
    """The home page (its canonical address is /video/ or /video/index.html)."""
    return bool(_HOME.search(html))


def apply(html):
    """The page with the current logo style: an existing block is replaced in place, otherwise it goes just before
    the last </body>; unchanged without </body>."""
    if not isinstance(html, str):
        return html
    value = block(is_home(html))
    start = html.find(MARK)
    if start >= 0:
        end = html.find(END, start)
        return html if end < 0 else html[:start] + value + html[end + len(END):]
    at = html.rfind('</body>')
    if at < 0:
        return html
    return html[:at] + value + html[at:]
