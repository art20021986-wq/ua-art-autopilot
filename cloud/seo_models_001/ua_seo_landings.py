"""Search landing pages (hub, order page, Japan page, one per model; Ukrainian and Russian) from catalog facts.

Pure: car facts in, {relative path under video/: html} out. Deterministic, so the
writer can skip unchanged files and the sitemap date means a real content change.
Texts state only terms already published on info.html; custom-order model texts
come from ua_seo_order_models. The hub answers the common
questions in plain text (and FAQPage JSON-LD), so search engines and AI assistants
can quote the terms directly.
"""
from html import escape
import re

import ua_seo_order_models as order_models
import ua_seo_schema as schema

ORIGIN = 'https://www.uaart.com.ua'
LANGS = ('uk', 'ru')
DIRS = {'uk': 'ua', 'ru': 'ru', 'ka': 'gu'}
HUB = {'uk': 'avto-z-korei-do-kyieva-pid-kluch', 'ru': 'avto-iz-korei-v-kiev-pod-kluch',
       'ka': 'avtomobili-koreidan-sakartveloshi'}
MODEL_SUFFIX = {'uk': 'koreya-kyiv', 'ru': 'koreya-kiev', 'ka': 'koreidan-sakartveloshi'}
MODEL_META = 'ua-seo-model'
ORDER = 'order'  # the custom-order page, in place of a model key
ORDER_SLUG = {'uk': 'avto-pid-zamovlennia-kyiv', 'ru': 'avto-pod-zakaz-kiev'}
JAPAN = 'japan'  # the Japan custom-order page, in place of a model key
JAPAN_SLUG = {'uk': 'avto-z-yaponii-pid-zamovlennia', 'ru': 'avto-iz-yaponii-pod-zakaz'}
# The order destinations the home page offers.
COUNTRIES = ('korea', 'japan', 'usa', 'europe', 'china')
STAGES = {1: ('У Кореї · викуплений і перевірений', 'В Корее · выкуплен и проверен'),
          2: ('На поромі · маршрут — Київ', 'На пароме · маршрут — Киев'),
          3: ('У Грузії · маршрут — Київ', 'В Грузии · маршрут — Киев'),
          4: ('У Києві · можна оглянути', 'В Киеве · можно посмотреть')}
