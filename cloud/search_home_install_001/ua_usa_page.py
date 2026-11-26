"""The USA auctions page video/usa.html (SEARCH-HOME-001, owner «Да» 2026-11-26).

Only HTML: takes the live Korea page as the site shell (head styles, header, footer, scripts) and puts the USA
content between <main id="main-content"> and </main>, plus the USA title/description/canonical. Texts carry the
site's data-uk/ru/ka twins, switched by ua-site-languages.js like every page. The calculator itself is usa-calc.js.
"""
import html
import re

NAME = 'video/usa.html'
URL = 'https://www.uaart.com.ua/video/usa.html'
MAIN_OPEN = '<main id="main-content">'
MAIN_CLOSE = '</main>'
SCRIPT = '/video/usa/usa-calc.js?v=usa-calc-1'

TITLE = {'uk': 'Аукціони США Copart та IAAI — авто під ключ | UA ART COMPANY',
         'ru': 'Аукционы США Copart и IAAI — авто под ключ | UA ART COMPANY',
         'ka': 'აშშ-ის აუქციონები Copart და IAAI — ავტომობილი სრული მომსახურებით | UA ART COMPANY'}
DESCRIPTION = {'uk': 'Авто з аукціонів Copart та IAAI під ключ до Києва. Порахуйте доставку за хвилину: оберіть, де стоїть авто.',
               'ru': 'Авто с аукционов Copart и IAAI под ключ до Киева. Посчитайте доставку за минуту: выберите, где стоит авто.',
               'ka': 'ავტომობილები Copart და IAAI აუქციონებიდან კიევამდე. დაითვალეთ მიწოდება ერთ წუთში.'}

OFFER = {'uk': 'Авто з усіх країн під ключ · послуга 600\u00a0$ за договором · інші витрати — за рахунками аукціонів і перевізників',
         'ru': 'Авто из всех стран под ключ · услуга 600\u00a0$ по договору · остальные расходы — по счетам аукционов и перевозчиков',
         'ka': 'ავტომობილები ყველა ქვეყნიდან სრული მომსახურებით · მომსახურება 600\u00a0$ ხელშეკრულებით · დანარჩენი ხარჯები — აუქციონებისა და გადამზიდავების ანგარიშებით'}

