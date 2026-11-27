"""The home page's three main blocks set apart (HOME-BLOCKS-001, owner «Да» 2026-11-27 to the mockup).

Owner: the auctions, the individual order and the cars in stock should read as separate blocks so that people do not
mix them up; in the site's style, no big changes. One style block in <head> of the home page only: each block is a
panel with a thin gold frame, rounded corners and a soft shadow (auctions: .ua-kr-auc with the ticker slot under it;
individual order: .hero.ua-order-first with its photo .ua-home-photo; cars in stock: #stages), with air and a gold line
with a small diamond between them. No new buttons, texts or sections; nothing moves after the page is shown (CSS only,
in <head>). Mockup: cloud/home_blocks_001/mockup.css.
"""
import ua_head_block

MARK = 'UA-HOME-BLOCKS-V1'
HOME = 'class="ua-kr-auc"'
FRAME = 'border:1px solid rgba(232,200,125,.34)'
SHADOW = 'box-shadow:0 18px 44px rgba(0,0,0,.34)'
STYLE = (
    '<style id="ua-home-blocks">'
    '.ua-kr-auc,.hero.ua-order-first,#stages{position:relative;margin:34px 12px 0;' + FRAME + ';border-radius:22px;'
    'background:linear-gradient(180deg,rgba(232,200,125,.06),rgba(11,21,36,0) 140px),#0a1626;' + SHADOW + '}'
    '.ua-kr-auc{margin-top:16px;border-bottom:0;border-radius:22px 22px 0 0;'
    'background:linear-gradient(135deg,#1a0f00,#0B1524 60%)}'
    '#ua-korea-ticker{margin:0 12px;' + FRAME + ';border-top:0;border-radius:0 0 22px 22px;overflow:hidden;' + SHADOW + '}'
    '.hero.ua-order-first{overflow:visible;border-bottom:0;border-radius:22px 22px 0 0;box-shadow:none}'
    '.ua-home-photo{margin:0 12px;' + FRAME + ';border-top:0;border-radius:0 0 22px 22px;overflow:hidden;' + SHADOW + '}'
    '#stages{padding:22px 12px 26px}'
    '.hero.ua-order-first::before,#stages::before{content:"";position:absolute;left:12%;right:12%;top:-19px;height:1px;'
    'background:linear-gradient(90deg,transparent,rgba(232,200,125,.7),transparent)}'
    '.hero.ua-order-first::after,#stages::after{content:"";position:absolute;left:50%;top:-23px;width:8px;height:8px;'
    'margin-left:-4px;transform:rotate(45deg);background:#e8c87d;box-shadow:0 0 10px rgba(232,200,125,.6)}'
    '@media (min-width:900px){.ua-kr-auc,.hero.ua-order-first,#stages{margin:44px 40px 0}.ua-kr-auc{margin-top:22px}'
    '#ua-korea-ticker,.ua-home-photo{margin:0 40px}#stages{padding:30px 34px 40px}'
    '.hero.ua-order-first::before,#stages::before{top:-23px}.hero.ua-order-first::after,#stages::after{top:-27px}}'
    '</style>')


def apply(html):
    if not isinstance(html, str) or HOME not in html:
        return html
    return ua_head_block.put(html, MARK, STYLE)


def remove(html):
    return ua_head_block.take(html, MARK) if isinstance(html, str) else html
