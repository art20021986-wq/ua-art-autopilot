"""The floating «Contact a manager» button (owner 2026-11-10/11, mockup approved): one look on every page.

The pages already carry the floating WhatsApp link (a.mcf-chat / a.floating-chat on the site pages, a.chat on the cards),
styled by several older layers (a green circle on phones). apply(html) adds one style block before </body> that restyles
that link only: a translucent glass pill with a thin gold border and the label «Зв'язатися з менеджером» (ru/ka by the
page language). The link and its target stay as they are. On phones (owner 2026-11-12) the pill is larger and sits in the
bottom centre of the screen, above the iPhone home bar. A page that already has the block gets the current one in its
place (so a new look reaches every page); a page without </body> is returned unchanged. CHAT-BRAND-001 (owner 2026-11-13:
«кнопка кривая, косая — проверь на всех страницах»): the old page layers set different heights, margins, fonts and
animations on the link, so the pill now resets them and looks the same on every page. The SEO landing pages have no
floating link (owner «да» 2026-11-13 to add it): apply(html, add_link=True) puts the same link (wa.me/380992222002,
WhatsApp glyph) inside the block when the page has none.
"""

import re

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
    'width:auto!important;min-width:0!important;max-width:none!important;height:auto!important;min-height:0!important;'
    'margin:0!important;box-sizing:border-box!important;transform:none!important;animation:none!important;'
    'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif!important;'
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
LINK = 'https://wa.me/380992222002'
# The link for a page without one: fixed in the corner like the other pages (the phone rules above centre it).
ADDED = ('<style>a.ua-chat-added{position:fixed!important;right:16px;bottom:16px;z-index:2147482000}</style>'
         '<a class="mcf-chat ua-chat-added" href="' + LINK + '" target="_blank" rel="noopener noreferrer">'
         '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a10 10 0 0 0-8.6 15L2 22l5.2-1.4A10 10 0 1 0 12 2zm0 '
         '18a8 8 0 0 1-4.1-1.1l-.3-.2-3 .8.8-2.9-.2-.3A8 8 0 1 1 12 20zm4.4-5.9c-.2-.1-1.4-.7-1.6-.8-.2-.1-.4-.1-.5.1-.2.2'
         '-.6.8-.7.9-.1.2-.3.2-.5.1a6.5 6.5 0 0 1-3.2-2.8c-.2-.4.2-.4.6-1.1.1-.2 0-.3 0-.5s-.5-1.3-.7-1.7c-.2-.4-.4-.4-.5'
         '-.4h-.5c-.2 0-.5.1-.7.3-.3.3-.9.9-.9 2.1s.9 2.5 1.1 2.7c.1.2 1.8 2.9 4.5 4 .6.3 1.1.4 1.5.5.6.2 1.2.2 1.6.1.5-.1'
         ' 1.4-.6 1.6-1.2.2-.6.2-1.1.1-1.2 0-.1-.2-.2-.4-.3z"/></svg></a>')
# A floating link (class in single or double quotes, as the page writers emit them) to WhatsApp.
_FLOATING = re.compile(r'<a\b(?=[^>]*\bclass=["\'][^"\']*\b(?:%s)\b[^"\']*["\'])(?=[^>]*wa\.me)[^>]*>' % '|'.join(_CLASSES))


def has_link(html):
    """The page has a floating contact link (its own or the added one)."""
    return bool(_FLOATING.search(html))


def block(html, add_link=False):
    """The block for this page (html without the block); with add_link, the link too when the page has none."""
    if add_link and not has_link(html):
        return MARK + '<style id="ua-chat-glass">' + CSS + '</style>' + ADDED + END
    return HTML


def apply(html, add_link=False):
    """The page with the current button block: an existing block is replaced in place, otherwise it goes just before
    the last </body>; unchanged without </body>."""
    if not isinstance(html, str):
        return html
    start = html.find(MARK)
    if start >= 0:
        end = html.find(END, start)
        if end < 0:
            return html
        end += len(END)
        return html[:start] + block(html[:start] + html[end:], add_link) + html[end:]
    at = html.rfind('</body>')
    if at < 0:
        return html
    return html[:at] + block(html, add_link) + html[at:]