T = {
    'eyebrow': ('🇺🇸 Аукціони США · Copart · IAAI', '🇺🇸 Аукционы США · Copart · IAAI', '🇺🇸 აშშ-ის აუქციონები · Copart · IAAI'),
    'h1': ('Авто з аукціонів Америки — під ключ', 'Авто с аукционов Америки — под ключ',
           'ავტომობილები ამერიკის აუქციონებიდან — სრული მომსახურებით'),
    'lead': ('Обираєте авто на Copart або IAAI — ми викуповуємо, оформлюємо документи, страхуємо та веземо до Києва.',
             'Выбираете авто на Copart или IAAI — мы выкупаем, оформляем документы, страхуем и везём до Киева.',
             'აირჩიეთ ავტომობილი Copart-ზე ან IAAI-ზე — ჩვენ ვყიდულობთ, ვაფორმებთ საბუთებს, ვაზღვევთ და მოგვაქვს კიევამდე.'),
    'inc': ('Що входить', 'Что входит', 'რას მოიცავს'),
    'calc': ('Скільки коштує під ключ', 'Сколько стоит под ключ', 'რა ღირს სრული მომსახურებით'),
    'where': ('Де стоїть авто', 'Где стоит авто', 'სად დგას ავტომობილი'),
    'ph': ('Місто, штат або індекс майданчика', 'Город, штат или индекс площадки', 'ქალაქი, შტატი ან ინდექსი'),
    'type': ('Тип авто', 'Тип авто', 'ავტომობილის ტიპი'),
    'car': ('🚗 Легкове', '🚗 Легковое', '🚗 მსუბუქი'),
    'suv': ('🚙 Позашляховик', '🚙 Внедорожник', '🚙 ჯიპი'),
    'other': ('Інше', 'Другое', 'სხვა'),
    'lead_btn': ('Залишити заявку', 'Оставить заявку', 'განაცხადის დატოვება'),
    'go': ('Залишити заявку на авто зі США', 'Оставить заявку на авто из США', 'განაცხადი ავტომობილზე აშშ-დან'),
}
INCLUDED = (
    ('Доступ до аукціонів Copart та IAAI — безкоштовно', 'Доступ к аукционам Copart и IAAI — бесплатно',
     'წვდომა Copart და IAAI აუქციონებზე — უფასოდ'),
    ('Викуп авто з аукціону', 'Выкуп авто с аукциона', 'ავტომობილის გამოსყიდვა აუქციონიდან'),
    ('Звіт Carfax — 0 $', 'Отчёт Carfax — 0 $', 'Carfax-ის ანგარიში — 0 $'),
    ('Страхування 0,5–1% від вартості авто, відшкодування оригінальними запчастинами',
     'Страхование 0,5–1% от стоимости авто, возмещение оригинальными запчастями',
     'დაზღვევა ავტომობილის ღირებულების 0,5–1%, ანაზღაურება ორიგინალი ნაწილებით'),
    ('Переоформлення документів — більшість безкоштовно; junk-документи (WI, IN, WA bill of sale) — 100 $',
     'Переоформление документов — большинство бесплатно; junk-документы (WI, IN, WA bill of sale) — 100 $',
     'საბუთების გადაფორმება — უმეტესად უფასოდ; junk-საბუთები (WI, IN, WA bill of sale) — 100 $'),
    ('Pending title — безкоштовна стоянка в портах США', 'Pending title — бесплатная стоянка в портах США',
     'Pending title — უფასო სადგომი აშშ-ის პორტებში'),
    ('Завантаження в контейнер і супровід до прибуття', 'Погрузка в контейнер и сопровождение до прибытия',
     'კონტეინერში ჩატვირთვა და თანხლება ჩამოსვლამდე'),
    ('Гібриди та електромобілі — +100 $', 'Гибриды и электромобили — +100 $', 'ჰიბრიდები და ელექტრომობილები — +100 $'),
    ('Особистий кабінет і підтримка 24/7', 'Личный кабинет и поддержка 24/7', 'პირადი კაბინეტი და მხარდაჭერა 24/7'),
)
STYLE = (
    '.ua-us{padding:22px 16px 26px;color:#e6ecf5;max-width:1148px;margin:0 auto;box-sizing:border-box}'
    '.ua-us .ey{color:#ffb020;font-weight:800;letter-spacing:.14em;font-size:12px;text-transform:uppercase}'
    '.ua-us h1{color:#fff;font-size:clamp(24px,4vw,38px);line-height:1.15;margin:8px 0}'
    '.ua-us .lead{color:#c9d3e0;margin:0 0 16px;font-size:15px}'
    '.ua-us h2{color:#ffd000;font-size:18px;margin:22px 0 10px}'
    '.ua-us ul.inc{list-style:none;padding:0;margin:0;display:grid;gap:8px}'
    '.ua-us ul.inc li{background:#0f1b2d;border:1px solid #2a3a52;border-radius:12px;padding:10px 12px;font-size:15px}'
    '.ua-us .calc{background:#fff;border-radius:16px;padding:14px;color:#111}'
    '.ua-us .calc label{display:block;font-size:12px;font-weight:700;color:#5a6678;margin:4px 0 6px}'
    '.ua-us .calc input{width:100%;box-sizing:border-box;height:50px;font-size:17px;padding:0 14px;'
    'border:2px solid #ffb020;border-radius:12px;background:#fff;color:#111}'
    '.ua-us [role=listbox]{list-style:none;margin:6px 0 12px;padding:0;border:1px solid #e3e8ef;border-radius:12px;'
    'max-height:300px;overflow:auto}'
    '.ua-us [role=option]{padding:11px 14px;font-size:15px;border-bottom:1px solid #eef1f5;cursor:pointer}'
    '.ua-us [role=option][aria-selected=true]{background:#fff6dd}'
    '.ua-us .ty{display:flex;gap:6px;margin-bottom:14px}'
    '.ua-us .ty button{flex:1;padding:11px 4px;border-radius:12px;border:1.5px solid #d5dbe4;background:#fff;'
    'font:700 14px/1.2 inherit;color:#111;cursor:pointer}'
    '.ua-us .ty button[aria-pressed=true]{border-color:#ffb020;background:#fff6dd}'
    '.ua-us .tot{background:#0B1524;color:#fff;border-radius:14px;padding:14px 16px;display:grid;gap:2px}'
    '.ua-us .tot span,.ua-us .tot small{color:#c9d3e0;font-size:14px}'
    '.ua-us .tot b{font-size:34px;color:#ffd000;line-height:1.2}'
    '.ua-us details{margin-top:10px}.ua-us summary{font-weight:700;font-size:14px;color:#5a6678;cursor:pointer}'
    '.ua-us .res div{display:flex;justify-content:space-between;gap:10px;padding:9px 0;border-bottom:1px solid #eef1f5;font-size:14px}'
    '.ua-us .res b{white-space:nowrap}.ua-us .calc p{font-size:13px;color:#5a6678;margin:8px 0 0}'
    '.ua-us a.go{display:block;text-align:center;margin-top:18px;padding:15px;border-radius:12px;font-weight:800;'
    'color:#111;text-decoration:none;background:linear-gradient(90deg,#ffd000,#ff8a00)}'
    '.ua-us-offer{margin:14px 16px 0;padding:14px 16px;border:1px solid rgba(212,175,55,.55);border-radius:14px;'
    'background:linear-gradient(180deg,rgba(212,175,55,.18),rgba(212,175,55,.06));color:#f4e3ae;font-weight:700;'
    'font-size:16px;line-height:1.35;display:flex;flex-direction:column;gap:10px;max-width:1148px;box-sizing:border-box}'
    '.ua-us-offer-go{display:block;text-align:center;padding:13px;border-radius:12px;background:#e8a33d;color:#111;'
    'font-weight:800;text-decoration:none}'
    '@media(min-width:900px){.ua-us{padding:34px 60px}.ua-us ul.inc{grid-template-columns:1fr 1fr}}'
)