T = {
    'uk': dict(home='Головна', catalog='Каталог', order='Підбір авто', terms='Умови', other='Русская версия',
               hub_title='Авто з Кореї під ключ у Києві — ціни та наявність | UA ART',
               hub_h1='Авто з Кореї під ключ у Києві',
               hub_desc='Автомобілі з Кореї під ключ у Києві: {n} авто в каталозі від {min} $. Ціна фіксується в договорі, депозит 500 $ входить у вартість. Фото, відео й діагностика кожного авто.',
               hub_intro='UA ART COMPANY купує автомобілі на аукціонах Кореї, перевіряє їх, доставляє через Грузію та передає в Києві. Зараз у каталозі {n} авто: від {min} до {max} $. Ціна в оголошенні — підсумкова, під ключ у Києві.',
               model_title='{model} з Кореї у Києві — ціни від {min} $ | UA ART',
               model_title_empty='{model} з Кореї під ключ у Києві | UA ART',
               model_h1='{model} з Кореї під ключ',
               model_desc='{model} з Кореї під ключ у Києві: {n} авто в каталозі, ціни від {min} до {max} $, роки {years}. Фото, відео, діагностика, доставка й розмитнення.',
               model_desc_empty='{model} з Кореї під ключ у Києві: підбір на аукціонах Кореї, перевірка, доставка й розмитнення. Залиште заявку на підбір.',
               model_intro='У каталозі UA ART зараз {n} {model}: ціни від {min} до {max} $, роки випуску {years}. Кожне авто має сторінку з фото, характеристиками, VIN і етапом доставки.',
               model_empty='Зараз {model} немає в каталозі. Залиште заявку — підберемо автомобіль на аукціонах Кореї під ваш бюджет.',
               cars='Автомобілі в каталозі', models='Моделі з Кореї', how='Як ми працюємо', versions='Покоління та двигуни',
               steps=('Підбираємо варіанти під ваш бюджет і перевіряємо історію та звіт аукціону.',
                      'Укладаємо договір; ціна фіксується в договорі, депозит 500 $ входить у вартість.',
                      'Викуп і підбір — від 3 до 10 днів, пором Корея → Грузія — близько 60 днів.',
                      'Грузія → Київ, розмитнення, сертифікація та видача — близько 15 днів.'),
               includes='У ціну входить: викуп на аукціоні, звіт і перевірка історії, доставка, розмитнення, сертифікація та всі платежі.',
               cta='Підібрати авто під замовлення', all_cars='Весь каталог', from_price='від {min} $',
               count='{n} авто', km='км', address='вул. Перемоги, 20, Київ', call='Подзвонити',
               order_title='Авто під замовлення в Києві — з Кореї, Японії, США, Європи, Китаю | UA ART',
               order_h1='Авто під замовлення в Києві',
               order_desc='Авто під замовлення з Кореї, Японії, США, Європи та Китаю з доставкою в Київ: підбір під бюджет, перевірка історії, доставка й розмитнення. Ціна фіксується в договорі, депозит 500 $ входить у вартість.',
               order_intro='UA ART COMPANY підбирає автомобілі під замовлення з Кореї, Японії, США, Європи та Китаю. Ви називаєте модель і бюджет — ми знаходимо варіанти, перевіряємо історію, викуповуємо, доставляємо, розмитнюємо й передаємо авто в Києві.',
               order_countries='Звідки замовити авто',
               country=dict(korea='Корея', japan='Японія', usa='США', europe='Європа', china='Китай'),
               order_korea='Найбільше зараз — з Кореї: у каталозі {n} авто від {min} до {max} $. Приклади:',
               order_link='Авто під замовлення з Кореї, Японії, США, Європи та Китаю',
               order_faq=(('Як замовити авто під замовлення?',
                           'Залиште заявку на підбір: модель, бюджет і країну. Ми підберемо варіанти, перевіримо історію та звіт аукціону, а після погодження укладемо договір; депозит 500 $ входить у вартість.'),
                          ('З яких країн можна замовити авто?',
                           'З Кореї, Японії, США, Європи та Китаю. Найбільше авто в нашому каталозі зараз — з Кореї.'),
                          ('Скільки триває доставка авто під замовлення?',
                           'Для Кореї: викуп і підбір — від 3 до 10 днів, пором Корея → Грузія — близько 60 днів, Грузія → Київ, розмитнення, сертифікація та видача — близько 15 днів. Для інших країн терміни називаємо під конкретний запит.'),
                          ('Що входить у ціну?',
                           'Викуп на аукціоні, звіт і перевірка історії, доставка, розмитнення, сертифікація та всі платежі.'),
                          ('Де подивитися приклади авто?',
                           'У каталозі: фото, відео, діагностика, VIN і етап доставки кожного авто. Ті, що вже в Києві, можна оглянути: вул. Перемоги, 20.')),
               faq_title='Часті питання',
               faq=(('Скільки коштує авто з Кореї під ключ у Києві?',
                     'Зараз у каталозі {n} авто від {min} до {max} $. Ціна в оголошенні — підсумкова: викуп на аукціоні, звіт і перевірка історії, доставка, розмитнення, сертифікація та всі платежі.'),
                    ('Скільки часу триває доставка з Кореї до Києва?',
                     'Викуп і підбір — від 3 до 10 днів, пором Корея → Грузія — близько 60 днів, Грузія → Київ, розмитнення, сертифікація та видача — близько 15 днів.'),
                    ('Як замовити авто з Кореї?',
                     'Підбираємо варіанти під ваш бюджет, перевіряємо історію та звіт аукціону й укладаємо договір. Ціна фіксується в договорі, депозит 500 $ входить у вартість.'),
                    ('Чи можна замовити модель, якої немає в каталозі?',
                     'Так. Залиште заявку на підбір — підберемо автомобіль на аукціонах Кореї під ваш бюджет.'),
                    ('Чи можна подивитися авто перед покупкою?',
                     'Кожне авто в каталозі має сторінку з фото, відео, діагностикою, характеристиками, VIN і етапом доставки. Авто, що вже в Києві, можна оглянути: вул. Перемоги, 20.'),
                    ('Де знаходиться UA ART COMPANY?',
                     'Київ, вул. Перемоги, 20. Телефон +380 99 222 20 02.'))),
    'ru': dict(home='Главная', catalog='Каталог', order='Подбор авто', terms='Условия', other='Українська версія',
               hub_title='Авто из Кореи под ключ в Киеве — цены и наличие | UA ART',
               hub_h1='Авто из Кореи под ключ в Киеве',
               hub_desc='Автомобили из Кореи под ключ в Киеве: {n} авто в каталоге от {min} $. Цена фиксируется в договоре, депозит 500 $ входит в стоимость. Фото, видео и диагностика каждого авто.',
               hub_intro='UA ART COMPANY покупает автомобили на аукционах Кореи, проверяет их, доставляет через Грузию и передаёт в Киеве. Сейчас в каталоге {n} авто: от {min} до {max} $. Цена в объявлении — итоговая, под ключ в Киеве.',
               model_title='{model} из Кореи в Киеве — цены от {min} $ | UA ART',
               model_title_empty='{model} из Кореи под ключ в Киеве | UA ART',
               model_h1='{model} из Кореи под ключ',
               model_desc='{model} из Кореи под ключ в Киеве: {n} авто в каталоге, цены от {min} до {max} $, годы {years}. Фото, видео, диагностика, доставка и растаможка.',
               model_desc_empty='{model} из Кореи под ключ в Киеве: подбор на аукционах Кореи, проверка, доставка и растаможка. Оставьте заявку на подбор.',
               model_intro='В каталоге UA ART сейчас {n} {model}: цены от {min} до {max} $, годы выпуска {years}. У каждого авто есть страница с фото, характеристиками, VIN и этапом доставки.',
               model_empty='Сейчас {model} нет в каталоге. Оставьте заявку — подберём автомобиль на аукционах Кореи под ваш бюджет.',
               cars='Автомобили в каталоге', models='Модели из Кореи', how='Как мы работаем', versions='Поколения и двигатели',
               steps=('Подбираем варианты под ваш бюджет и проверяем историю и отчёт аукциона.',
                      'Заключаем договор; цена фиксируется в договоре, депозит 500 $ входит в стоимость.',
                      'Выкуп и подбор — от 3 до 10 дней, паром Корея → Грузия — около 60 дней.',
                      'Грузия → Киев, растаможка, сертификация и выдача — около 15 дней.'),
               includes='В цену входит: выкуп на аукционе, отчёт и проверка истории, доставка, растаможка, сертификация и все платежи.',
               cta='Подобрать авто под заказ', all_cars='Весь каталог', from_price='от {min} $',
               count='{n} авто', km='км', address='ул. Победы 20, Киев', call='Позвонить',
               order_title='Авто под заказ в Киеве — из Кореи, Японии, США, Европы, Китая | UA ART',
               order_h1='Авто под заказ в Киеве',
               order_desc='Авто под заказ из Кореи, Японии, США, Европы и Китая с доставкой в Киев: подбор под бюджет, проверка истории, доставка и растаможка. Цена фиксируется в договоре, депозит 500 $ входит в стоимость.',
               order_intro='UA ART COMPANY подбирает автомобили под заказ из Кореи, Японии, США, Европы и Китая. Вы называете модель и бюджет — мы находим варианты, проверяем историю, выкупаем, доставляем, растаможиваем и передаём авто в Киеве.',
               order_countries='Откуда заказать авто',
               country=dict(korea='Корея', japan='Япония', usa='США', europe='Европа', china='Китай'),
               order_korea='Больше всего сейчас — из Кореи: в каталоге {n} авто от {min} до {max} $. Примеры:',
               order_link='Авто под заказ из Кореи, Японии, США, Европы и Китая',
               order_faq=(('Как заказать авто под заказ?',
                           'Оставьте заявку на подбор: модель, бюджет и страну. Мы подберём варианты, проверим историю и отчёт аукциона, а после согласования заключим договор; депозит 500 $ входит в стоимость.'),
                          ('Из каких стран можно заказать авто?',
                           'Из Кореи, Японии, США, Европы и Китая. Больше всего авто в нашем каталоге сейчас — из Кореи.'),
                          ('Сколько длится доставка авто под заказ?',
                           'Для Кореи: выкуп и подбор — от 3 до 10 дней, паром Корея → Грузия — около 60 дней, Грузия → Киев, растаможка, сертификация и выдача — около 15 дней. Для других стран сроки называем под конкретный запрос.'),
                          ('Что входит в цену?',
                           'Выкуп на аукционе, отчёт и проверка истории, доставка, растаможка, сертификация и все платежи.'),
                          ('Где посмотреть примеры авто?',
                           'В каталоге: фото, видео, диагностика, VIN и этап доставки каждого авто. Те, что уже в Киеве, можно осмотреть: ул. Победы 20.')),
               faq_title='Частые вопросы',
               faq=(('Сколько стоит авто из Кореи под ключ в Киеве?',
                     'Сейчас в каталоге {n} авто от {min} до {max} $. Цена в объявлении — итоговая: выкуп на аукционе, отчёт и проверка истории, доставка, растаможка, сертификация и все платежи.'),
                    ('Сколько времени занимает доставка из Кореи в Киев?',
                     'Выкуп и подбор — от 3 до 10 дней, паром Корея → Грузия — около 60 дней, Грузия → Киев, растаможка, сертификация и выдача — около 15 дней.'),
                    ('Как заказать авто из Кореи?',
                     'Подбираем варианты под ваш бюджет, проверяем историю и отчёт аукциона и заключаем договор. Цена фиксируется в договоре, депозит 500 $ входит в стоимость.'),
                    ('Можно ли заказать модель, которой нет в каталоге?',
                     'Да. Оставьте заявку на подбор — подберём автомобиль на аукционах Кореи под ваш бюджет.'),
                    ('Можно ли посмотреть авто перед покупкой?',
                     'У каждого авто в каталоге есть страница с фото, видео, диагностикой, характеристиками, VIN и этапом доставки. Авто, которые уже в Киеве, можно осмотреть: ул. Победы 20.'),
                    ('Где находится UA ART COMPANY?',
                     'Киев, ул. Победы 20. Телефон +380 99 222 20 02.'))),
}
CSS = ('body{margin:0;background:#0B1524;color:#e8eef8;font:16px/1.55 system-ui,-apple-system,Segoe UI,Arial,sans-serif}'
       'a{color:#f4b65c}main,header,footer{max-width:1040px;margin:0 auto;padding:0 16px}'
       'header nav{display:flex;flex-wrap:wrap;gap:14px;padding:16px 0;font-size:15px}'
       'h1{font-size:30px;line-height:1.2;margin:8px 0 12px}h2{font-size:22px;margin:28px 0 12px}h3{font-size:17px;margin:18px 0 6px}'
       '.cars{list-style:none;padding:0;display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(240px,1fr))}'
       '.cars li{background:#0f2137;border:1px solid rgba(240,166,60,.25);border-radius:16px;overflow:hidden}'
       '.cars a{color:inherit;text-decoration:none;display:block}.cars img{display:block;width:100%;aspect-ratio:16/10;object-fit:cover;background:#0B1524}'
       '.cars div{padding:12px 14px}.cars b{display:block;font-size:17px}.price{display:block;color:#f0a63c;font-weight:800;font-size:18px}'
       '.muted{color:#aebed0;font-size:14px}.models{display:flex;flex-wrap:wrap;gap:10px;padding:0;list-style:none}'
       '.models a{display:block;padding:9px 14px;border:1px solid rgba(240,166,60,.45);border-radius:12px;text-decoration:none}'
       '.cta{display:inline-block;margin:18px 0;padding:14px 20px;border-radius:14px;background:#f0a63c;color:#10161f;font-weight:800;text-decoration:none}'
       'footer{padding:28px 16px 40px;color:#aebed0;font-size:14px}')


