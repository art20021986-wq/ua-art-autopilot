"""Static Ukrainian and Russian versions of a car card (CARD-LANG-001).

The CRM writers keep writing /video/UA-XXXX.html (Russian HTML that the site language script shows in
Ukrainian). This module derives two static pages from it: /video/ua/UA-XXXX.html (Ukrainian) and
/video/ru/UA-XXXX.html (Russian), each with its own canonical and hreflang links. The Ukrainian text comes
from the site's own translations (the dictionary and the data-uk attributes of ua-site-languages.js, the
one source), so there is no second dictionary. A card whose Ukrainian text is incomplete is not derived.
Pure functions; reconcile() writes the derived files atomically and only when the source changed.
"""
import hashlib
import html
import json
import os
from pathlib import Path
import re
import tempfile

ORIGIN = 'https://www.uaart.com.ua'
CARD = re.compile(r'UA-[0-9]{4,}\.html')
DIRS = {'uk': 'ua', 'ru': 'ru'}
SOURCE_MARK = 'ua-card-lang-source'  # <meta name=... content=revision(): the CRM page and translations it came from>
SKIP = {'script', 'style', 'code', 'pre', 'textarea'}
ATTRIBUTES = {'title': 'title', 'aria-label': 'aria', 'placeholder': 'placeholder', 'alt': 'alt', 'content': 'content'}
META_TEXT = re.compile(r'(?:description|title)$')
RUSSIAN_ONLY = re.compile('[ыэъёЫЭЪЁ]')
TAG = re.compile(r'<!--.*?-->|<(/?)([a-zA-Z][a-zA-Z0-9-]*)((?:[^>"\']|"[^"]*"|\'[^\']*\')*)>', re.S)
ATTR = re.compile(r'([^\s=/>]+)(?:\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+))?')
# The site script's own phrase rules for Ukrainian (ua-site-languages.js translated(), language 'uk').
RULES = (
    (r'^(\d+) (?:автомобиль|автомобиля|автомобилей|автомобіль|автомобілі|автомобілів)$', lambda m: m[1] + ' ' + plural(int(m[1]), 'автомобіль', 'автомобілі', 'автомобілів')),
    (r'^(?:Открыть все автомобили|Відкрити всі автомобілі)\s*·\s*(\d+)$', lambda m: 'Відкрити всі автомобілі · ' + m[1]),
    (r'^(?:Показано|Показанo|Показуємо|Показано авто|ნაჩვენებია)\s*:?\s*(\d+)$', lambda m: 'Показано: ' + m[1]),
    (r'^(\d+) (?:день|дня|дней|дні|днів) до (?:Киева|Києва)$', lambda m: m[1] + ' ' + plural(int(m[1]), 'день', 'дні', 'днів') + ' до Києва'),
    (r'^(?:обновлено|оновлено) (.+)$', lambda m: 'оновлено ' + m[1]),
    (r'^(\d+) (фото|видео|відео)$', lambda m: m[1] + ' ' + ('фото' if m[2] == 'фото' else 'відео')),
    (r'^Фото:\s*(\d+)(?:\s*·\s*(?:Видео|Відео):\s*(\d+))?$', lambda m: 'Фото: ' + m[1] + (' · Відео: ' + m[2] if m[2] else '')),
    (r'^кадр (\d+)$', lambda m: 'кадр ' + m[1]),
    (r'^(\d+) фото · листайте вбок, тап — во весь экран$', lambda m: m[1] + ' фото · гортайте вбік, дотик — на весь екран'),
    (r'^Диагностика (.+) — UA ART COMPANY$', lambda m: 'Діагностика ' + m[1] + ' — UA ART COMPANY'),
    (r'^UA ART COMPANY LLC · диагностика (UA-\d+)$', lambda m: 'UA ART COMPANY LLC · діагностика ' + m[1]),
    (r'^Забронировать авто за (.+)$', lambda m: 'Забронювати авто за ' + m[1]),
    (r'^Отследить контейнер (.+) — откроется в новой вкладке$', lambda m: 'Відстежити контейнер ' + m[1] + ' — відкриється в новій вкладці'),
    (r'^(.* · UA ART COMPANY — )авто из Кореи под ключ в Киеве(.*)$', lambda m: m[1] + 'авто з Кореї під ключ у Києві' + m[2]),
    (r'^(UA ART COMPANY — )авто из Кореи под ключ в Киеве\.(.*)$', lambda m: m[1] + 'авто з Кореї під ключ у Києві.' + m[2]),
    (r'^(Форма:)\s*(.*)$', lambda m: 'Форма: ' + m[2]),
)
RULES = tuple((re.compile(pattern), make) for pattern, make in RULES)


