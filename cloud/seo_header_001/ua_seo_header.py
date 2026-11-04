"""The site's top block on the landing pages (FINANCE-001 stage 5, owner «Да 5»): logo, contacts, languages.

The same block as the home page (video/index.html <header class="site-header">, styles from video/ua-v203.css and
the page's own rules, read 2026-11-04): UA ART COMPANY logo, phone, WhatsApp, Telegram, Viber, office on the map,
RU / UA / GE. It does not stick to the top while scrolling (owner's choice). The landing pages are static per
language, so RU and UA are links to the page's own language versions (hreflang) and GE opens the home page in
Georgian; the pages keep their navigation line below. Pure: (lang, versions) in, HTML out.
"""
from html import escape

import ua_seo_schema as schema

PHONE_TEXT = '+380 99 222 20 02'
WHATSAPP = 'https://wa.me/380992222002'
TELEGRAM = 'https://t.me/UA_artcompany_LLC_bot'
VIBER = 'viber://chat?number=%2B380992222002'
GEORGIAN = '/video/index.html?lang=ka'
TEXT = {'uk': dict(small='АВТОМОБІЛІ З РІЗНИХ КРАЇН', home='UA ART Company — головна', call='Зателефонувати',
                   map='Офіс на мапі', contacts='Контакти UA ART', languages='Вибір мови'),
        'ru': dict(small='АВТОМОБИЛИ ИЗ РАЗНЫХ СТРАН', home='UA ART Company — главная', call='Позвонить',
                   map='Офис на карте', contacts='Контакты UA ART', languages='Выбор языка')}
PHONE_ICON = ('<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
              'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
              '<path d="M8 3 5 5c-1 1 1 5 4 8s7 5 8 4l2-3-4-2-2 2c-2-1-4-3-5-5l2-2z"/></svg>')