def slug(value):
    return re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')


def model_name(key):
    return '%s %s' % key


def path(lang, key=None):
    if key == ORDER:
        name = ORDER_SLUG[lang]
    elif key == JAPAN:
        name = JAPAN_SLUG[lang]
    else:
        name = HUB[lang] if key is None else '%s-%s-%s' % (slug(key[0]), slug(key[1]), MODEL_SUFFIX[lang])
    return 'seo/%s/%s.html' % (DIRS[lang], name)


def url(relative):
    return '%s/video/%s' % (ORIGIN, relative)


def money(value):
    return '{:,}'.format(value).replace(',', ' ')


def _years(cars):
    years = sorted({int(m.group(0)) for c in cars for m in [re.search(r'(19|20)[0-9]{2}$', c['name'])] if m})
    if not years:
        return ''
    return str(years[0]) if years[0] == years[-1] else '%d–%d' % (years[0], years[-1])


def _prices(cars):
    prices = [c['price_usd'] for c in cars if c.get('price_usd')]
    return (money(min(prices)), money(max(prices))) if prices else (None, None)


def _alternates(key, existing):
    links = [(lang, path(lang, key)) for lang in LANGS]
    ka = 'seo/gu/%s.html' % (HUB['ka'] if key is None else '%s-%s-%s' % (slug(key[0]), slug(key[1]), MODEL_SUFFIX['ka']))
    if ka in existing and key not in (ORDER, JAPAN):
        links.append(('ka', ka))
    links.append(('x-default', path('uk', key)))
    return ''.join('<link rel="alternate" hreflang="%s" href="%s">' % (lang, url(rel)) for lang, rel in links)