def plural(n, one, few, many):
    return one if n % 10 == 1 and n % 100 != 11 else few if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else many


def dictionary(script):
    """The site script's Ukrainian dictionary (Russian phrase -> Ukrainian)."""
    start = script.index('var dictionaries = ') + len('var dictionaries = ')
    value, _ = json.JSONDecoder().raw_decode(script[start:])
    return value['uk']


def clean(value):
    return ' '.join(value.split())


def phrase(value, words):
    """The script's translated(value, 'uk'): dictionary, then its phrase rules; whitespace kept."""
    text = clean(value)
    out = words.get(text)
    for pattern, make in RULES:
        if out is not None:
            break
        found = pattern.match(text)
        if found:
            out = make(found)
    if out is None:
        return value
    return value[:len(value) - len(value.lstrip())] + out + value[len(value.rstrip()):]


def attributes(raw):
    return {name.lower(): html.unescape(value[1:-1] if value and value[0] in '"\'' else value or '')
            for name, value in ATTR.findall(raw)}


def set_attribute(raw, name, value):
    """raw: the attribute text of a tag; sets (or adds) one attribute."""
    quoted = '"%s"' % html.escape(value, quote=True)
    pattern = re.compile(r'(\s%s\s*=\s*)("[^"]*"|\'[^\']*\'|[^\s>]+)' % re.escape(name), re.I)
    if pattern.search(raw):
        return pattern.sub(lambda m: m[1] + quoted, raw, count=1)
    end = '/' if raw.rstrip().endswith('/') else ''
    return raw.rstrip().rstrip('/') + ' %s=%s%s' % (name, quoted, (' ' + end) if end else '')


def ukrainian(source, words):
    """The card page with the Ukrainian text the site script would show; returns (html, untranslated)."""
    out, missing, stack, position = [], [], [], 0
    for match in TAG.finditer(source):
        text = source[position:match.start()]
        if text:
            parent = stack[-1] if stack else None
            skipped = any(tag in SKIP or attrs.get('data-site-no-translate') is not None for tag, attrs in stack)
            if not skipped and clean(text):
                data_uk = parent and (parent[1].get('data-uk') or parent[1].get('data-ua'))
                new = data_uk if data_uk and parent[1].get('data-ru') is not None else phrase(html.unescape(text), words)
                if new != html.unescape(text):
                    text = html.escape(new, quote=False)
                elif RUSSIAN_ONLY.search(new):
                    missing.append(clean(new))
            out.append(text)
        position = match.end()
        whole = match.group(0)
        if whole.startswith('<!--'):
            out.append(whole)
            continue
        closing, tag, raw = match.group(1), match.group(2).lower(), match.group(3)
        if closing:
            while stack and stack.pop()[0] != tag:
                pass
            out.append(whole)
            continue
        attrs = attributes(raw)
        if not any(t in SKIP for t, _ in stack):
            raw = _attributes_uk(tag, raw, attrs, words, missing)
        out.append('<%s%s>' % (match.group(2), raw))
        if not raw.rstrip().endswith('/') and tag not in ('meta', 'link', 'img', 'br', 'hr', 'input', 'source', 'base', 'wbr'):
            stack.append((tag, attrs))
    out.append(source[position:])
    return ''.join(out), missing


def _attributes_uk(tag, raw, attrs, words, missing):
    for name, suffix in ATTRIBUTES.items():
        if name not in attrs:
            continue
        if name == 'content' and not (tag == 'meta' and META_TEXT.search(attrs.get('name') or attrs.get('property') or '')):
            continue
        value = attrs.get('data-uk-' + suffix) or attrs.get('data-ua-' + suffix)
        if value is None:
            value = phrase(attrs[name], words)
            if value == attrs[name] and RUSSIAN_ONLY.search(value):
                missing.append(clean(value))
        if value != attrs[name]:
            raw = set_attribute(raw, name, value)
    return raw


def absolute(source):
    """Relative links and media of a /video/ page (attributes and the gallery's photo list), made absolute
    for a page one folder deeper."""
    def fix(match):
        value = match.group(3)
        if re.match(r'^(?:[a-z][a-z0-9+.-]*:|/|#)', value, re.I) or not value:
            return match.group(0)
        return '%s%s/video/%s%s' % (match.group(1), match.group(2), value, match.group(2))
    source = re.sub(r'(\s(?:src|href|poster|data-src)\s*=\s*)(["\'])(.*?)\2', fix, source)
    # The card gallery keeps its photo list in a script: 'foto/UA-XXXX/001.jpg'.
    return re.sub(r'(["\'])foto/', r'\1/video/foto/', source)


