"""Two buttons under the logo: «⌂ Головна» and «‹ Назад» (LOGO-001, owner «Да» 2026-11-28; cloud/header_nav_001).

They replace the caption «← На головну». apply(html) writes them into the header just before the RU / UA / GE switch, so
on a phone they share the switch's row (left: the buttons, right: the switch): a.brand headers (catalogue, Korea, Japan,
USA, landings) and .shapka headers (cards, order page, terms). The home page and pages without such a header are
returned unchanged. Gold-outlined pills 30 px high, the touch area 44 px. Labels by the page language (uk, ru, ka), as the
caption had them. «Головна» opens the home page; «Назад» goes back when the visitor came from a uaart.com.ua page,
otherwise opens the home page. The card header is clickable as a whole (to the home page): the buttons keep the click.
ua_brand_home puts CSS into its <head> block.
"""
import re

START = '<!--UA-HEADER-NAV-V1-->'
END = '<!--/UA-HEADER-NAV-V1-->'
HOME = '/video/index.html'
_HOME_ICON = ('<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.4" '
              'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 10.5 12 3l9 7.5"/>'
              '<path d="M5 9.5V21h14V9.5"/></svg>')
_BACK_ICON = ('<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.8" '
              'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg>')
_BACK = ("event.stopPropagation();try{if(history.length-1)if(/(^|\\.)uaart\\.com\\.ua$/.test(new window.URL(document.referrer)"
         ".hostname)){history.back();return false}}catch(e){}")
NAV = (START + '<div class="ua-hnav">'
       '<a class="ua-hnav-home" href="' + HOME + '" onclick="event.stopPropagation()">' + _HOME_ICON + '<span></span></a>'
       '<a class="ua-hnav-back" href="' + HOME + '" onclick="' + _BACK + '">' + _BACK_ICON + '<span></span></a>'
       '</div>' + END)
_LABELS = (('', 'Головна', 'Назад'), ('ru', 'Главная', 'Назад'), ('ka', 'მთავარი', 'უკან'))
GOLD = '#e8c87d'


def _label(button, lang, text):
    return ('html[lang^="%s"] ' % lang if lang else '') + '.%s span::after{content:"%s"}' % (button, text)


CSS = (
    '.ua-hnav{display:flex!important;align-items:center;gap:6px;margin:0;padding:0;order:3}'
    '.ua-hnav a{position:relative;display:inline-flex!important;align-items:center;gap:4px;box-sizing:border-box;'
    'height:30px!important;min-height:0!important;margin:0!important;padding:0 12px!important;border:1px solid rgba(232,200,125,.6)!important;'
    'border-radius:999px!important;background:none!important;color:' + GOLD + '!important;text-decoration:none!important;'
    'font:500 12.5px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif!important;letter-spacing:0;'
    'white-space:nowrap;cursor:pointer}'
    '.ua-hnav a::before{content:"";position:absolute;inset:-7px -3px}'
    '.ua-hnav svg{flex:none;width:11px;height:11px}'
    + ''.join(_label('ua-hnav-home', lang, home) + _label('ua-hnav-back', lang, back) for lang, home, back in _LABELS)
    # The card header is a block: the buttons stand on the switch's row, left.
    + '.shapka .ua-hnav{float:left;margin-top:15px}'
)
_HEADER = re.compile(r'<a [^>]*class="brand"|<div class=[\'"]logo[\'"]>')
_SWITCH = re.compile(r'<(?:div|nav) class="lang-toggle[^"]*"')
# Cards and the order page get their switch later in the same writer chain (ua_lang_bar, just before .svyaz): there the
# buttons go before .svyaz, so the switch lands right after them (LOGO-CARD-001).
_SVYAZ = re.compile(r'<div class=[\'"]svyaz[\'"]>')


def apply(html):
    """The buttons before the header's language switch (once); a page without a brand header or switch is unchanged."""
    if not isinstance(html, str):
        return html
    start = html.find(START)
    if start >= 0:
        end = html.find(END, start)
        return html if end < 0 else html[:start] + NAV + html[end + len(END):]
    header = _HEADER.search(html, max(html.find('<body'), 0))
    switch = _SWITCH.search(html, header.end()) if header else None
    if switch is None:
        switch = _SVYAZ.search(html, header.end()) if header else None
    if switch is None:
        return html
    return html[:switch.start()] + NAV + html[switch.start():]


def remove(html):
    """The buttons taken out (rollback of a page another writer rewrote since)."""
    if not isinstance(html, str):
        return html
    start = html.find(START)
    end = html.find(END, start) if start >= 0 else -1
    return html if end < 0 else html[:start] + html[end + len(END):]
