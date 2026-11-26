"""Room for the Korea auction ticker kept from the first paint (PERF-CWV-001, owner «да» 2026-11-26).

The home page shows an empty slot <div id="ua-korea-ticker"> right under the auctions block; a small loader fills it
with /video/korea/ticker.html after the page is shown, and the slot grows from 0 to the ticker height, pushing the
«Авто під замовлення» block and everything below it down (Lighthouse CLS 0.297 on a phone). This style keeps the slot at
the ticker height from the start: 494 px up to 600 px wide (the ticker's phone layout), 426 px wider (measured on the
live page 2026-11-26 at 360, 412, 768 and 1280 px). Only pages with the slot get it; the slot markup and the loader
(ua_korea_home.py) stay as they are.
"""
import ua_head_block

MARK = 'UA-LAYOUT-RESERVE-V1'
SLOT = 'id="ua-korea-ticker"'
# html #id:empty outranks the loader's own «#ua-korea-ticker:empty{display:none}».
STYLE = ('<style id="ua-layout-reserve">'
         'html #ua-korea-ticker,html #ua-korea-ticker:empty{display:block;min-height:494px}'
         '@media (min-width:601px){html #ua-korea-ticker,html #ua-korea-ticker:empty{min-height:426px}}'
         '</style>')


def apply(html):
    if not isinstance(html, str) or SLOT not in html:
        return html
    return ua_head_block.put(html, MARK, STYLE)


def remove(html):
    return ua_head_block.take(html, MARK) if isinstance(html, str) else html