def _car_list(cars, lang):
    t = T[lang]
    items = []
    for i, c in enumerate(cars):
        stage = STAGES.get(c.get('stage'))
        details = ' · '.join(x for x in (
            ('%s %s' % (money(c['mileage_km']), t['km'])) if c.get('mileage_km') is not None else '',
            stage[LANGS.index(lang)] if stage else '') if x)
        image = ('<img src="%s" alt="%s" loading="%s" decoding="async">' % (
            escape(c['image']), escape(c['name']), 'eager' if i == 0 else 'lazy')) if c.get('image') else ''
        price = '<span class="price">%s $</span>' % money(c['price_usd']) if c.get('price_usd') else ''
        items.append('<li><a href="%s">%s<div><b>%s</b>%s<span class="muted">%s</span></div></a></li>' % (
            escape(c['url']), image, escape(c['name']), price, escape(details)))
    return '<ul class="cars">%s</ul>' % ''.join(items)


def _model_links(groups, lang, current=None):
    t = T[lang]
    items = []
    for key in sorted(groups):
        if key == current:
            continue
        low = _prices(groups[key])[0]
        label = model_name(key) + (' — ' + t['from_price'].format(min=low) if low else '')
        items.append('<li><a href="/video/%s">%s</a></li>' % (path(lang, key), escape(label)))
    return '<ul class="models">%s</ul>' % ''.join(items) if items else ''


