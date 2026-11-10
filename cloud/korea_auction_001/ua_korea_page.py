"""JPAUTO-KOREA-001: the «Korea online auctions» page (video/korea.html), owner 2026-11-10.

build(home_html) takes the live home page as the layout (header, menu, languages, footer, styles) and
replaces only the title, description, canonical and <main> with this page's content (uk/ru/ka through
the site's data-* language attributes). No scripts of its own; the auction platform is never named.
"""
import re
from html import escape

URL = 'https://www.uaart.com.ua/video/korea.html'
ONLINE = 'https://t.me/UA_artcompany_LLC_bot?start=korea_online'  # until partner login exists (stage 2)
TELEGRAM = 'https://t.me/UA_artcompany_LLC_bot'


def t(uk, ru, ka, tag='span', cls=''):
    """Element with the site's three-language attributes; Ukrainian text by default."""
    c = ' class="%s"' % cls if cls else ''
    return '<%s%s data-uk="%s" data-ru="%s" data-ka="%s">%s</%s>' % (
        tag, c, escape(uk), escape(ru), escape(ka), escape(uk), tag)


TITLE = ('Аукціони Кореї онлайн — UA ART COMPANY', 'Аукционы Кореи онлайн — UA ART COMPANY',
         'კორეის აუქციონები ონლაინ — UA ART COMPANY')
DESCRIPTION = ('Обирайте авто на аукціонах Кореї онлайн разом з UA ART COMPANY: тисячі лотів щотижня, '
               'оцінка стану, пробіг і стартова ціна. Депозит 2000 $ входить у вартість авто.',
               'Выбирайте авто на аукционах Кореи онлайн вместе с UA ART COMPANY: тысячи лотов каждую неделю, '
               'оценка состояния, пробег и стартовая цена. Депозит 2000 $ входит в стоимость авто.',
               'აირჩიეთ ავტომობილი კორეის აუქციონებზე ონლაინ UA ART COMPANY-სთან ერთად: ათასობით ლოტი '
               'ყოველკვირა. დეპოზიტი 2000 $ შედის ავტომობილის ღირებულებაში.')

STEPS = (
    (('Договір і депозит 2000 $', 'Договор и депозит 2000 $', 'ხელშეკრულება და დეპოზიტი 2000 $'),
     ('Депозит входить у вартість авто', 'Депозит входит в стоимость авто', 'დეპოზიტი შედის ავტომობილის ფასში')),
    (('Доступ до аукціонів онлайн', 'Доступ к аукционам онлайн', 'წვდომა აუქციონებზე ონლაინ'),
     ('Особистий вхід на сайті', 'Личный вход на сайте', 'პირადი შესვლა საიტზე')),
    (('Обираєте авто і суму ставки', 'Выбираете авто и сумму ставки', 'ირჩევთ ავტომობილს და ფსონს'),
     ('Фото, оцінка стану, пробіг, старт', 'Фото, оценка, пробег, старт', 'ფოტო, შეფასება, გარბენი, საწყისი')),
    (('Купуємо, веземо, розмитнюємо', 'Покупаем, везём, растаможиваем', 'ვყიდულობთ, ვაწვდით, ვაფორმებთ'),
     ('Менеджер ставить ставку і веде авто до видачі', 'Менеджер делает ставку и ведёт авто до выдачи',
      'მენეჯერი დებს ფსონს და მიჰყავს ავტომობილი გაცემამდე')),
)

AUCTIONS = (
    ('Auto Hub', ('Найбільший: понад 2 000 авто на торгах щосереди', 'Крупнейший: более 2 000 авто на торгах каждую среду',
                  'უდიდესი: 2 000-ზე მეტი ავტო ყოველ ოთხშაბათს')),
    ('K Car', ('Майданчики Осан і Седжон, торги щовівторка', 'Площадки Осан и Седжон, торги каждый вторник',
               'ოსანი და სეჯონი, ვაჭრობა ყოველ სამშაბათს')),
    ('SK Rent Car', ('Авто з прокатного парку, торги щовівторка', 'Авто из прокатного парка, торги каждый вторник',
                     'ავტომობილები გაქირავების პარკიდან, ყოველ სამშაბათს')),
    ('AutoPlus · AutoHands', ('Щотижневі торги: понеділок і середа', 'Еженедельные торги: понедельник и среда',
                              'ყოველკვირეული ვაჭრობა: ორშაბათი და ოთხშაბათი')),
    ('Oneprice', ('Авто за фіксованою ціною, без торгу', 'Авто по фиксированной цене, без торга',
                  'ავტომობილები ფიქსირებულ ფასად')),
)

