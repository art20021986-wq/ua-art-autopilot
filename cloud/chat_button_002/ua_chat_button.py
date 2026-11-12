"""The floating «Contact a manager» button (owner 2026-11-10/11, mockup approved): one look on every page.

The pages already carry the floating WhatsApp link (a.mcf-chat / a.floating-chat on the site pages, a.chat on the cards),
styled by several older layers (a green circle on phones). apply(html) adds one style block before </body> that restyles
that link only: a translucent glass pill with a thin gold border and the label «Зв'язатися з менеджером» (ru/ka by the
page language). The link and its target stay as they are. On phones (owner 2026-11-12) the pill is larger and sits in the
bottom centre of the screen, above the iPhone home bar. A page that already has the block gets the current one in its
place (so a new look reaches every page); a page without </body> is returned unchanged.
"""

MARK = '<!--UA-CHAT-GLASS-V1-->'
END = '<!--/UA-CHAT-GLASS-V1-->'
# The floating link only; header and in-text WhatsApp links have other classes.
_CLASSES = ('mcf-chat', 'floating-chat', 'chat')


def _all(suffix='', lang=''):
    root = 'html[lang^="%s"]' % lang if lang else 'html'
    return ','.join('%s body a.%s[href*="wa.me"]%s' % (root, name, suffix) for name in _CLASSES)


def _label(lang, text):
    return _all('::after', lang) + '{content:"%s"!important}' % text


CSS = (
    _all() + '{display:inline-flex!important;align-items:center!important;gap:0!important;'
    'width:auto!important;min-width:0!important;max-width:none!important;height:auto!important;'
    'padding:8px 13px 8px 10px!important;border-radius:999px!important;overflow:visible!important;'
    'background:rgba(11,21,36,.55)!important;-webkit-backdrop-filter:blur(10px) saturate(140%)!important;'
    'backdrop-filter:blur(10px) saturate(140%)!important;border:1px solid rgba(232,200,125,.45)!important;'
    'color:#e8c87d!important;font-size:0!important;line-height:1!important;font-weight:500!important;'
    'text-decoration:none!important;white-space:nowrap!important;opacity:1!important;'
    'box-shadow:0 4px 16px rgba(0,0,0,.25)!important;transition:background .15s,border-color .15s}'
    + _all(':hover') + ',' + _all(':focus-visible') +
    '{background:rgba(11,21,36,.8)!important;border-color:#e8c87d!important;outline:none!important}'
    + _all(' svg') + '{display:block!important;width:16px!important;height:16px!important;flex:0 0 16px!important;'
    'fill:currentColor!important}'
    + _all(' > :not(svg)') + '{display:none!important}'
    + _all('::after') + '{display:inline!important;margin-left:7px!important;font-size:13px!important;line-height:1!important;'
    'color:#e8c87d!important;content:"Зв’язатися з менеджером"!important}'
    + _label('ru', 'Связаться с менеджером') + _label('ka', 'მენეჯერთან დაკავშირება')
    # Phones: larger, bottom centre, clear of the iPhone home bar.
    + '@media (max-width:767px){'
    + _all() + '{left:50%!important;right:auto!important;transform:translateX(-50%)!important;'
    'bottom:calc(16px + env(safe-area-inset-bottom,0px))!important;min-height:0!important;'
    'padding:13px 22px 13px 18px!important}'
    + _all(' svg') + '{width:22px!important;height:22px!important;flex:0 0 22px!important}'
    + _all('::after') + '{font-size:16px!important;margin-left:10px!important}}'
)
HTML = MARK + '<style id="ua-chat-glass">' + CSS + '</style>' + END


def apply(html):
    """The page with the current button style: an existing block is replaced in place, otherwise it goes just before
    the last </body>; unchanged without </body>."""
    if not isinstance(html, str):
        return html
    start = html.find(MARK)
    if start >= 0:
        end = html.find(END, start)
        return html if end < 0 else html[:start] + HTML + html[end + len(END):]
    at = html.rfind('</body>')
    if at < 0:
        return html
    return html[:at] + HTML + html[at:]