def _page(lang, key, title, description, h1, body, ld, existing):
    t = T[lang]
    other = LANGS[1 - LANGS.index(lang)]
    meta = '<meta name="%s" content="%s">' % (MODEL_META, escape('|'.join(key))) if isinstance(key, tuple) else ''
    nav = ('<a href="/video/index.html">{home}</a><a href="/video/katalog.html">{catalog}</a>'
           '<a href="/video/podbor.html">{order}</a><a href="/video/info.html">{terms}</a>'
           '<a href="/video/%s" hreflang="%s" lang="%s">{other}</a>' % (path(other, key), other, other)).format(**t)
    footer = ('UA ART COMPANY · %s · <a href="tel:%s">+380 99 222 20 02</a> · '
              '<a href="%s">Google Maps</a>' % (escape(t['address']), schema.PHONE, schema.MAP))
    return ('<!doctype html><html lang="%s"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>%s</title><meta name="description" content="%s">%s'
            '<link rel="canonical" href="%s">%s'
            '<meta property="og:type" content="website"><meta property="og:title" content="%s">'
            '<meta property="og:description" content="%s"><meta property="og:url" content="%s">'
            '<link rel="icon" href="/video/brand/ua-art/favicon.ico">'
            '<style>%s</style>%s</head><body><header><nav>%s</nav></header><main><h1>%s</h1>%s</main>'
            '<footer>%s</footer></body></html>\n') % (
        lang, escape(title), escape(description, quote=True), meta, url(path(lang, key)),
        _alternates(key, existing), escape(title, quote=True), escape(description, quote=True),
        url(path(lang, key)), CSS, ld, nav, escape(h1), body, footer)


