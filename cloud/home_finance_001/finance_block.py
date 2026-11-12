"""Markup and style of the home «Кредит і лізинг» block (HOME-FINANCE-001). No page parsing here.

Two partner cards side by side: ОТП Банк credit (bank green, its advantage — a car on its way or under order — on a
gold badge) and ХАПАЙ Авто leasing (the partner's violet). Each card opens its section of the finance page.
Every text element holds its three languages in data-ru / data-uk / data-ka with the Ukrainian text inside (one text
node per element), as the site's language script expects. Logos are the files already on the site, translate="no".
"""
import finance_text as T

MARK = 'ua-home-finance-001'
ARROW = ('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" '
         'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14m-5-5 5 5-5 5"/></svg>')


def text(tag, words, cls=''):
    ru, uk, ka = words
    for value in words:
        if any(c in value for c in '<>"&'):
            raise ValueError('HOME_FINANCE_TEXT')
    return '<%s%s data-ru="%s" data-uk="%s" data-ka="%s">%s</%s>' % (
        tag, ' class="%s"' % cls if cls else '', ru, uk, ka, uk, tag)


def card(item):
    width, height = item['size']
    badge = text('span', item['badge'], 'ua-fin-badge') if item['badge'] else ''
    return ('<a class="ua-fin-card ua-fin-%s" href="%s#%s">%s<span class="ua-fin-arrow">%s</span>'
            '<img class="ua-fin-logo" src="%s" width="%d" height="%d" alt="%s" translate="no" loading="lazy" '
            'decoding="async">%s%s%s</a>'
            % (item['key'], T.PAGE, item['anchor'], text('span', item['kind'], 'ua-fin-kind'), ARROW, item['logo'],
               width, height, item['alt'], badge, text('b', item['main'], 'ua-fin-main'),
               text('span', item['go'], 'ua-fin-go')))


def section():
    return ('<section class="ua-fin section-frame" id="kredyt-lizynh" aria-labelledby="ua-fin-h">%s'
            '<h2 id="ua-fin-h" data-ru="%s" data-uk="%s" data-ka="%s">%s</h2><div class="ua-fin-grid">%s</div></section>'
            % (text('span', T.KICKER, 'section-kicker'), T.TITLE[0], T.TITLE[1], T.TITLE[2], T.TITLE[1],
               ''.join(card(item) for item in T.CARDS)))


CSS = ('<style id="%s">'
       '.ua-fin h2{margin:6px 0 0;font-size:clamp(20px,2.3vw,26px);line-height:1.2;letter-spacing:-.3px}'
       '.ua-fin-grid{margin-top:14px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}'
       '.ua-fin-card{position:relative;display:flex;flex-direction:column;align-items:flex-start;gap:10px;'
       'padding:16px 18px;border:1px solid var(--fin-line);border-radius:18px;color:#fff;text-decoration:none;'
       'overflow:hidden;isolation:isolate;box-shadow:0 18px 42px rgba(0,0,0,.3),inset 0 1px rgba(255,255,255,.22);'
       'transition:transform .2s ease,box-shadow .2s ease}'
       '.ua-fin-card::before{content:"";position:absolute;inset:0;z-index:-1;'
       'background:linear-gradient(120deg,rgba(255,255,255,.14),transparent 38%%)}'
       '.ua-fin-card:hover{transform:translateY(-2px);box-shadow:0 24px 52px rgba(0,0,0,.38),inset 0 1px rgba(255,255,255,.28)}'
       '.ua-fin-card:focus-visible{outline:2px solid var(--gold,#efa938);outline-offset:3px}'
       '.ua-fin-otp{--fin-line:rgba(120,214,80,.55);background:radial-gradient(120%% 110%% at 100%% 0%%,'
       'rgba(108,206,64,.6),transparent 58%%),linear-gradient(150deg,#2f8a1c,#1f5e12 60%%,#123f0a)}'
       '.ua-fin-hapai{--fin-line:rgba(150,96,255,.6);background:radial-gradient(120%% 110%% at 100%% 0%%,'
       'rgba(139,74,255,.55),transparent 58%%),linear-gradient(150deg,#2a1760,#170d3a 60%%,#0d0824)}'
       '.ua-fin-kind{padding:4px 10px;border:1px solid rgba(255,255,255,.3);border-radius:999px;'
       'background:rgba(255,255,255,.1);font-size:11px;font-weight:800;letter-spacing:1.6px;text-transform:uppercase}'
       '.ua-fin-logo{display:block;height:auto;max-width:100%%}'
       '.ua-fin-otp .ua-fin-logo{width:132px}.ua-fin-hapai .ua-fin-logo{width:176px;margin:8px 0 6px}'
       '.ua-fin-badge{padding:4px 10px;border-radius:999px;background:linear-gradient(135deg,#ffd77e,#efa938);'
       'color:#1d1405;font-size:11px;font-weight:800;letter-spacing:.4px;box-shadow:0 4px 14px rgba(239,169,56,.35)}'
       '.ua-fin-main{font-size:16px;line-height:1.3;font-weight:800}'
       '.ua-fin-go{margin-top:auto;color:#ffe3a6;font-size:13px;font-weight:700;line-height:1.35}'
       '.ua-fin-arrow{position:absolute;top:14px;right:14px;width:30px;height:30px;display:grid;place-items:center;'
       'border:1px solid rgba(255,255,255,.3);border-radius:50%%;background:rgba(255,255,255,.12);color:#ffe3a6;'
       'transition:transform .2s ease}'
       '.ua-fin-card:hover .ua-fin-arrow{transform:translateX(3px)}'
       '@media(max-width:560px){.ua-fin-grid{gap:10px}.ua-fin-card{padding:14px 12px;gap:8px;border-radius:16px}'
       '.ua-fin-arrow{top:12px;right:10px;width:26px;height:26px}.ua-fin-main{font-size:14px}.ua-fin-badge{font-size:10px;padding:3px 8px;border-radius:10px}'
       '.ua-fin-otp .ua-fin-logo{width:112px}.ua-fin-hapai .ua-fin-logo{width:150px}}'
       '@media(max-width:340px){.ua-fin-grid{grid-template-columns:1fr}}'
       '@media(prefers-reduced-motion:reduce){.ua-fin-card,.ua-fin-arrow{transition:none}'
       '.ua-fin-card:hover,.ua-fin-card:hover .ua-fin-arrow{transform:none}}'
       '</style>' % MARK)
