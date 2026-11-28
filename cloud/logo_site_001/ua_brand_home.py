"""The site header's logo and the way back home (owner 2026-11-13 CHAT-BRAND-001; LOGO-001, owner «Да» 2026-11-28).

The site headers link the logo to the home page: a.brand (span.brand-mark + span.brand-copy) on the home, catalogue,
Korea and landing pages; .shapka .logo (div.znak + text) on the order, terms and car card pages. apply(html) adds one style
block in <head>: the new logo C in place of the «UA» square (ua_logo_c) and, on every page but the home page, the
«Головна» / «Назад» buttons' style (ua_header_nav), and writes the buttons into the header. LOGO-001 replaces the gold ring
around the mark and the caption «← На головну» of CHAT-BRAND-001.
The block stands in <head> (PERF-CWV-001); a page that already has it gets the current one in its place; a page without
</head> keeps it before </body>; a page without either is returned unchanged.
"""
import re

import ua_header_nav
import ua_logo_c

MARK = '<!--UA-BRAND-HOME-V1-->'
END = '<!--/UA-BRAND-HOME-V1-->'
_HOME = re.compile(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\'][^"\']*/video/(?:index\.html)?["\']', re.I)


def block(home=False):
    return MARK + '<style id="ua-brand-home">' + ua_logo_c.CSS + ('' if home else ua_header_nav.CSS) + '</style>' + END


def is_home(html):
    """The home page (its canonical address is /video/ or /video/index.html)."""
    return bool(_HOME.search(html))


def _style(html, value):
    start = html.find(MARK)
    if start >= 0:
        end = html.find(END, start)
        if end < 0:
            return html
        if end < html.find('</head>'):
            return html[:start] + value + html[end + len(END):]
        html = html[:start] + html[end + len(END):]
    at = html.find('</head>')
    if at < 0:
        at = html.rfind('</body>')
    if at < 0:
        return html
    return html[:at] + value + html[at:]


def apply(html):
    """The page with the current header style in <head> (a block already in <head> is replaced in place, one elsewhere is
    taken out and the current one goes just before the first </head>, before the last </body> on a page without <head>;
    unchanged without both) and, except on the home page, the buttons in the header."""
    if not isinstance(html, str):
        return html
    home = is_home(html)
    html = _style(html, block(home))
    return html if home else ua_header_nav.apply(html)
