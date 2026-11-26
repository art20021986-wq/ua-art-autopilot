"""The RU / UA / GE language switch in the page itself on pages with the .shapka header (PERF-CWV-001, owner «да» 2026-11-26).

On the car cards and the order page the switch is built by /video/ua-site-languages.js after the page is shown: the
script inserts it in .shapka just before .svyaz and the header grows by 52 px, pushing the photo gallery down
(Lighthouse CLS 0.21-0.32 on a phone). The script uses a switch that is already on the page (it looks for .lang-toggle
first, adds GE if missing and handles clicks on any .lang-toggle button), so this module writes the same switch into the
page, in the same place, with the script's own style in <head>. On pages whose switch is already in the page but has
only RU and UA (the catalogue), the script adds GE after the page is shown and the header moves; GE is written into the
switch the same way. Nothing new is shown: the switch looks and works as now. Any other page is returned unchanged.
"""
import re

import ua_head_block

MARK = 'UA-LANG-BAR-V1'
BAR = ('<div class="lang-toggle ua-site-lang" aria-label="Выбор языка">'
       '<button type="button" data-lang="ru">RU</button><i></i>'
       '<button type="button" data-lang="uk">UA</button><i></i>'
       '<button type="button" data-lang="ka">GE</button></div>')
# The style ua-site-languages.js adds for its switch (the same rules, so nothing moves when the script adds them again).
STYLE = ('<style id="ua-lang-bar">.ua-site-lang{display:flex;align-items:center;justify-content:center;gap:0;'
         'width:max-content;max-width:100%;margin:8px 0 0 auto;padding:4px;border:1px solid #2b405a;border-radius:14px;'
         'background:#0d1826}.ua-site-lang button{min-width:44px;min-height:34px;padding:6px 8px;border:0;background:none;'
         'color:#9fb0c4;font-family:inherit;font-weight:700;font-size:14px;line-height:1.2;cursor:pointer}'
         '.ua-site-lang button.active{color:#e8a33d}.ua-site-lang i{display:block;width:1px;height:14px;'
         'background:#2b405a}</style>')
GE = '<i></i><button type="button" data-lang="ka">GE</button>'
TOGGLE = re.compile(r'<div class="lang-toggle"[^>]*>')
SHAPKA = re.compile(r'<div class=[\'"]shapka[\'"]>')
SVYAZ = re.compile(r'<div class=[\'"]svyaz[\'"]>')


def _with_ge(html):
    """The page's own switch with GE at its end, as the script adds it (the switch holds only buttons and dividers)."""
    toggle = TOGGLE.search(html)
    if toggle is None:
        return html
    end = html.find('</div>', toggle.end())
    if end < 0 or 'data-lang="ka"' in html[toggle.end():end] or '<div' in html[toggle.end():end]:
        return html
    return html[:end] + GE + html[end:]


def apply(html):
    if not isinstance(html, str):
        return html
    if 'lang-toggle' in html:
        return _with_ge(html)
    header = SHAPKA.search(html)
    contacts = SVYAZ.search(html, header.end()) if header else None
    if contacts is None:
        return html
    html = html[:contacts.start()] + BAR + html[contacts.start():]
    return ua_head_block.put(html, MARK, STYLE)


def remove(html):
    """This module's additions taken back (rollback of a page another writer rewrote since)."""
    if not isinstance(html, str):
        return html
    toggle = TOGGLE.search(html)
    if toggle is not None:
        end = html.find('</div>', toggle.end())
        if end > 0 and html[:end].endswith(GE):
            html = html[:end - len(GE)] + html[end:]
    return ua_head_block.take(html.replace(BAR, '', 1), MARK)
