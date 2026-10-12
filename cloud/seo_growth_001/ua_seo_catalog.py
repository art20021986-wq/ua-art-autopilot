"""Public facts of the published cars, read from the installed catalog page only.

Pure: no network, database or file access. The catalog is the single public list
of published cars, so pages derived from it never show a car the site hides.
"""
from html import unescape
import re

ORIGIN = 'https://www.uaart.com.ua'
ARTICLE = re.compile(r'<article\b[^>]*>.*?</article>', re.S | re.I)
CODE = re.compile(r'href="(UA-[0-9]{4,})\.html"')
# Cyrillic letters that CRM operators type instead of identical Latin ones.
LOOKALIKE = str.maketrans('АВЕКМНОРСТХаеорсх', 'ABEKMHOPCTXaeopcx')
BRANDS = {'kia': 'Kia', 'hyundai': 'Hyundai', 'audi': 'Audi', 'mercedes-benz': 'Mercedes-Benz',
          'bmw': 'BMW', 'genesis': 'Genesis', 'chevrolet': 'Chevrolet', 'renault': 'Renault',
          'ssangyong': 'SsangYong', 'volkswagen': 'Volkswagen', 'toyota': 'Toyota', 'lexus': 'Lexus'}
MODEL_ALIASES = {'Б-КЛАССА': 'B-Class', 'Б-КЛАСС': 'B-Class', 'Е-КЛАСС': 'E-Class'}


def _text(value):
    return ' '.join(unescape(re.sub(r'<[^>]+>', ' ', value)).split())


def _first(pattern, value):
    found = re.search(pattern, value, re.S)
    return _text(found.group(1)) if found else ''


def _number(value):
    digits = re.sub(r'[^0-9]', '', value or '')
    return int(digits) if digits else None


def model_key(name):
    """('Kia', 'K5') for 'Kia К5 2016'; None when the brand is unknown."""
    words = name.split()
    if words and re.fullmatch(r'(19|20)[0-9]{2}', words[-1]):
        words = words[:-1]
    if len(words) < 2:
        return None
    brand = BRANDS.get(words[0].translate(LOOKALIKE).lower())
    if brand is None:
        return None
    raw = ' '.join(words[1:])
    if raw.upper() in MODEL_ALIASES:
        return brand, MODEL_ALIASES[raw.upper()]
    model = raw.translate(LOOKALIKE)
    if brand == 'Mercedes-Benz':
        letter = re.fullmatch(r'([A-Z])[ -]?(?:[0-9]{3}[a-z]?|class)', model, re.I)
        if letter:
            return brand, letter.group(1).upper() + '-Class'
    if not re.fullmatch(r'[A-Za-z0-9 -]+', model):
        return None
    if re.fullmatch(r'[A-Za-z]{1,3}[0-9]{1,3}|[A-Za-z]{2,3}', model):
        return brand, model.upper()
    return brand, ' '.join(w if w.isupper() and len(w) <= 3 else w.capitalize() for w in model.split())


def cars(catalog):
    """Cars in catalog order: code, name, url, image, price_usd, mileage_km, specs, stage, key."""
    result, seen = [], set()
    for article in ARTICLE.findall(catalog):
        codes = set(CODE.findall(article))
        if len(codes) != 1:
            continue
        code = codes.pop()
        if code in seen:
            raise ValueError('SEO_CATALOG_DUPLICATE:' + code)
        seen.add(code)
        name = _first(r'<h2[^>]*>(.*?)</h2>', article)
        price = re.search(r'data-ua-market="ukraine"[^>]*?data-ua-value="([^"]*)"', article)
        stage = re.search(r'data-ua-stage="([0-9])"', article)
        image = re.search(r'<img\b[^>]*\bsrc="([^"]+)"', article)
        specs = _first(r'<p>(.*?)</p>', article)
        if not name:
            raise ValueError('SEO_CATALOG_NAME:' + code)
        src = unescape(image.group(1)) if image else ''
        if src and not src.startswith('http'):
            src = ORIGIN + '/video/' + src.lstrip('./')
        result.append({'code': code, 'name': name, 'url': '%s/video/%s.html' % (ORIGIN, code),
                       'image': src, 'price_usd': _number(price.group(1)) if price else None,
                       'mileage_km': _number(specs.split('км')[0]) if 'км' in specs else None,
                       'specs': specs, 'stage': int(stage.group(1)) if stage else None,
                       'key': model_key(name)})
    return result
