"""New home page order (HOME-LAYOUT-001): custom order first, then strengths, steps, stages.

The custom-order block becomes the first screen (owner photo, 8 countries, two buttons),
a short "how we work" block follows the strengths strip, Telegram and Viber join the
header contacts. Stage cards, counters, scripts and the head stay byte for byte.
"""
import re

MARK = 'ua-home-layout-001'
TELEGRAM = 'https://t.me/UA_artcompany_LLC_bot'
VIBER = 'viber://chat?number=%2B380992222002'
DESKTOP = '/video/order/hero/kia_k5_desktop.webp'
MOBILE = '/video/order/hero/kia_k5_mobile.webp'

HERO = re.compile(r'<section class="hero hero-main"[^>]*>.*?</section>', re.S)
ORDER = re.compile(r'<section class="order-feature section-frame">.*?</section>', re.S)
COUNTRIES = re.compile(r'<nav class="countries-inline ua-order-inline".*?</nav>', re.S)
PRICE = re.compile(r'<div class="fixed-price">.*?</div>', re.S)
STRIP = re.compile(r'<section class="confidence-strip[^>]*>.*?</section>', re.S)
WHATSAPP = re.compile(r'<a class="header-whatsapp"[^>]*>WhatsApp</a>')

STEPS = (
    ('Заявка', 'Заявка', 'განაცხადი',
     'Расскажите бюджет и пожелания', 'Розкажіть бюджет і побажання', 'გვითხარით ბიუჯეტი და სურვილები'),
    ('Подбор и проверка', 'Підбір і перевірка', 'შერჩევა და შემოწმება',
     'Фото, видео и OBD-диагностика', 'Фото, відео та OBD-діагностика', 'ფოტო, ვიდეო და OBD დიაგნოსტიკა'),
    ('Договор', 'Договір', 'ხელშეკრულება',
     'Цена фиксируется до покупки', 'Ціна фіксується до купівлі', 'ფასი ფიქსირდება შეძენამდე'),
    ('Доставка', 'Доставка', 'მიწოდება',
     'Маршрут и дата онлайн', 'Маршрут і дата онлайн', 'მარშრუტი და თარიღი ონლაინ'),
    ('Растаможка и выдача', 'Розмитнення і видача', 'განბაჟება და გადაცემა',
     'В Киеве, с сопровождением', 'У Києві, з супроводом', 'კიევში, თანხლებით'),
)

CSS = '''<style id="%s">
.ua-order-first{display:grid;grid-template-columns:46%% 54%%;border-bottom:1px solid var(--line)}
.ua-order-first>picture{grid-column:2;grid-row:1;position:relative;display:block;min-height:100%%}
.ua-order-first>picture img{position:absolute;inset:0;width:100%%;height:100%%;object-fit:cover;object-position:center}
.ua-order-shade{grid-column:2;grid-row:1;z-index:1;background:linear-gradient(90deg,rgba(6,15,27,1) 0%%,rgba(6,15,27,.3) 22%%,rgba(6,15,27,0) 45%%)}
.ua-order-copy{grid-column:1;grid-row:1;position:relative;z-index:2;padding:34px 26px 34px 35px;display:grid;gap:14px;align-content:center}
.ua-order-copy h1{margin:0;font-size:clamp(34px,3.6vw,48px);line-height:1.04;letter-spacing:-1.4px}
.ua-order-copy p{margin:0;color:#c1ccda;font-size:17px;line-height:1.5}
.ua-order-copy .countries-inline{padding:2px 0 0;border:0;font-size:13px}
.ua-order-copy .ua-order-inline a{min-height:74px;gap:6px;padding:8px 3px}
.ua-order-copy .ua-order-inline img{width:40px;height:27px}
.ua-order-copy .fixed-price{font-size:14px}
.ua-order-actions{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.ua-order-actions .button{min-height:50px;width:auto}
.ua-order-actions .ua-write{border:1px solid #4b6a8c;color:#dce4ef}
.ua-how ol{list-style:none;margin:18px 0 0;padding:0;display:grid;grid-template-columns:repeat(5,1fr);gap:10px}
.ua-how li{padding:16px 14px;border:1px solid #314862;border-radius:14px;background:rgba(7,17,30,.6)}
.ua-how li b{display:block;margin:8px 0 4px;font-size:15px}
.ua-how li small{color:#9fb0c4;font-size:12px;line-height:1.45}
.ua-how li i{font-style:normal;color:var(--gold);font-weight:800}
.header-contacts{grid-template-columns:1.45fr .72fr .72fr .72fr 1fr}
.header-telegram{color:#5fb8f0!important;font-weight:700}
.header-viber{color:#a78bfa!important;font-weight:700}
@media (max-width:700px){
.ua-order-first{display:block}
.ua-order-first>picture{aspect-ratio:16/9;min-height:0}
.ua-order-first>picture img{object-position:center 62%%}
.ua-order-shade{display:none}
.ua-order-copy{padding:20px 16px 26px;gap:13px}
.ua-order-copy h1{font-size:32px}
.ua-order-copy p{font-size:14px}
.ua-order-copy .countries-inline,.ua-order-copy .fixed-price{width:auto;font-size:12px}
.ua-order-actions .button{min-height:48px;font-size:14px;padding:0 8px}
.ua-how ol{grid-template-columns:1fr}
.ua-how li{display:grid;grid-template-columns:28px 1fr;column-gap:8px;padding:12px 14px}
.ua-how li i{grid-row:span 2}
.ua-how li b{margin:0 0 2px}
.header-contacts{grid-template-columns:repeat(3,1fr)}
.header-contacts .header-phone{grid-column:span 2;border-right:1px solid #314862!important}
.header-contacts .header-map{grid-row:1;grid-column:3;border-bottom:1px solid #314862;border-right:0!important}
.header-contacts .header-viber{border-right:0!important}
}
</style>''' % MARK