WHY = (
    ('Ціна аукціону — нижча за ринок перепродажу', 'Цена аукциона — ниже рынка перепродажи',
     'აუქციონის ფასი — გადაყიდვის ბაზარზე დაბალი'),
    ('Чесна оцінка стану і лист огляду на кожне авто', 'Честная оценка состояния и лист осмотра на каждое авто',
     'მდგომარეობის შეფასება და დათვალიერების ფურცელი'),
    ('До 25 фото, пробіг, VIN та історія кожного лота', 'До 25 фото, пробег, VIN и история каждого лота',
     '25-მდე ფოტო, გარბენი, VIN და ისტორია'),
    ('Тисячі лотів щотижня — Hyundai, Kia, Genesis та інші', 'Тысячи лотов каждую неделю — Hyundai, Kia, Genesis и другие',
     'ათასობით ლოტი ყოველკვირა — Hyundai, Kia, Genesis'),
)

CSS = (
    '<style id="ua-korea-page-v1">'
    '.kr-wrap{max-width:1180px;margin:0 auto;padding:28px 20px 56px;color:#fff}'
    '.kr-hero{display:grid;gap:18px;padding:34px 28px;border-radius:22px;'
    'background:radial-gradient(120% 140% at 0% 0%,#1d3557 0%,#0B1524 60%);border:1px solid #2a3b55}'
    '.kr-kicker{color:#f2b544;letter-spacing:.18em;font-size:13px;font-weight:700}'
    '.kr-hero h1{margin:0;font-size:clamp(28px,4vw,44px);line-height:1.15}'
    '.kr-hero p{margin:0;font-size:18px;opacity:.9;max-width:760px}'
    '.kr-live{display:inline-flex;align-items:center;gap:8px;color:#ff4d4d;font-weight:700}'
    '.kr-actions{display:flex;flex-wrap:wrap;gap:12px}'
    '.kr-btn{display:inline-block;padding:16px 26px;border-radius:14px;font-weight:800;font-size:18px;'
    'text-decoration:none;background:linear-gradient(135deg,#ffd200,#ff8a00);color:#0B1524}'
    '.kr-btn.ghost{background:none;color:#fff;border:1px solid #3a4d6b}'
    '.kr-sec{margin-top:34px}.kr-sec h2{font-size:26px;margin:0 0 16px}'
    '.kr-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}'
    '.kr-card{background:#13233a;border:1px solid #23344f;border-radius:16px;padding:18px}'
    '.kr-card b{display:block;font-size:17px;margin-bottom:6px}.kr-card span{opacity:.85}'
    '.kr-num{color:#f2b544;font-weight:800;font-size:22px;display:block;margin-bottom:6px}'
    '.kr-deposit{display:grid;gap:10px;padding:26px;border-radius:18px;'
    'background:linear-gradient(135deg,#ffd200,#ff8a00);color:#0B1524}'
    '.kr-deposit strong{font-size:clamp(24px,3.4vw,34px)}'
    '.kr-list{list-style:none;margin:0;padding:0;display:grid;gap:10px}'
    '.kr-list li::before{content:"✓ ";color:#4ade80;font-weight:800}'
    '.kr-biz{border:1px dashed #f2b544}'
    '</style>'
)