def head(source, name, lang):
    """lang on <html>, a self canonical and the hreflang links of both versions."""
    code = name[:-5]
    links = ''.join('<link rel="alternate" hreflang="%s" href="%s/video/%s/%s">' % (l, ORIGIN, DIRS[l], name)
                    for l in ('uk', 'ru'))
    links += '<link rel="alternate" hreflang="x-default" href="%s/video/%s/%s">' % (ORIGIN, DIRS['uk'], name)
    source = re.sub(r'<link\s+rel=["\'](?:canonical|alternate)["\'][^>]*>\s*', '', source, flags=re.I)
    source = re.sub(r'(<html\b[^>]*?\blang\s*=\s*)(["\'])[^"\']*\2', r'\1"%s"' % lang, source, count=1, flags=re.I)
    tags = '<link rel="canonical" href="%s/video/%s/%s">%s' % (ORIGIN, DIRS[lang], name, links)
    source, count = re.subn(r'</head\s*>', tags + '</head>', source, count=1, flags=re.I)
    if count != 1 or not code.startswith('UA-'):
        raise ValueError('CARD_HEAD:' + name)
    return source


def versions(source, name, words, wanted):
    """({'ua/UA-XXXX.html': uk html, 'ru/UA-XXXX.html': ru html}, []) or (None, the untranslated phrases)."""
    if not CARD.fullmatch(name):
        raise ValueError('CARD_NAME:' + name)
    mark = '<meta name="%s" content="%s">' % (SOURCE_MARK, wanted)
    base = absolute(source).replace('</head>', mark + '</head>', 1)
    uk, missing = ukrainian(base, words)
    if missing:
        return None, sorted(set(missing))
    return {'%s/%s' % (DIRS['uk'], name): head(uk, name, 'uk'), '%s/%s' % (DIRS['ru'], name): head(base, name, 'ru')}, []


def mark_of(page):
    found = re.search(r'<meta name="%s" content="([0-9a-f]{64})">' % SOURCE_MARK, page)
    return found and found.group(1)


def revision(source, script):
    """What a derived page was built from: the CRM page and the translations."""
    return hashlib.sha256(source.encode() + b'\0' + script.encode()).hexdigest()


def canonical(name, root):
    """The canonical URL of a card: its Ukrainian version once it exists, else the card itself."""
    if (Path(root)/DIRS['uk']/name).is_file() and (Path(root)/DIRS['ru']/name).is_file():
        return '%s/video/%s/%s' % (ORIGIN, DIRS['uk'], name)
    return '%s/video/%s' % (ORIGIN, name)


def write(path, value):
    """Atomic public file write; False when the file already holds value."""
    path = Path(path)
    if path.is_file() and path.read_bytes() == value:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.card-lang-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


def reconcile(root, published):
    """Language versions of the published cards (names) under root (/home/Carix/video).

    A version is rebuilt only when its CRM page or the translations changed; versions of cards no longer
    published are removed. Returns what changed; never raises for one card.
    """
    root = Path(root)
    script = (root/'ua-site-languages.js').read_text(encoding='utf-8')
    words = dictionary(script)
    result = {'written': [], 'incomplete': {}, 'removed': [], 'failed': {}}
    for name in sorted(published):
        try:
            source = (root/name).read_text(encoding='utf-8')
            wanted = revision(source, script)
            paths = [root/DIRS[lang]/name for lang in ('uk', 'ru')]
            if all(p.is_file() and mark_of(p.read_text(encoding='utf-8')) == wanted for p in paths):
                continue
            pages, missing = versions(source, name, words, wanted)
            if pages is None:
                result['incomplete'][name] = missing[:20]
                continue
            for relative, page in pages.items():
                write(root/relative, page.encode('utf-8'))
            result['written'].append(name)
        except Exception as error:  # one card never stops the others
            result['failed'][name] = type(error).__name__ + ':' + str(error)[:160]
    for lang in ('uk', 'ru'):
        for path in sorted((root/DIRS[lang]).glob('UA-*.html')):
            if path.name not in published:
                path.unlink()
                result['removed'].append('%s/%s' % (DIRS[lang], path.name))
    return result


def root_of(file_name):
    """The public folder of a written card: its own folder for a path, else /home/Carix/video."""
    path = Path(str(file_name))
    return path.parent if path.is_absolute() else Path('/home/Carix/video')
