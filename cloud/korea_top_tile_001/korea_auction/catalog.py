"""Owner's own cars from the public site catalogue (read-only): what the ticker promotes.

parse(html) -> cars [{code, title, year, stage, photo, url, price_usd}]
model_rules(cars) -> matchers telling whether an auction lot is the same model as an owner's car.
"""
import re
import urllib.request

SITE = 'https://www.uaart.com.ua/video/'
CATALOG_URL = SITE + 'katalog.html'
_CYR = str.maketrans('АВЕКМНОРСТХБ', 'ABEKMHOPCTXB')  # Cyrillic look-alikes in titles (К5, Б-КЛАССА)


def fetch(timeout=30):
    req = urllib.request.Request(CATALOG_URL, headers={'User-Agent': 'UA-ART-korea-auction/1'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def parse(html):
    cars = []
    for card in re.findall(r'<article class="catalog-card".*?</article>', html, re.S):
        code = re.search(r'UA-\d{4}', card)
        title = re.search(r'<h2>([^<]+)</h2>', card)
        if not code or not title:
            continue
        name = ' '.join(title.group(1).split())
        year = re.search(r'(\d{4})$', name)
        photo = re.search(r'<img[^>]+src="([^"]+)"', card)
        price = re.search(r'data-ua-market="ukraine"[^>]*data-ua-value="(\d+)"', card)
        link = re.search(r'class="catalog-photo" href="([^"]+)"', card)
        cars.append({'code': code.group(0), 'title': name, 'year': int(year.group(1)) if year else 0,
                     'stage': re.search(r'data-stage="([^"]+)"', card).group(1),
                     'photo': photo.group(1) if photo else '', 'url': link.group(1) if link else '',
                     'price_usd': int(price.group(1)) if price else 0})
    return cars


def absolute(path):
    """Site-relative link -> absolute /video/ address (the ticker is shown on other pages too)."""
    return path if path.startswith(('http://', 'https://', '/')) else SITE + path


def _rule(title):
    """Car title -> (maker, regex for the model in an auction lot), or None."""
    words = title.upper().translate(_CYR).replace('-', ' ').split()
    if len(words) < 2:
        return None
    maker, rest = words[0], ' '.join(words[1:-1] if words[-1].isdigit() else words[1:])
    if maker.startswith('MERCEDES'):
        rest = re.sub(r'^BENZ\s+', '', rest)
        cls = re.match(r'([A-Z]{1,3})\b', rest)  # 'B CLASS', 'E 220', 'B KLASSA'
        return ('MERCEDES', re.compile(r'\b%s\s?CLASS\b' % cls.group(1))) if cls else None
    token = rest.split()[0] if rest else ''
    return (maker, re.compile(r'(?<![\w])%s(?![\w])' % re.escape(token))) if token else None


def model_rules(cars):
    rules, seen = [], set()
    for car in cars:
        rule = _rule(car['title'])
        if rule and (rule[0], rule[1].pattern) not in seen:
            seen.add((rule[0], rule[1].pattern))
            rules.append(rule)
    return rules


def same_model(lot, rules):
    maker, model = lot['maker'].upper(), lot['model'].upper()
    return any(maker.startswith(m) and rx.search(model) for m, rx in rules)