def _main():
    steps = ''.join('<div class="kr-card"><span class="kr-num">%d</span>%s%s</div>' % (
        n, t(*title, tag='b'), t(*sub)) for n, (title, sub) in enumerate(STEPS, 1))
    auctions = ''.join('<div class="kr-card"><b>%s</b>%s</div>' % (escape(name), t(*desc))
                       for name, desc in AUCTIONS)
    why = ''.join('<li>%s</li>' % t(*w) for w in WHY)
    online = ('<a class="kr-btn" href="%s" target="_blank" rel="noopener">%s</a>'
              % (ONLINE, t('Дивитися онлайн', 'Смотреть онлайн', 'ონლაინ ნახვა')))
    write = ('<a class="kr-btn ghost" href="%s" target="_blank" rel="noopener">%s</a>'
             % (TELEGRAM, t('Написати в Telegram', 'Написать в Telegram', 'მოგვწერეთ Telegram-ში')))
    return (
        '<main id="main-content">' + CSS + '<div class="kr-wrap" id="online">'
        '<section class="kr-hero">'
        + t('АУКЦІОНИ КОРЕЇ · ОНЛАЙН', 'АУКЦИОНЫ КОРЕИ · ОНЛАЙН', 'კორეის აუქციონები · ონლაინ', cls='kr-kicker')
        + t('Обирайте авто на аукціонах Кореї — онлайн, разом з нами',
            'Выбирайте авто на аукционах Кореи — онлайн, вместе с нами',
            'აირჩიეთ ავტომობილი კორეის აუქციონებზე — ონლაინ, ჩვენთან ერთად', tag='h1')
        + t('Тисячі авто на торгах щотижня. Ви бачите фото, оцінку стану, пробіг і стартову ціну — '
            'обираєте авто і суму, а ми купуємо його для вас і веземо під ключ.',
            'Тысячи авто на торгах каждую неделю. Вы видите фото, оценку состояния, пробег и стартовую цену — '
            'выбираете авто и сумму, а мы покупаем его для вас и везём под ключ.',
            'ათასობით ავტომობილი ვაჭრობაზე ყოველკვირა. ხედავთ ფოტოს, შეფასებას, გარბენს და საწყის ფასს — '
            'ირჩევთ ავტომობილს და თანხას, ჩვენ კი ვყიდულობთ და ჩამოგვაქვს.', tag='p')
        + '<span class="kr-live">● ' + t('Торги щодня з понеділка по суботу', 'Торги каждый день с понедельника по субботу',
                                          'ვაჭრობა ყოველდღე ორშაბათიდან შაბათამდე') + '</span>'
        + '<div class="kr-actions">' + online + write + '</div></section>'
        '<section class="kr-sec"><div class="kr-deposit">'
        + t('Депозит 2000 $ — входить у вартість авто', 'Депозит 2000 $ — входит в стоимость авто',
            'დეპოზიტი 2000 $ — შედის ავტომობილის ღირებულებაში', tag='strong')
        + t('Укладаєте договір, вносите 2000 $ за курсом НБУ — і отримуєте право обирати авто на аукціонах Кореї '
            'та робити ставки через нас. Депозит повністю зараховується в ціну купленого авто.',
            'Заключаете договор, вносите 2000 $ по курсу НБУ — и получаете право выбирать авто на аукционах Кореи '
            'и делать ставки через нас. Депозит полностью засчитывается в цену купленного авто.',
            'აფორმებთ ხელშეკრულებას, შეგაქვთ 2000 $ ეროვნული ბანკის კურსით — და იღებთ უფლებას აირჩიოთ '
            'ავტომობილი და დადოთ ფსონი ჩვენი მეშვეობით. დეპოზიტი სრულად ჩაითვლება ფასში.')
        + '</div></section>'
        '<section class="kr-sec"><h2>' + t('Як це працює', 'Как это работает', 'როგორ მუშაობს') + '</h2>'
        '<div class="kr-grid">' + steps + '</div></section>'
        '<section class="kr-sec"><h2>' + t('Аукціони, до яких ви отримуєте доступ', 'Аукционы, к которым вы получаете доступ',
                                           'აუქციონები, რომლებზეც იღებთ წვდომას') + '</h2>'
        '<div class="kr-grid">' + auctions + '</div></section>'
        '<section class="kr-sec"><h2>' + t('Чому аукціон вигідніше', 'Почему аукцион выгоднее', 'რატომ არის აუქციონი უფრო მომგებიანი')
        + '</h2><ul class="kr-list">' + why + '</ul></section>'
        '<section class="kr-sec"><div class="kr-card kr-biz">'
        + t('Для автобізнесу — індивідуальні умови', 'Для автобизнеса — индивидуальные условия',
            'ავტობიზნესისთვის — ინდივიდუალური პირობები', tag='b')
        + t('Для автобізнесменів на індивідуальних умовах буде можливість купувати авто самостійно. '
            'Напишіть нам — обговоримо обсяги та умови.',
            'Для автобизнесменов на индивидуальных условиях будет возможность покупать авто самостоятельно. '
            'Напишите нам — обсудим объёмы и условия.',
            'ავტობიზნესმენებისთვის ინდივიდუალური პირობებით შესაძლებელი იქნება ავტომობილების დამოუკიდებლად შეძენა. '
            'მოგვწერეთ — განვიხილავთ პირობებს.')
        + '</div></section>'
        '<section class="kr-sec"><div class="kr-actions">' + online + write + '</div></section>'
        '</div></main>'
    )


def build(home_html):
    """Home page layout with this page's title, description, canonical and main content."""
    html = re.sub(r'<main id="main-content">.*?</main>', lambda m: _main(), home_html, count=1, flags=re.S)
    html = re.sub(r'<title[^>]*>.*?</title>', lambda m: t(*TITLE, tag='title'), html, count=1, flags=re.S)
    html = re.sub(r'<meta name="description"[^>]*>', lambda m: (
        '<meta name="description" content="%s" data-uk-content="%s" data-ru-content="%s" data-ka-content="%s">'
        % tuple(escape(x) for x in (DESCRIPTION[0],) + DESCRIPTION)), html, count=1)
    html = re.sub(r'<link rel="canonical"[^>]*>', '<link rel="canonical" href="%s">' % URL, html, count=1)
    html = re.sub(r'<script type="application/ld\+json"[^>]*>.*?</script>', '', html, flags=re.S)
    return html
