"""The «Ми на AUTO.RIA» badge with the official AUTO.RIA logo at the bottom of every page (owner 2026-11-13).

The home page footer already has it (a.ua-autoria-badge with the logo, AUTORIA-REVIEWS-001). The Korea auctions pages
have the badge with the plain text «AUTO.RIA» instead of the logo; the other pages have none. apply(html) adds one
block: on a page without the badge, the same badge (logo file /video/brand/autoria-logo.svg, same link, label by the
page language) at the end of the footer, just before the social icons; on a page with a text-only badge, a style
that shows the logo in place of the text (the text stays for screen readers). A page that already has the block gets
the current one in its place; a page without </body> is returned unchanged.
"""
import re

MARK = '<!--UA-AUTORIA-BADGE-V1-->'
END = '<!--/UA-AUTORIA-BADGE-V1-->'
LINK = 'https://auto.ria.com/uk/dealers/yua-art-kompani/3356/'
LOGO = '/video/brand/autoria-logo.svg'
SOCIAL = '<!--UA-SOCIAL-V1-->'
_LABELS = {'ru': 'Мы на', 'uk': 'Ми на', 'ka': 'გვიპოვეთ'}
_LANG = re.compile(r'<html[^>]*\blang=["\']?([a-z]{2})', re.I)
_BLOCK = re.compile(re.escape(MARK) + '.*?' + re.escape(END), re.S)
GOLD = '#efa938'  # the home page badge colour
# A text-only badge (the Korea pages): the logo drawn in place of the word, same size as on the home page.
TEXT_LOGO = ('a.ua-autoria-badge span.ua-autoria-mark{display:inline-block!important;width:88px!important;'
             'height:26px!important;font-size:0!important;color:transparent!important;'
             'background:url(' + LOGO + ') center/contain no-repeat!important}')
# The added badge: the home page look (gold outline, logo after the label), centred like the social icons.
BADGE_CSS = ('.ua-autoria-row{text-align:center;margin:16px 0 0}'
             '.ua-autoria-row .ua-autoria-badge{display:inline-flex;align-items:center;gap:10px;padding:7px 12px;'
             'border:1px solid ' + GOLD + ';border-radius:10px;color:' + GOLD + ';font:700 13px/1.2 -apple-system,'
             'BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;text-decoration:none}'
             '.ua-autoria-row .ua-autoria-mark{display:block;width:88px;height:26px}')


def _badge(lang):
    label = _LABELS.get(lang, _LABELS['uk'])
    data = ''.join(' data-%s="%s"' % item for item in sorted(_LABELS.items()))
    return ('<div class="ua-autoria-row"><a class="ua-autoria-badge" href="%s" target="_blank" '
            'rel="noopener noreferrer" data-autoria="footer_badge"><span%s>%s</span><img class="ua-autoria-mark" '
            'src="%s" alt="AUTO.RIA" width="88" height="26" loading="lazy" decoding="async"></a></div>'
            % (LINK, data, label, LOGO))


def block(html):
    """The block for this page (html without the block): style only if the page has its own badge."""
    if 'ua-autoria-badge' in html:
        return MARK + '<style id="ua-autoria-badge">' + TEXT_LOGO + '</style>' + END
    found = _LANG.search(html)
    return MARK + '<style id="ua-autoria-badge">' + BADGE_CSS + '</style>' + _badge(
        found.group(1).lower() if found else 'uk') + END


def _place(html):
    """Where the block goes: before the social icons, else the end of the last footer, else before </body>."""
    if 'ua-autoria-badge' in html:
        return html.rfind('</body>')
    for marker in (SOCIAL, '</footer>', '</body>'):
        at = html.rfind(marker)
        if at >= 0:
            return at
    return -1


def apply(html):
    """The page with the current badge block (an existing one is replaced in place); unchanged without </body>."""
    if not isinstance(html, str) or '</body>' not in html:
        return html
    found = _BLOCK.search(html)
    if found:
        rest = html[:found.start()] + html[found.end():]
        return html[:found.start()] + block(rest) + html[found.end():]
    at = _place(html)
    return html[:at] + block(html) + html[at:]
