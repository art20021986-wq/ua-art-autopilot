"""The Japan auction page video/japan.html, made from the live video/korea.html (JAPAN-LHD-001, owner 2026-11-27 «Да» to
cloud/photos/41-JAPAN-LHD-mockup-v2.png: «as Korea, left-hand drive only»).

Same site chrome, lot list, filters and lot card; the Japan texts, the Japan lot list (/video/japan/lots.json), the
start price in yen and Japan time. Left out, as Korea-only: the client login and the online bid in won (the CRM bids are
Korea's), the Korea auction houses, «Чому аукціон вигідніше» (Hyundai, Kia, Genesis) and the FAQ (the Korea ferry
times); a lot card's button is «Зв'язатися з менеджером» (lead with country japan and the lot). Only one Russian page
exists for Korea, so the Japan page has its own language switch only (uk/ru/ka in place), without a ru/ address.
Every edit must match the expected number of times, else the build stops; every other byte stays.
"""
KOREA_URL = 'https://www.uaart.com.ua/video/korea.html'
JAPAN_URL = 'https://www.uaart.com.ua/video/japan.html'

TEXTS = (
    # title, og:title (uk twice: text and data-uk), description, og:description
    ('Аукціони Кореї онлайн — UA ART COMPANY', 'Аукціони Японії онлайн — авто з лівим кермом — UA ART COMPANY', 4),
    ('Аукционы Кореи онлайн — UA ART COMPANY', 'Аукционы Японии онлайн — авто с левым рулём — UA ART COMPANY', 2),
    ('კორეის აუქციონები ონლაინ — UA ART COMPANY', 'იაპონიის აუქციონები ონლაინ — მარცხენასაჭიანი ავტომობილები — UA ART COMPANY', 2),
    ('Обирайте авто на аукціонах Кореї онлайн разом з UA ART COMPANY: тисячі лотів щотижня, оцінка стану, пробіг і '
     'стартова ціна. Передоплата 1 000 $ зараховується у вартість авто.',
     'Обирайте авто з лівим кермом на аукціонах Японії онлайн разом з UA ART COMPANY: фото, оцінка стану, пробіг і '
     'стартова ціна. Передоплата 1 000 $ зараховується у вартість авто.', 4),
    ('Выбирайте авто на аукционах Кореи онлайн вместе с UA ART COMPANY: тысячи лотов каждую неделю, оценка состояния, '
     'пробег и стартовая цена. Предоплата 1 000 $ засчитывается в стоимость авто.',
     'Выбирайте авто с левым рулём на аукционах Японии онлайн вместе с UA ART COMPANY: фото, оценка состояния, пробег '
     'и стартовая цена. Предоплата 1 000 $ засчитывается в стоимость авто.', 2),
    ('აირჩიეთ ავტომობილი კორეის აუქციონებზე ონლაინ UA ART COMPANY-სთან ერთად: ათასობით ლოტი ყოველკვირა. წინასწარი '
     'გადახდა 1 000 $ ჩაითვლება ავტომობილის ღირებულებაში.',
     'აირჩიეთ მარცხენასაჭიანი ავტომობილი იაპონიის აუქციონებზე ონლაინ UA ART COMPANY-სთან ერთად. წინასწარი გადახდა '
     '1 000 $ ჩაითვლება ავტომობილის ღირებულებაში.', 2),
    # the hero
    ('АУКЦІОНИ КОРЕЇ · ОНЛАЙН', 'АУКЦІОНИ ЯПОНІЇ · ОНЛАЙН', 2),
    ('АУКЦИОНЫ КОРЕИ · ОНЛАЙН', 'АУКЦИОНЫ ЯПОНИИ · ОНЛАЙН', 1),
    ('კორეის აუქციონები · ონლაინ', 'იაპონიის აუქციონები · ონლაინ', 1),
    ('Обирайте авто на аукціонах Кореї — онлайн, разом з нами', 'Обирайте авто на аукціонах Японії — тільки з лівим кермом', 2),
    ('Выбирайте авто на аукционах Кореи — онлайн, вместе с нами', 'Выбирайте авто на аукционах Японии — только с левым рулём', 1),
    ('აირჩიეთ ავტომობილი კორეის აუქციონებზე — ონლაინ, ჩვენთან ერთად',
     'აირჩიეთ ავტომობილი იაპონიის აუქციონებზე — მხოლოდ მარცხენა საჭით', 1),
    ('Тисячі авто на торгах щотижня.', 'Щотижня — авто з лівим кермом з аукціонів Японії.', 2),
    ('Тысячи авто на торгах каждую неделю.', 'Каждую неделю — авто с левым рулём с аукционов Японии.', 1),
    ('ათასობით ავტომობილი ვაჭრობაზე ყოველკვირა.', 'ყოველკვირა — მარცხენასაჭიანი ავტომობილები იაპონიის აუქციონებიდან.', 1),
    ('Аукціони онлайн: зараз — Корея. Незабаром — Японія та інші країни.', 'Японія: показуємо лише авто з лівим кермом.', 2),
    ('Аукционы онлайн: сейчас — Корея. Скоро — Япония и другие страны.', 'Япония: показываем только авто с левым рулём.', 1),
    ('ონლაინ აუქციონები: ახლა — კორეა. მალე — იაპონია და სხვა ქვეყნები.',
     'იაპონია: ვაჩვენებთ მხოლოდ მარცხენასაჭიან ავტომობილებს.', 1),
    # «two ways to buy» and the lot list note
    ('на торгах Кореї та суму ставки', 'на торгах Японії та суму ставки', 2),
    ('на торгах Кореи и сумму ставки', 'на торгах Японии и сумму ставки', 1),
    ('კორეის ვაჭრობაზე და ფსონს', 'იაპონიის ვაჭრობაზე და ფსონს', 1),
    ('Ціни — стартові в Кореї.', 'Ціни — стартові в Японії.', 2),
    ('Цены — стартовые в Корее.', 'Цены — стартовые в Японии.', 1),
    ('ფასები — საწყისი კორეაში.', 'ფასები — საწყისი იაპონიაში.', 1),
)
CODE = (
    # addresses: the page's own (canonical, og:url, hreflang uk and x-default); no Russian address for Japan
    ('<link rel="alternate" hreflang="ru" href="https://www.uaart.com.ua/video/ru/korea.html">', '', 1),
    (KOREA_URL, JAPAN_URL, 4),
    # the lot list, its galleries, the lead button's country, the yen price, the time zone name, no Korea holidays
    ('fetch("/video/korea/lots.json",{cache:"no-cache"}).then(function(r){return r.ok?r.json():{lots:[]};})',
     'fetch("/video/japan/lots.json",{cache:"no-cache"}).then(function(r){return r.ok?r.json():{lots:[]};})', 1),
    ("fetch('/video/korea/gallery/' + encodeURIComponent(id)", "fetch('/video/japan/gallery/' + encodeURIComponent(id)", 1),
    ('data-quick-lead-auction="korea"', 'data-quick-lead-auction="japan"', 2),
    ('" <small>(₩"+n(l.start_krw)+")</small>"', '" <small>(¥"+n(l.start_jpy)+")</small>"', 1),
    ('var ZN=[["Корея","Київ"],["Корея","Киев"],["კორეა","კიევი"]];',
     'var ZN=[["Японія","Київ"],["Япония","Киев"],["იაპონია","კიევი"]];', 1),
)
# Korea-only blocks, cut whole: (first bytes, last bytes)
CUTS = (
    ('<!--UA-KOREA-LOGIN-V1-->', '<!--/UA-KOREA-LOGIN-V1-->'),
    ('<!--UA-KOREA-BID-V1-->', '<!--/UA-KOREA-BID-V1-->'),
    ('<section class="kr-sec"><h2><span data-uk="Аукціони, до яких', '<!--/UA-KOREA-FAQ-V1-->'),
    ('<span class="kr-live">● <span data-uk="Торги щодня з понеділка по п\'ятницю"', '</span></span>'),
)
HOLIDAYS = 'var HOL={'  # the Korea page's holiday list (Korea holidays): Japan has none of them


def _cut(text, first, last):
    start = text.find(first)
    end = text.find(last, start)
    if text.count(first) != 1 or start < 0 or end < 0:
        raise ValueError('JAPAN_PAGE_CUT:' + first[:40])
    return text[:start] + text[end + len(last):]


def _holidays(text):
    start = text.find(HOLIDAYS)
    end = text.find('};', start)
    if text.count(HOLIDAYS) != 1 or end < 0:
        raise ValueError('JAPAN_PAGE_HOLIDAYS')
    return text[:start] + 'var HOL={};' + text[end + 2:]


CHECK = '/video/japan/lots.json'  # public proof that the page is the Japan page


def build(korea):
    """video/korea.html bytes -> video/japan.html bytes."""
    text = korea.decode('utf-8')
    if CHECK in text:
        raise ValueError('JAPAN_PAGE_SOURCE_IS_JAPAN')
    for first, last in CUTS:
        text = _cut(text, first, last)
    for old, new, count in TEXTS + CODE:
        if text.count(old) != count:
            raise ValueError('JAPAN_PAGE_ANCHOR:%d:%s' % (text.count(old), old[:40]))
        text = text.replace(old, new)
    text = _holidays(text)
    return text.encode('utf-8')
