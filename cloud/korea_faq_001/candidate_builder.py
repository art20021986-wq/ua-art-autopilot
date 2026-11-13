"""Build the KOREA-FAQ-001 candidate (owner «Да» 2026-11-13 to the text and «ставить блок на сайт»).

/video/korea.html gets the owner-approved «Часті питання» block (cloud/korea_faq/approved.md) right after the section
«Чому аукціон вигідніше», in the page's own markup (kr-sec, data-uk/data-ru per text), between UA-KOREA-FAQ-V1 marks.
The Russian page /video/ru/korea.html follows by itself (ua_korea_ru via the card version job). No structured data:
Google shows FAQ rich results only for government and health sites. Every other byte stays as it is.
"""
from html import escape

PAGE = 'video/korea.html'
MARK = 'UA-KOREA-FAQ-V1'
ANCHOR = 'Чому аукціон вигідніше'
TITLE = ('Часті питання', 'Частые вопросы')
QA = (
    (('Скільки передоплата?', 'Сколько предоплата?'),
     ('Передоплата — від 1 000 $. Вона зараховується у вартість авто.',
      'Предоплата — от 1 000 $. Она засчитывается в стоимость авто.')),
    (('Як проходить ставка?', 'Как проходит ставка?'),
     ('Ви обираєте лот і суму ставки, а ми купуємо авто для вас. Логін і пароль для входу видає менеджер після договору.',
      'Вы выбираете лот и сумму ставки, а мы покупаем авто для вас. Логин и пароль для входа выдаёт менеджер после договора.')),
    (('Ціна в лоті — це ціна під ключ?', 'Цена в лоте — это цена под ключ?'),
     ('Ні, це стартова ціна в Кореї. Ціну під ключ розраховує менеджер, вона фіксується в договорі до купівлі.',
      'Нет, это стартовая цена в Корее. Цену под ключ рассчитывает менеджер, она фиксируется в договоре до покупки.')),
    (('Коли проходять торги?', 'Когда проходят торги?'),
     ('Щодня з понеділка по суботу.', 'Ежедневно с понедельника по субботу.')),
    (('Скільки триває доставка до Києва?', 'Сколько длится доставка до Киева?'),
     ('Викуп на аукціоні — від 3 до 10 днів, пором Корея → Грузія — близько 60 днів, Грузія → Київ, розмитнення, '
      'сертифікація та видача — близько 15 днів.',
      'Выкуп на аукционе — от 3 до 10 дней, паром Корея → Грузия — около 60 дней, Грузия → Киев, растаможка, '
      'сертификация и выдача — около 15 дней.')),
)
DEPENDENCY_SHA256 = {}


def text(pair):
    uk, ru = pair
    return '<span data-uk="%s" data-ru="%s">%s</span>' % (escape(uk), escape(ru), escape(uk, quote=False))


def block():
    items = ''.join('<h3>%s</h3><p>%s</p>' % (text(q), text(a)) for q, a in QA)
    style = '<style>#faq h3{color:#f0a63c;font-size:18px;margin:14px 0 4px}#faq p{margin:0}</style>'  # as the approved image
    return '<!--%s--><section class="kr-sec" id="faq">%s<h2>%s</h2>%s</section><!--/%s-->' % (
        MARK, style, text(TITLE), items, MARK)


def targets(root):
    return (PAGE,)


def build(source, dependencies, read_original=None):
    page = source[PAGE].decode('utf-8')
    if MARK in page:
        raise ValueError('KOREA_FAQ_ALREADY_APPLIED')
    at = page.find('>' + ANCHOR + '</span></h2>')
    if at < 0 or page.count('>' + ANCHOR + '</span></h2>') != 1:
        raise ValueError('KOREA_FAQ_ANCHOR')
    start = page.rfind('<section', 0, at)
    end = page.find('</section>', at)
    if start < 0 or end < 0 or '<section' in page[start + 8:at]:
        raise ValueError('KOREA_FAQ_SECTION')
    end += len('</section>')
    return {PAGE: (page[:end] + block() + page[end:]).encode('utf-8')}
