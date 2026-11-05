"""Home page, «5 steps» block: step 1 becomes «Бесплатная консультация» with owner-approved details
(ORDER-PROCESS-001, texts in tasks/ORDER-PROCESS-001.md).

Only the first <li> of the steps list and one small CSS block change; every other byte stays. Each text element
holds its three languages in data-ru / data-uk / data-ka with the Ukrainian text inside, as the site's language
script expects (one text node per element). Details open with the browser's own <details>, no script.
"""
import re

MARK = 'ua-home-step1-001'
FORM = 'podbor.html'

OLD_STEP = ('<li><i>1</i><b data-ru="Заявка" data-uk="Заявка" data-ka="განაცხადი">Заявка</b>'
            '<small data-ru="Расскажите бюджет и пожелания" data-uk="Розкажіть бюджет і побажання" '
            'data-ka="გვითხარით ბიუჯეტი და სურვილები">Розкажіть бюджет і побажання</small></li>')
HEAD = re.compile(r'(?=</head\s*>)', re.I)

# (ru, uk, ka)
TITLE = ('Бесплатная консультация', 'Безкоштовна консультація', 'უფასო კონსულტაცია')
SHORT = ('Оставьте заявку — это ни к чему не обязывает', 'Залиште заявку — це ні до чого не зобов’язує',
         'დატოვეთ განაცხადი — ეს არაფერს გავალდებულებთ')
MORE = ('Подробнее', 'Детальніше', 'დაწვრილებით')
LINES = (
    ('Заполните заявку на сайте: марка, модель, год, бюджет, страна, пожелания. '
     'Или позвоните — менеджер оформит заявку за вас.',
     'Заповніть заявку на сайті: марка, модель, рік, бюджет, країна, побажання. '
     'Або зателефонуйте — менеджер оформить заявку за вас.',
     'შეავსეთ განაცხადი საიტზე: მარკა, მოდელი, წელი, ბიუჯეტი, ქვეყანა, სურვილები. '
     'ან დაგვირეკეთ — მენეჯერი განაცხადს თქვენ მაგივრად შეავსებს.'),
    ('Заявки обрабатываем строго по очереди поступления. Возможно, ответим в тот же день; '
     'максимум — 3 рабочих дня (все дни, кроме воскресенья и праздников).',
     'Заявки обробляємо суворо в порядку надходження. Можливо, відповімо того ж дня; '
     'максимум — 3 робочі дні (усі дні, крім неділі та свят).',
     'განაცხადებს ვამუშავებთ მკაცრად შემოსვლის რიგით. შესაძლოა, იმავე დღეს გიპასუხოთ; '
     'მაქსიმუმ — 3 სამუშაო დღე (ყველა დღე, გარდა კვირისა და დღესასწაულებისა).'),
    ('В ответ вы получите предварительный расчёт стоимости авто. Это ориентировочная цена: итоговая может '
     'отличаться до 1000 $ в большую или меньшую сторону (цена на аукционе, курс, доставка). '
     'Окончательная цена фиксируется в договоре.',
     'У відповідь ви отримаєте попередній розрахунок вартості авто. Це орієнтовна ціна: остаточна може '
     'відрізнятися до 1000 $ у більший або менший бік (ціна на аукціоні, курс, доставка). '
     'Остаточна ціна фіксується в договорі.',
     'პასუხად მიიღებთ ავტომობილის ღირებულების წინასწარ გაანგარიშებას. ეს მიახლოებითი ფასია: საბოლოო შეიძლება '
     'განსხვავდებოდეს 1000 $-მდე მეტად ან ნაკლებად (აუქციონის ფასი, კურსი, მიწოდება). '
     'საბოლოო ფასი ფიქსირდება ხელშეკრულებაში.'),
    ('Заявка — не договор и ни к чему вас не обязывает.',
     'Заявка — не договір і ні до чого вас не зобов’язує.',
     'განაცხადი არ არის ხელშეკრულება და არაფერს გავალდებულებთ.'),
)
PAY = ('Оплата на этом шаге: 0 грн', 'Оплата на цьому кроці: 0 грн', 'გადახდა ამ ეტაპზე: 0')
BUTTON = ('Заполнить заявку', 'Заповнити заявку', 'განაცხადის შევსება')
# Public proof that this release is live.
CHECK = '>Безкоштовна консультація</b>'


def _text(tag, words, cls=''):
    ru, uk, ka = words
    for value in words:
        if any(c in value for c in '<>"&'):
            raise ValueError('HOME_STEP1_TEXT')
    return '<%s%s data-ru="%s" data-uk="%s" data-ka="%s">%s</%s>' % (
        tag, ' class="%s"' % cls if cls else '', ru, uk, ka, uk, tag)


def step():
    lines = ''.join(_text('p', words) for words in LINES)
    ru, uk, ka = BUTTON
    button = '<a class="button gold" href="%s" data-ru="%s" data-uk="%s" data-ka="%s">%s</a>' % (FORM, ru, uk, ka, uk)
    return ('<li class="ua-step-free"><i>1</i>%s%s<details class="ua-step-more">%s<div>%s%s%s</div></details></li>'
            % (_text('b', TITLE), _text('small', SHORT), _text('summary', MORE), lines,
               _text('p', PAY, 'ua-step-pay'), button))


CSS = ('<style id="%s">'
       '.ua-how li.ua-step-free:has(details[open]){grid-column:1/-1}'
       '.ua-step-more{grid-column:1/-1;margin-top:10px}'
       '.ua-step-more summary{cursor:pointer;color:var(--gold);font-weight:700;font-size:16px;padding:6px 0;'
       'min-height:44px;display:flex;align-items:center}'
       '.ua-step-more summary::-webkit-details-marker{display:none}'
       '.ua-step-more summary::after{content:"\\25BE";margin-left:8px}'
       '.ua-step-more[open] summary::after{content:"\\25B4"}'
       '.ua-step-more summary:focus-visible{outline:2px solid var(--gold);outline-offset:3px;border-radius:6px}'
       '.ua-step-more>div{display:grid;gap:10px;padding-top:4px}'
       '.ua-step-more p{margin:0;font-size:16px;line-height:1.6;color:#e6edf5;max-width:68ch}'
       '.ua-step-more .ua-step-pay{font-weight:800;color:var(--gold)}'
       '.ua-step-more .button{justify-self:start;margin-top:4px;min-height:48px;padding:0 22px}'
       '@media (max-width:700px){.ua-step-more .button{justify-self:stretch;text-align:center}}'
       '</style>' % MARK)


def build(source):
    text = source.decode('utf-8')
    if MARK in text or text.count(OLD_STEP) != 1:
        raise ValueError('HOME_STEP1_ANCHOR')
    if len(HEAD.findall(text)) != 1:
        raise ValueError('HOME_HEAD')
    text = text.replace(OLD_STEP, step(), 1)
    text = HEAD.sub(lambda m: CSS, text, count=1)
    return text.encode('utf-8')