def _process(lang):
    t = T[lang]
    return '<h2>%s</h2><ol>%s</ol><p>%s</p><a class="cta" href="/video/podbor.html">%s</a>' % (
        t['how'], ''.join('<li>%s</li>' % escape(s) for s in t['steps']), escape(t['includes']), escape(t['cta']))


def _faq(lang, fill):
    t = T[lang]
    pairs = [(q, a.format(**fill)) for q, a in t['faq']]
    if not fill['n']:
        pairs = pairs[1:]  # no price range without cars in the catalog
    html = '<h2>%s</h2>%s' % (t['faq_title'], ''.join('<h3>%s</h3><p>%s</p>' % (escape(q), escape(a)) for q, a in pairs))
    return html, schema.faq(pairs)


def hub(lang, cars, groups, existing):
    t = T[lang]
    low, high = _prices(cars)
    fill = dict(n=len(cars), min=low or '—', max=high or '—')
    faq_html, faq_ld = _faq(lang, fill)
    body = ('<p>%s</p><h2>%s</h2>%s<h2>%s</h2>%s<p><a href="/video/katalog.html">%s</a></p>%s%s' % (
        escape(t['hub_intro'].format(**fill)), t['models'], _model_links(groups, lang),
        t['cars'], _car_list(cars, lang), t['all_cars'], _process(lang), faq_html))
    body += '<p><a href="/video/%s">%s</a></p>' % (path(lang, ORDER), escape(t['order_link']))
    ld = schema.script(schema.dealer(lang),
                       schema.breadcrumbs([(t['home'], ORIGIN + '/video/index.html'), (t['hub_h1'], url(path(lang)))]),
                       schema.item_list(cars), faq_ld)
    return _page(lang, None, t['hub_title'], t['hub_desc'].format(**fill), t['hub_h1'], body, ld, existing)


def order(lang, cars, existing):
    t = T[lang]
    low, high = _prices(cars)
    fill = dict(n=len(cars), min=low or '—', max=high or '—')
    countries = ''.join('<li><a href="/video/podbor.html?strana=%s&amp;lang=%s">%s</a></li>' % (c, lang, escape(t['country'][c]))
                        for c in COUNTRIES)
    examples = '<p>%s</p>%s' % (escape(t['order_korea'].format(**fill)), _car_list(cars[:6], lang)) if cars else ''
    pairs = [(q, a) for q, a in t['order_faq']]
    body = ('<p>%s</p><h2>%s</h2><ul class="models">%s</ul><p><a href="/video/%s">%s</a></p>%s%s<h2>%s</h2>%s'
            '<p><a href="/video/%s">%s</a></p>' % (
        escape(t['order_intro']), t['order_countries'], countries, path(lang, JAPAN),
        escape(order_models.JAPAN[lang]['link']), examples, _process(lang), t['faq_title'],
        ''.join('<h3>%s</h3><p>%s</p>' % (escape(q), escape(a)) for q, a in pairs), path(lang), escape(t['hub_h1'])))
    ld = schema.script(schema.dealer(lang),
                       schema.breadcrumbs([(t['home'], ORIGIN + '/video/index.html'), (t['order_h1'], url(path(lang, ORDER)))]),
                       schema.faq(pairs))
    return _page(lang, ORDER, t['order_title'], t['order_desc'], t['order_h1'], body, ld, existing)