MAP_ICON = ('<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
            'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            '<path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11Z"/><circle cx="12" cy="10" r="2.4"/></svg>')
CSS = (
    ':root{--ink:#f5f7fb;--muted:#a8b5c8;--dim:#6e7f98;--night:#07111e;--night-2:#0a1728;--card:#0e1d31;--card-2:#1'
    '2243a;--line:#263d59;--gold:#efa938;--gold-2:#c98422;--green:#5fd289;--blue:#77b5ed;--shadow:0 24px 70px rgba('
    '0,0,0,.28);--gold-glow:rgba(239,169,56,.14);}.header-main{min-height:112px;padding:22px 34px;display:flex;alig'
    'n-items:center;gap:30px;}.brand{display:flex;align-items:center;gap:16px;min-width:max-content;}.brand-mark{wi'
    'dth:72px;height:72px;display:grid;place-items:center;border-radius:18px;color:#0c1726;background:linear-gradie'
    'nt(145deg,#ffc35b,var(--gold));font-size:25px;font-weight:900;box-shadow:inset 0 1px rgba(255,255,255,.45),0 8'
    'px 24px rgba(232,168,56,.16);}.brand-copy{display:flex;flex-direction:column;gap:7px;}.brand-copy b{color:var('
    '--gold);letter-spacing:2.5px;font-size:22px;}.brand-copy small{color:var(--muted);letter-spacing:4px;font-size'
    ':11px;}.lang-toggle{flex:0 0 auto;height:52px;padding:0 13px;display:flex;align-items:center;gap:12px;border:1'
    'px solid var(--line);border-radius:15px;background:rgba(11,24,41,.7);}.lang-toggle i{width:1px;height:22px;bac'
    'kground:var(--line);}.header-contacts{display:grid;grid-template-columns:1.45fr .72fr 1fr;margin:0 34px 14px;o'
    'verflow:hidden;border:1px solid #314862;border-radius:17px;background:rgba(7,17,30,.86);}.header-contacts a{mi'
    'n-height:52px;display:flex;align-items:center;justify-content:center;gap:9px;border-right:1px solid #314862;co'
    'lor:#dce4ef;font-size:13px;}.header-contacts a:last-child{border-right:0;}.header-contacts svg{flex:0 0 auto;c'
    'olor:var(--gold);}.header-phone b{color:var(--ink);font-size:14px;}.header-whatsapp{color:#68df93 !important;f'
    'ont-weight:700;}@media (max-width:900px){.header-main{min-height:94px;padding:16px 20px;position:relative;flex'
    '-wrap:wrap;}.lang-toggle{order:3;}.header-contacts{order:4;}.header-contacts{margin:0 20px 12px;}.brand-mark{w'
    'idth:58px;height:58px;border-radius:15px;font-size:21px;}.brand-copy b{font-size:18px;}.brand-copy small{font-'
    'size:9px;letter-spacing:2.3px;}}@media (max-width:700px){.header-main{min-height:82px;padding:13px 16px;gap:10'
    'px;}.brand{gap:10px;min-width:0;}.brand-mark{width:48px;height:48px;border-radius:13px;font-size:17px;}.brand-'
    'copy{gap:4px;min-width:0;}.brand-copy b{font-size:13px;letter-spacing:1.4px;white-space:nowrap;}.brand-copy sm'
    'all{font-size:7px;letter-spacing:1.3px;white-space:nowrap;}.lang-toggle{height:42px;margin-left:auto;padding:0'
    ' 10px;gap:9px;border-radius:12px;}.header-contacts{grid-template-columns:1fr 1fr;margin:0 12px 10px;border-rad'
    'ius:14px;}.header-contacts a{min-height:43px;font-size:11px;}.header-phone{grid-column:1 / -1;border-right:0 !'
    'important;border-bottom:1px solid #314862;}.header-phone b{font-size:12px;}.header-whatsapp{border-right:1px s'
    'olid #314862 !important;}}@media (max-width:370px){.brand-copy small{display:none;}.brand-copy b{font-size:12p'
    'x;}}.header-contacts{grid-template-columns:1.45fr .72fr .72fr .72fr 1fr}.header-telegram{color:#5fb8f0!importa'
    'nt;font-weight:700}.header-viber{color:#a78bfa!important;font-weight:700}@media (max-width:700px){.header-cont'
    'acts{grid-template-columns:repeat(3,1fr)}.header-contacts .header-phone{grid-column:span 2;border-right:1px so'
    'lid #314862!important}.header-contacts .header-map{grid-row:1;grid-column:3;border-bottom:1px solid #314862;bo'
    'rder-right:0!important}.header-contacts .header-viber{border-right:0!important}}.site-header{position:static;m'
    'ax-width:none;margin:0;padding:0;background:rgba(7,17,30,.96);border-bottom:1px solid var(--line)}.site-header'
    ' a{text-decoration:none}.lang-toggle{margin-left:auto}.lang-toggle a{color:#8392a8;font-size:15px;font-weight:'
    '800}.lang-toggle a[aria-current]{color:var(--gold)}@media (max-width:700px){.lang-toggle a{font-size:13px}}'
)


def header(lang, versions):
    """versions: {'uk': '/video/seo/ua/….html', 'ru': '/video/seo/ru/….html'} of this page."""
    t = TEXT[lang]
    languages = '<i></i>'.join(
        '<a href="{}" hreflang="{}" lang="{}"{}>{}</a>'.format(
            escape(href, quote=True), code, code, ' aria-current="true"' if code == lang else '', label)
        for code, label, href in (('ru', 'RU', versions['ru']), ('uk', 'UA', versions['uk']), ('ka', 'GE', GEORGIAN)))
    return ''.join((
        '<header class="site-header"><div class="header-main">',
        '<a href="/video/index.html" class="brand" aria-label="{}"><span class="brand-mark">UA</span>'.format(
            escape(t['home'], quote=True)),
        '<span class="brand-copy"><b>UA ART COMPANY</b><small>{}</small></span></a>'.format(escape(t['small'])),
        '<nav class="lang-toggle" aria-label="{}">{}</nav></div>'.format(escape(t['languages'], quote=True), languages),
        '<div class="header-contacts" aria-label="{}">'.format(escape(t['contacts'], quote=True)),
        '<a class="header-phone" href="tel:{}">{}<span>{}</span><b>{}</b></a>'.format(
            escape(schema.PHONE, quote=True), PHONE_ICON, escape(t['call']), PHONE_TEXT),
        '<a class="header-whatsapp" href="{}" target="_blank" rel="noopener noreferrer">WhatsApp</a>'.format(WHATSAPP),
        '<a class="header-telegram" href="{}" target="_blank" rel="noopener noreferrer">Telegram</a>'.format(TELEGRAM),
        '<a class="header-viber" href="{}">Viber</a>'.format(VIBER),
        '<a class="header-map" href="{}" target="_blank" rel="noopener noreferrer">{}<span>{}</span></a>'.format(
            escape(schema.MAP, quote=True), MAP_ICON, escape(t['map'])),
        '</div></header>'))
