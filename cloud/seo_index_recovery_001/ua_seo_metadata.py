"""Deterministic SEO at HTML generation; no network, database or file writes."""
from html import escape
from html.parser import HTMLParser
from pathlib import PurePath
import re
from urllib.parse import urlsplit

CORE = ('index.html', 'katalog.html', 'podbor.html', 'info.html')
CARD = re.compile(r'UA-[0-9]{4,}\.html', re.I)
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
        'meta', 'param', 'source', 'track', 'wbr'}


class Document(HTMLParser):
    """Read facts and source spans without reserializing the page."""
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.source = source
        self.lines = [0]
        for line in source.splitlines(keepends=True):
            self.lines.append(self.lines[-1] + len(line))
        self.nodes, self.stack = [], []
        self.feed(source)

    def position(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        start = self.position()
        raw = self.get_starttag_text()
        node = dict(tag=tag, attrs=dict(attrs), start=start, open_end=start+len(raw),
                    end=start+len(raw), inner_end=start+len(raw), text=[])
        self.nodes.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack and self.stack[-1]['tag'] == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i]['tag'] == tag:
                node = self.stack[i]
                node['inner_end'] = self.position()
                node['end'] = self.source.index('>', self.position()) + 1
                del self.stack[i:]
                break

    def handle_data(self, value):
        for node in self.stack:
            if node['tag'] in ('title', 'h1', 'td'):
                node['text'].append(value)

    def select(self, tag):
        return [n for n in self.nodes if n['tag'] == tag]


def text(node):
    return ' '.join(''.join(node['text']).split())


def page_name(source):
    doc = Document(source)
    for node in doc.select('link'):
        if 'canonical' in (node['attrs'].get('rel') or '').lower().split():
            name = PurePath(urlsplit(node['attrs'].get('href', '')).path).name
            if name in CORE:
                return name
            if CARD.fullmatch(name):
                return ''
    title = ' '.join(text(n) for n in doc.select('title')).lower()
    if 'каталог' in title:
        return 'katalog.html'
    if any(word in title for word in ('подбор', 'под заказ', 'замовлення')):
        return 'podbor.html'
    if any(word in title for word in ('услов', 'информац', 'умови')):
        return 'info.html'
    return 'index.html' if 'ua art company' in title else ''


def localized(values, suffix=''):
    return ''.join(' data-%s%s="%s"' % (lang, suffix, escape(value, quote=True))
                   for lang, value in values.items())


def core_metadata(name):
    values = {
        'index.html': (
            ('Автомобили под ключ в Киеве — UA ART COMPANY',
             'Автомобілі під ключ у Києві — UA ART COMPANY'),
            ('Подбор, проверка, доставка и оформление автомобилей. Каталог авто в наличии и в пути, заказ автомобиля из-за рубежа — UA ART COMPANY, Киев.',
             'Підбір, перевірка, доставка та оформлення автомобілів. Каталог авто в наявності й у дорозі, замовлення автомобіля з-за кордону — UA ART COMPANY, Київ.')),
        'katalog.html': (
            ('Каталог авто в наличии и в пути — UA ART COMPANY',
             'Каталог авто в наявності й у дорозі — UA ART COMPANY'),
            ('Каталог автомобилей UA ART COMPANY: фото, характеристики, цены и текущий этап доставки. Выберите автомобиль в наличии или в пути.',
             'Каталог автомобілів UA ART COMPANY: фото, характеристики, ціни та поточний етап доставки. Оберіть автомобіль у наявності або в дорозі.')),
        'podbor.html': (
            ('Подбор авто под заказ в Украину — UA ART COMPANY',
             'Підбір авто під замовлення в Україну — UA ART COMPANY'),
            ('Подбор автомобиля из Кореи, США, Японии и других стран. Укажите страну, модель и бюджет в заявке UA ART COMPANY для обсуждения подбора и доставки.',
             'Підбір автомобіля з Кореї, США, Японії та інших країн. Укажіть країну, модель і бюджет у заявці UA ART COMPANY для обговорення підбору та доставки.')),
        'info.html': (
            ('Условия покупки и доставки авто — UA ART COMPANY',
             'Умови купівлі та доставки авто — UA ART COMPANY'),
            ('Условия покупки автомобиля в UA ART COMPANY: состав цены, порядок оплаты, доставка и оформление. Ознакомьтесь с условиями перед выбором автомобиля.',
             'Умови купівлі автомобіля в UA ART COMPANY: склад ціни, порядок оплати, доставка та оформлення. Ознайомтеся з умовами перед вибором автомобіля.')),
    }
    title, description = values[name]
    return dict(zip(('ru', 'uk'), title)), dict(zip(('ru', 'uk'), description))


def card_metadata(doc, name):
    headings = doc.select('h1')
    if len(headings) != 1 or not text(headings[0]):
        raise ValueError('SEO_CARD_HEADING:' + name)
    model = text(headings[0])
    cells = [text(n) for n in doc.select('td')]
    facts = dict(zip(cells[::2], cells[1::2]))
    mileage = facts.get('Пробег') or facts.get('Пробіг') or ''
    engine = facts.get('Двигатель') or facts.get('Двигун') or ''
    detail = mileage if mileage else name[:-5]
    titles = {'ru': '%s, %s — купить | UA ART' % (model, detail),
              'uk': '%s, %s — купити | UA ART' % (model, detail)}
    ru = '%s.%s%s Фото и характеристики автомобиля, страница диагностики и условия покупки в UA ART COMPANY.' % (
        model, (' Пробег %s.' % mileage) if mileage else '',
        (' Двигатель %s.' % engine) if engine else '')
    uk = '%s.%s%s Фото й характеристики автомобіля, сторінка діагностики та умови купівлі в UA ART COMPANY.' % (
        model, (' Пробіг %s.' % mileage) if mileage else '',
        (' Двигун %s.' % engine) if engine else '')
    return titles, {'ru': ru, 'uk': uk}, model


