"""Deterministic SEO at HTML generation; no network, database or file writes."""
from html import escape
from html.parser import HTMLParser
from pathlib import PurePath
import re
from urllib.parse import urljoin, urlsplit

from ua_seo_catalog import model_key
from ua_seo_landings import model_name, path as landing_path
import ua_google_tag
import ua_seo_schema as schema

ORIGIN = 'https://www.uaart.com.ua'
LINKS_ID = 'ua-seo-links'
# Part of every card revision: bump when SEO page output changes, to republish all cards.
SEO_REVISION = 'SEO-GROWTH-001'
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


def card_facts(doc, source, name):
    """Public facts of one card page for its title, description and JSON-LD."""
    headings = doc.select('h1')
    if len(headings) != 1 or not text(headings[0]):
        raise ValueError('SEO_CARD_HEADING:' + name)
    code = name[:-5].upper()
    model = text(headings[0])
    cells = [text(n) for n in doc.select('td')]
    table = dict(zip(cells[::2], cells[1::2]))
    mileage = table.get('Пробег') or table.get('Пробіг') or ''
    price = re.search(r'data-ua-market=["\']ukraine["\'][^>]*?data-ua-value=["\']([0-9]+)', source)
    stage = (re.search(r'data-ua-stage-current=["\']([0-9])', source)
             or re.search(r'data-ua-stage=["\']([0-9])', source))
    image = next((n['attrs']['src'] for n in doc.select('img')
                  if code in n['attrs'].get('src', '').upper() and '/foto/' in '/' + n['attrs'].get('src', '')), '')
    year = re.search(r'(?:19|20)[0-9]{2}$', model)
    return {'code': code, 'name': model, 'url': '%s/video/%s' % (ORIGIN, name),
            'mileage': mileage, 'engine': table.get('Двигатель') or table.get('Двигун') or '',
            'mileage_km': int(re.sub(r'[^0-9]', '', mileage)) if re.search(r'[0-9]', mileage) else None,
            'price_usd': int(price.group(1)) if price and int(price.group(1)) > 0 else None,
            'stage': int(stage.group(1)) if stage else None,
            'image': urljoin(ORIGIN + '/video/', urlsplit(image).path.replace('/m/', '/')) if image else '',
            'year': int(year.group(0)) if year else None, 'key': model_key(model)}


def card_metadata(facts, name):
    model, mileage, engine = facts['name'], facts['mileage'], facts['engine']
    detail = mileage if mileage else name[:-5]
    price = ('{:,}'.format(facts['price_usd']).replace(',', '\u00a0') + ' $') if facts['price_usd'] else ''
    tail = (' — %s' % price) if price else ''
    titles = {'ru': '%s из Кореи, %s%s | купить в Киеве | UA ART' % (model, detail, tail),
              'uk': '%s з Кореї, %s%s | купити в Києві | UA ART' % (model, detail, tail)}
    ru = '%s из Кореи под ключ в Киеве%s.%s%s Фото, видео, VIN, диагностика и доставка — UA ART COMPANY.' % (
        model, (' — %s' % price) if price else '', (' Пробег %s.' % mileage) if mileage else '',
        (' Двигатель %s.' % engine) if engine else '')
    uk = '%s з Кореї під ключ у Києві%s.%s%s Фото, відео, VIN, діагностика та доставка — UA ART COMPANY.' % (
        model, (' — %s' % price) if price else '', (' Пробіг %s.' % mileage) if mileage else '',
        (' Двигун %s.' % engine) if engine else '')
    return titles, {'ru': ru, 'uk': uk}, model


def card_links(facts):
    """Links from a card to its model page and the hub, both languages; no other car codes."""
    links = []
    if facts['key']:
        name = model_name(facts['key'])
        links += [('/video/' + landing_path('uk', facts['key']), 'uk', name + ' з Кореї'),
                  ('/video/' + landing_path('ru', facts['key']), 'ru', name + ' из Кореи')]
    links += [('/video/' + landing_path('uk'), 'uk', 'Авто з Кореї під ключ'),
              ('/video/' + landing_path('ru'), 'ru', 'Авто из Кореи под ключ')]
    return ('<nav id="%s" aria-label="UA ART" style="max-width:960px;margin:18px auto;padding:0 16px;'
            'font-size:14px;line-height:1.7;opacity:.85">%s</nav>' % (LINKS_ID, ' · '.join(
                '<a href="%s" lang="%s" style="color:inherit">%s</a>' % (href, lang, escape(label))
                for href, lang, label in links)))


def card_schema(facts):
    return schema.script(schema.car(facts), schema.dealer('ru'), schema.breadcrumbs([
        ('UA ART COMPANY', ORIGIN + '/video/index.html'),
        ('Каталог', ORIGIN + '/video/katalog.html'), (facts['name'], facts['url'])]))


def replace_or_insert(doc, tag, ident, container, value):
    """Edit replacing the element with this id, else inserting before </container>."""
    own = [n for n in doc.select(tag) if n['attrs'].get('id') == ident]
    if own:
        return [(own[0]['start'], own[0]['end'], value)] + [(n['start'], n['end'], '') for n in own[1:]]
    parents = doc.select(container)
    if not parents:
        raise ValueError('SEO_%s_MISSING' % container.upper())
    return [(parents[0]['inner_end'], parents[0]['inner_end'], value)]


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
        facts = card_facts(doc, source, name)
        title, description, model = card_metadata(facts, name)
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
    if is_card:
        edits += replace_or_insert(doc, 'script', schema.SCRIPT_ID, 'head', card_schema(facts))
        edits += replace_or_insert(doc, 'nav', LINKS_ID, 'body', card_links(facts))
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
    return ua_google_tag.apply(source)
