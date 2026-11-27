"""Room kept from the first paint for parts that scripts add after the page is shown (PERF-CWV-001, owner «да» 2026-11-26).

1. The Korea auction ticker (home page). The page shows an empty slot <div id="ua-korea-ticker"> under the auctions
   block; a small loader fills it with /video/korea/ticker.html after the page is shown, and the slot grows from 0 to
   the ticker height, pushing everything below it down (Lighthouse CLS 0.297 on a phone). The slot keeps close to the
   ticker height from the start. HOME-BLOCKS-001 (2026-11-27): the ticker grew with the week tile (KOREA-PLAN-DAYS);
   measured on the live page at 320-600 px it is 898-1023 px high (about 30vw + 800 px up to 480 px, steeper above),
   from 601 px 669-693 px. The room is kept slightly below the measured height so a shorter week never leaves an empty
   gap; the rest is a small shift.
2. The menu button «☰» (pages with the .header-main header: home, catalogue, Korea). Up to 900 px wide the header
   script (i18n-home-ge.js / i18n.js) adds a 42×42 px .nav-toggle (order 2, margin-left auto) after the page is shown;
   at 380-420 px the language switch then drops to the next line and the page moves down (CLS 0.062 at 412 px,
   2026-11-27). Until the button is there, the header holds an empty box of the same size in the same place.
Only pages with the slot or the header get the matching rules; the markup and the scripts stay as they are.
"""
import ua_head_block

MARK = 'UA-LAYOUT-RESERVE-V1'
SLOT = 'id="ua-korea-ticker"'
HEADER = 'class="header-main"'
# html #id:empty outranks the loader's own «#ua-korea-ticker:empty{display:none}».
TICKER = ('html #ua-korea-ticker,html #ua-korea-ticker:empty{display:block;'
          'min-height:max(calc(30vw + 770px),calc(60vw + 620px))}'
          '@media (min-width:601px){html #ua-korea-ticker,html #ua-korea-ticker:empty{min-height:640px}}')
MENU = ('@media (max-width:900px){.header-main:not(:has(.nav-toggle))::after{content:"";order:2;flex:0 0 42px;'
        'height:42px;margin-left:auto}}')


def style(html):
    rules = (TICKER if SLOT in html else '') + (MENU if HEADER in html else '')
    return '<style id="ua-layout-reserve">' + rules + '</style>' if rules else ''


def apply(html):
    if not isinstance(html, str):
        return html
    value = style(html)
    return ua_head_block.put(html, MARK, value) if value else html


def remove(html):
    return ua_head_block.take(html, MARK) if isinstance(html, str) else html