def _one(pattern, text, name):
    found = pattern.findall(text)
    if len(found) != 1:
        raise ValueError('HOME_%s:%d' % (name, len(found)))
    return found[0]


def _attrs(ru, uk, ka):
    return 'data-ru="%s" data-uk="%s" data-ka="%s">%s' % (ru, uk, ka, uk)


def hero(countries, price):
    return (
        '<section class="hero ua-order-first">'
        '<picture><source media="(max-width:700px)" srcset="%s" type="image/webp">'
        '<img src="%s" alt="Kia K5 — UA ART COMPANY, Київ" width="1400" height="868" fetchpriority="high" decoding="async">'
        '</picture><div class="ua-order-shade"></div><div class="ua-order-copy">'
        '<span class="eyebrow" %s</span>'
        '<h1><span %s</span><br><span %s</span></h1>'
        '<p %s</p>%s%s<div class="ua-order-actions">'
        '<a class="button gold" href="podbor.html" %s</a>'
        '<a class="button ua-write" href="%s" target="_blank" rel="noopener noreferrer" %s</a>'
        '</div></div></section>'
    ) % (MOBILE, DESKTOP,
         _attrs('АВТО ПОД ЗАКАЗ · КИЕВ', 'АВТО ПІД ЗАМОВЛЕННЯ · КИЇВ', 'ავტომობილი შეკვეთით · კიევი'),
         _attrs('Авто под заказ', 'Авто під замовлення', 'ავტომობილი შეკვეთით'),
         _attrs('под ключ в Киеве', 'під ключ у Києві', 'სრული მომსახურებით კიევში'),
         _attrs('Подберём автомобиль под ваш бюджет и пожелания', 'Підберемо автомобіль під ваш бюджет і побажання',
                'შეგირჩევთ ავტომობილს თქვენი ბიუჯეტისა და სურვილების შესაბამისად'),
         countries, price,
         _attrs('Подобрать авто', 'Підібрати авто', 'ავტომობილის შერჩევა'),
         TELEGRAM, _attrs('Написать в Telegram', 'Написати в Telegram', 'მოგვწერეთ Telegram-ში'))


def steps():
    items = ''.join('<li><i>%d</i><b %s</b><small %s</small></li>' % (n, _attrs(*step[:3]), _attrs(*step[3:]))
                    for n, step in enumerate(STEPS, 1))
    return ('<section class="ua-how section-frame"><span class="section-kicker" %s</span><h2 %s</h2><ol>%s</ol></section>'
            % (_attrs('КАК МЫ РАБОТАЕМ', 'ЯК МИ ПРАЦЮЄМО', 'როგორ ვმუშაობთ'),
               _attrs('5 шагов до вашего авто', '5 кроків до вашого авто', '5 ნაბიჯი თქვენს ავტომობილამდე'), items))


def messengers():
    return ('<a class="header-telegram" href="%s" target="_blank" rel="noopener noreferrer">Telegram</a>'
            '<a class="header-viber" href="%s">Viber</a>' % (TELEGRAM, VIBER))


def build(source):
    text = source.decode('utf-8')
    if MARK in text:
        raise ValueError('HOME_ALREADY_CHANGED')
    old_hero = _one(HERO, text, 'HERO')
    order = _one(ORDER, text, 'ORDER')
    strip = _one(STRIP, text, 'STRIP')
    whatsapp = _one(WHATSAPP, text, 'WHATSAPP')
    if len(re.findall(r'</head\s*>', text, re.I)) != 1:
        raise ValueError('HOME_HEAD')
    countries = _one(COUNTRIES, order, 'COUNTRIES')
    price = _one(PRICE, order, 'PRICE')
    text = text.replace(order, '', 1)
    text = text.replace(old_hero, hero(countries, price), 1)
    text = text.replace(strip, strip + steps(), 1)
    text = text.replace(whatsapp, whatsapp + messengers(), 1)
    text = re.sub(r'</head\s*>', lambda m: CSS + m.group(), text, count=1, flags=re.I)
    return text.encode('utf-8')