def _attrs(values, attr='data'):
    return ' '.join('%s-%s="%s"' % (attr, lang, html.escape(v, quote=True)) for lang, v in zip(('uk', 'ru', 'ka'), values))


def _t(tag, values, extra=''):
    return '<%s %s%s>%s</%s>' % (tag, _attrs(values), extra, html.escape(values[0]), tag)


def content():
    offer = (OFFER['uk'], OFFER['ru'], OFFER['ka'])
    items = ''.join(_t('li', v) for v in INCLUDED)
    calc = ('<div class="calc" id="usa-calc" hidden>'
            '<label for="usa-where" %s>%s</label>'
            '<input id="usa-where" type="text" role="combobox" aria-autocomplete="list" aria-expanded="false" '
            'aria-controls="usa-yards" autocomplete="off" %s placeholder="%s">'
            '<ul id="usa-yards" role="listbox" hidden></ul>'
            '<label %s>%s</label><div class="ty">'
            '<button type="button" data-kind="car" aria-pressed="true" %s>%s</button>'
            '<button type="button" data-kind="suv" aria-pressed="false" %s>%s</button>'
            '<button type="button" data-kind="other" aria-pressed="false" %s>%s</button></div>'
            '<div id="usa-result" aria-live="polite"></div></div>'
            % (_attrs(T['where']), T['where'][0], _attrs(T['ph'], 'data-ph'), T['ph'][0],
               _attrs(T['type']), T['type'][0], _attrs(T['car']), T['car'][0], _attrs(T['suv']), T['suv'][0],
               _attrs(T['other']), T['other'][0]))
    lead = T['lead_btn']
    return ('<style>%s</style><div class="ua-us-offer"><div %s>%s</div>'
            '<a class="ua-us-offer-go" href="podbor.html?strana=usa&amp;lang=uk" %s>%s</a></div><section class="ua-us">'
            '%s%s%s%s<ul class="inc">%s</ul>%s%s'
            '<a class="go" href="podbor.html?strana=usa&amp;lang=uk" %s>%s</a></section>'
            '<script src="%s" defer></script>'
            % (STYLE, _attrs(offer), html.escape(offer[0]), _attrs(lead), lead[0],
               _t('div', T['eyebrow'], ' class="ey"'), _t('h1', T['h1']), _t('p', T['lead'], ' class="lead"'),
               _t('h2', T['inc']), items, _t('h2', T['calc']), calc, _attrs(T['go']), T['go'][0], SCRIPT))


def _meta(start, values):
    """<meta ...> with the site's data-uk-content/ru/ka twins."""
    twins = ' '.join('data-%s-content="%s"' % (lang, html.escape(v, quote=True)) for lang, v in zip(('uk', 'ru', 'ka'), values))
    return '%s content="%s" %s>' % (start, html.escape(values[0], quote=True), twins)


def _replace_one(pattern, value, source, code):
    source, n = re.subn(pattern, lambda m: value, source, count=1, flags=re.S)
    if n != 1:
        raise ValueError(code)
    return source


def _head(source):
    title, desc = tuple(TITLE[k] for k in ('uk', 'ru', 'ka')), tuple(DESCRIPTION[k] for k in ('uk', 'ru', 'ka'))
    source = _replace_one(r'<title[^>]*>.*?</title>', '<title %s>%s</title>' % (_attrs(title), html.escape(title[0])),
                          source, 'KOREA_LAYOUT_TITLE')
    source = _replace_one(r'<meta name="description"[^>]*>', _meta('<meta name="description"', desc), source, 'KOREA_LAYOUT_DESC')
    source = _replace_one(r'<meta property="og:title"[^>]*>', _meta('<meta property="og:title"', title), source, 'KOREA_LAYOUT_OG')
    source = _replace_one(r'<meta property="og:description"[^>]*>', _meta('<meta property="og:description"', desc),
                          source, 'KOREA_LAYOUT_OG')
    source = _replace_one(r'<link rel="canonical" href="[^"]*">', '<link rel="canonical" href="%s">' % URL, source, 'KOREA_LAYOUT_CANON')
    source = _replace_one(r'<meta property="og:url" content="[^"]*">', '<meta property="og:url" content="%s">' % URL,
                          source, 'KOREA_LAYOUT_OG')
    return re.sub(r'<link rel="alternate" hreflang="[^"]+" href="[^"]*">', '', source)


def build(korea_html):
    """korea.html text -> usa.html text."""
    if korea_html.count(MAIN_OPEN) != 1 or korea_html.count(MAIN_CLOSE) != 1:
        raise ValueError('KOREA_LAYOUT_MAIN')
    start = korea_html.index(MAIN_OPEN) + len(MAIN_OPEN)
    end = korea_html.index(MAIN_CLOSE)
    return _head(korea_html[:start]) + content() + korea_html[end:]