def normalize(source, file_name):
    """Idempotent edit of SEO fields only; preserve all business content."""
    if not isinstance(source, str) or not source:
        return source
    name = PurePath(str(file_name)).name
    is_card = CARD.fullmatch(name)
    if name not in CORE and not is_card:
        return source
    doc = Document(source)
    titles = doc.select('title')
    if len(titles) != 1 or not doc.select('head'):
        raise ValueError('SEO_HEAD_INVALID:' + name)
    html = doc.select('html')
    lang = 'uk' if html and html[0]['attrs'].get('lang') == 'uk' else 'ru'
    if name == 'podbor.html' and 'id="ua-order"' in source:
        lang = 'uk'  # The server-rendered order form is Ukrainian.
    if is_card:
        title, description, model = card_metadata(doc, name)
    else:
        title, description = core_metadata(name)
    # Keep existing Georgian translations when available; other locales keep
    # using the site's existing language presentation module.
    old_ka = titles[0]['attrs'].get('data-ka')
    if old_ka:
        title['ka'] = old_ka
    edits = [(titles[0]['start'], titles[0]['end'],
              '<title%s>%s</title>' % (localized(title), escape(title[lang])))]
    if name == 'podbor.html' and html and lang == 'uk':
        node = html[0]
        raw = source[node['start']:node['open_end']]
        raw = re.sub(r'\blang\s*=\s*([\"\']).*?\1', 'lang="uk"', raw, count=1, flags=re.I)
        edits.append((node['start'], node['open_end'], raw))
    descriptions = [n for n in doc.select('meta') if (n['attrs'].get('name') or '').lower() == 'description']
    if descriptions and descriptions[0]['attrs'].get('data-ka-content'):
        description['ka'] = descriptions[0]['attrs']['data-ka-content']
    meta = '<meta name="description" content="%s"%s>' % (escape(description[lang], quote=True), localized(description, '-content'))
    for i, node in enumerate(descriptions):
        edits.append((node['start'], node['end'], meta if i == 0 else ''))
    if not descriptions:
        edits.append((titles[0]['end'], titles[0]['end'], meta))
    for node in doc.select('meta'):
        prop = node['attrs'].get('property')
        if prop in ('og:title', 'og:description'):
            value = title if prop == 'og:title' else description
            edits.append((node['start'], node['end'], '<meta property="%s" content="%s"%s>' %
                          (prop, escape(value[lang], quote=True), localized(value, '-content'))))
    if is_card:
        numbers = {}
        for node in doc.select('img'):
            attrs = node['attrs']
            src = attrs.get('src', '')
            if ('/foto/' not in '/' + src or name[:-5].upper() not in src.upper()
                    or attrs.get('alt') or attrs.get('role') == 'presentation'
                    or attrs.get('aria-hidden') == 'true'):
                continue
            key = PurePath(urlsplit(src).path).name
            number = numbers.setdefault(key, len(numbers)+1)
            values = {'ru': '%s — фото %s' % (model, number), 'uk': '%s — фото %s' % (model, number)}
            raw = source[node['start']:node['open_end']]
            raw = re.sub(r'\s+alt\s*=\s*([\"\']).*?\1', '', raw, flags=re.I)
            end = '/>' if raw.endswith('/>') else '>'
            raw = raw[:-len(end)] + ' alt="%s"%s' % (escape(values[lang], quote=True), localized(values, '-alt')) + end
            edits.append((node['start'], node['open_end'], raw))
    if name == 'info.html' and not doc.select('h1'):
        for node in doc.select('div'):
            if node['attrs'].get('class') == 'zagolovok':
                inner = source[node['open_end']:node['inner_end']]
                edits.append((node['start'], node['end'], '<h1 class="zagolovok" style="margin:0">%s</h1>' % inner))
                break
    if name == 'podbor.html' and 'id="ua-seo-order-intro"' not in source:
        headings = doc.select('h1')
        if len(headings) == 1:
            # Outside the form's no-translate subtree: compact static copy,
            # no script, no new form fields or handlers.
            copy = 'Підбір авто з Кореї, США, Японії та інших країн починається з вибору моделі й бюджету. Залиште заявку, щоб обговорити доступні варіанти, перевірку автомобіля та умови доставки в Україну.'
            ru = 'Подбор авто из Кореи, США, Японии и других стран начинается с выбора модели и бюджета. Оставьте заявку, чтобы обсудить доступные варианты, проверку автомобиля и условия доставки в Украину.'
            block = '<p id="ua-seo-order-intro" style="margin:12px 0;color:inherit"><span%s>%s</span> <a href="info.html"%s>%s</a></p>' % (
                localized({'ru': ru, 'uk': copy}), escape(copy if lang == 'uk' else ru),
                localized({'ru': 'Условия покупки и доставки', 'uk': 'Умови купівлі та доставки'}),
                'Умови купівлі та доставки' if lang == 'uk' else 'Условия покупки и доставки')
            # Put the copy immediately before main, where existing locale code
            # handles the data attributes normally.
            mains = [n for n in doc.select('main') if n['attrs'].get('id') == 'ua-order']
            if mains:
                block = '<div style="max-width:960px;margin:0 auto;padding:0 16px">' + block + '</div>'
                edits.append((mains[0]['start'], mains[0]['start'], block))
    for start, end, value in sorted(edits, key=lambda e:(e[0],e[1]), reverse=True):
        source = source[:start] + value + source[end:]
    return source