def model(lang, key, cars, groups, existing):
    t = T[lang]
    name = model_name(key)
    low, high = _prices(cars)
    fill = dict(model=name, n=len(cars), min=low, max=high, years=_years(cars))
    texts = order_models.KOREA.get(key, {}).get(lang)
    if cars and low:
        title, description = t['model_title'].format(**fill), t['model_desc'].format(**fill)
        intro = t['model_intro'].format(**fill)
    else:
        title, description = t['model_title_empty'].format(**fill), t['model_desc_empty'].format(**fill)
        intro = t['model_empty'].format(**fill)
        if texts:
            description = texts['desc']
    lead, about, faq_html = '', '', ''
    if texts:  # the model itself first, then the catalog state
        lead = '<p>%s</p>' % escape(texts['about'])
        about = '<h2>%s</h2><ul>%s</ul>' % (t['versions'], ''.join('<li>%s</li>' % escape(v) for v in texts['versions']))
        faq_html = '<h2>%s</h2>%s' % (t['faq_title'], ''.join(
            '<h3>%s</h3><p>%s</p>' % (escape(q), escape(a)) for q, a in texts['faq']))
    others = _model_links(groups, lang, key)
    body = '%s<p>%s</p>%s%s%s%s%s<p><a href="/video/%s">%s</a></p>' % (
        lead, escape(intro), about, ('<h2>%s</h2>%s' % (t['cars'], _car_list(cars, lang))) if cars else '',
        _process(lang), faq_html, ('<h2>%s</h2>%s' % (t['models'], others)) if others else '',
        path(lang), escape(t['hub_h1']))
    h1 = t['model_h1'].format(**fill)
    nodes = [schema.breadcrumbs([(t['home'], ORIGIN + '/video/index.html'), (t['hub_h1'], url(path(lang))),
                                 (h1, url(path(lang, key)))])]
    if cars:
        nodes.append(schema.item_list(cars))
    if texts:
        nodes.append(schema.faq(list(texts['faq'])))
    return _page(lang, key, title, description, h1, body, schema.script(*nodes), existing)


def japan(lang, existing):
    t, j = T[lang], order_models.JAPAN[lang]
    models = ''.join('<h3>%s</h3><p>%s</p>' % (escape(name), escape(text)) for name, text in j['models'])
    steps = ''.join('<li>%s</li>' % escape(s) for s in j['steps'])
    body = ('<p>%s</p><h2>%s</h2>%s<p>%s</p><h2>%s</h2><ol>%s</ol><p>%s</p>'
            '<a class="cta" href="/video/podbor.html?strana=japan&amp;lang=%s">%s</a><h2>%s</h2>%s'
            '<p><a href="/video/%s">%s</a></p>') % (
        escape(j['intro']), escape(j['models_title']), models, escape(j['other']), t['how'], steps,
        escape(t['includes']), lang, escape(j['cta']), t['faq_title'],
        ''.join('<h3>%s</h3><p>%s</p>' % (escape(q), escape(a)) for q, a in j['faq']),
        path(lang, ORDER), escape(t['order_h1']))
    ld = schema.script(schema.dealer(lang),
                       schema.breadcrumbs([(t['home'], ORIGIN + '/video/index.html'),
                                           (t['order_h1'], url(path(lang, ORDER))), (j['h1'], url(path(lang, JAPAN)))]),
                       schema.faq(list(j['faq'])))
    return _page(lang, JAPAN, j['title'], j['desc'], j['h1'], body, ld, existing)


def pages(cars, kept_keys=(), existing=frozenset()):
    """All landing pages. kept_keys: models whose page already exists and must stay."""
    groups = {}
    for c in cars:
        if c.get('key'):
            groups.setdefault(c['key'], []).append(c)
    keys = set(groups) | {tuple(k) for k in kept_keys} | set(order_models.KOREA)
    for key in keys:
        groups.setdefault(key, [])
    listed = {k: v for k, v in groups.items() if v or k in order_models.KOREA}
    result = {}
    for lang in LANGS:
        result[path(lang)] = hub(lang, cars, listed, existing)
        result[path(lang, ORDER)] = order(lang, cars, existing)
        result[path(lang, JAPAN)] = japan(lang, existing)
        for key in sorted(keys):
            result[path(lang, key)] = model(lang, key, groups[key], listed, existing)
    return result
