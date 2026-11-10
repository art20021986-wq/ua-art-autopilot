"""JPAUTO-KOREA-001: home page additions (owner 2026-11-10).

apply(html) on the home page (the «Авто під замовлення» hero with the country flags):
  1. under the Korea flag — the «● Аукціони онлайн» mark;
  2. right after the hero — the slot of the Korea auction ticker. The ticker itself is a separate
     file (/video/korea/ticker.html) refreshed 3 times a day; a tiny loader inserts it, and the slot
     stays empty (invisible) if the file is missing.
Any other page, or a page that already has the additions, is returned unchanged.
"""
MARK = '<!--UA-KOREA-AUCTION-V1-->'
FLAG = '<a href="podbor.html?strana=korea'
HERO = '<section class="hero ua-order-first">'
TICKER_SRC = '/video/korea/ticker.html'

BADGE = ('<span class="ua-kr-live" data-uk="● Аукціони онлайн" data-ru="● Аукционы онлайн" '
         'data-ka="● აუქციონები ონლაინ">● Аукціони онлайн</span>')
STYLE = ('<style id="ua-korea-auction-v1">'
         '.ua-kr-live{display:block;margin-top:4px;font-size:12px;font-weight:700;color:#ff4d4d;'
         'text-align:center;white-space:nowrap;animation:ua-kr-blink 1.6s ease-in-out infinite}'
         '@keyframes ua-kr-blink{50%{opacity:.45}}'
         '@media (max-width:600px){.ua-kr-live{white-space:normal;font-size:10px;line-height:1.15;'
         'text-align:center}}'
         '@media (prefers-reduced-motion:reduce){.ua-kr-live{animation:none}}'
         '#ua-korea-ticker:empty{display:none}</style>')
SLOT = ('<div id="ua-korea-ticker"></div><script>(function(){var s=document.getElementById(\'ua-korea-ticker\');'
        'fetch(\'' + TICKER_SRC + '\',{cache:\'no-cache\'}).then(function(r){return r.ok?r.text():\'\';})'
        '.then(function(h){if(!h)return;var t=document.createElement(\'template\');t.innerHTML=h;'
        't.content.querySelectorAll(\'script\').forEach(function(o){var n=document.createElement(\'script\');'
        'n.textContent=o.textContent;o.replaceWith(n);});s.appendChild(t.content);})'
        '.catch(function(){});})();</script>')


def apply(html):
    """Home page with the Korea mark and ticker slot; anything else unchanged."""
    if not isinstance(html, str) or MARK in html or HERO not in html or FLAG not in html:
        return html
    flag = html.index(FLAG)
    end_a = html.index('</a>', flag)
    html = html[:end_a] + BADGE + html[end_a:]
    hero = html.index(HERO)
    end_hero = html.index('</section>', hero) + len('</section>')
    html = html[:end_hero] + MARK + STYLE + SLOT + html[end_hero:]
    return html
