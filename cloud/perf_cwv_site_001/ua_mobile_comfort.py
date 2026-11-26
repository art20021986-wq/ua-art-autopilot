"""Phone sizes for taps and small text (PERF-CWV-001, owner «да» 2026-11-26; 119 of 144 visits from Ukraine are phones).

Measured on the live pages at 360 px (2026-11-26): the RU / UA / GE switch on the home, catalogue and Korea pages reacts
only on its 19×15 px letters; the phone number in the header breaks onto two lines; the card's stage labels («ЕТАП 2 ІЗ
4», «ЗАРАЗ», «ПОТОЧНИЙ ЕТАП») are 8-9 px; the ticker arrows are 38 px and the header contact buttons 43 px. Guidance
(web.dev «Accessible tap targets»: 48×48 px; WCAG 2.5.5 and Apple: 44×44 px; text at least 12 px). One style block in
<head> on every page:
- the switch letters fill the switch box (44 px tall, 44 px wide each; the box grows a little to hold them);
- the phone number on one line;
- the card stage labels 12 px;
- the ticker arrows 44 px (48 px would cover more of the tile under them) and the header contact buttons 48 px tall on
  phones.
No new buttons, texts or links; nothing else changes.
"""
import ua_head_block

MARK = 'UA-MOBILE-COMFORT-V1'
STYLE = ('<style id="ua-mobile-comfort">'
         '.site-header .lang-toggle{gap:0}'
         '.site-header .lang-toggle button{min-width:44px;min-height:44px;padding:0 4px}'
         '.header-phone b{white-space:nowrap}'
         '.ua-stage-v1-count,.ua-stage-v1-now,.ua-stage-v1-current-copy small{font-size:12px!important}'
         '@media (max-width:600px){.korea-ticker .kt-arrow{width:44px;height:44px;line-height:40px}}'
         '@media (max-width:700px){.site-header .header-contacts a{min-height:48px}}'
         '</style>')


def apply(html):
    if not isinstance(html, str):
        return html
    return ua_head_block.put(html, MARK, STYLE)


def remove(html):
    return ua_head_block.take(html, MARK) if isinstance(html, str) else html
