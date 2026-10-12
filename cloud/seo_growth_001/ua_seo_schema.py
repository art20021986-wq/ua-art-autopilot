"""schema.org JSON-LD for public pages. Pure: facts in, one <script> block out."""
import json

ORIGIN = 'https://www.uaart.com.ua'
SCRIPT_ID = 'ua-seo-ld'
PHONE = '+380992222002'
MAP = 'https://maps.app.goo.gl/4HvzWMdCp1QT2F9CA'
STREET = {'ru': 'ул. Победы 20', 'uk': 'вул. Перемоги, 20'}
CITY = {'ru': 'Киев', 'uk': 'Київ'}


def dealer(lang):
    return {'@type': 'AutoDealer', '@id': ORIGIN + '/#dealer', 'name': 'UA ART COMPANY',
            'url': ORIGIN + '/video/index.html', 'telephone': PHONE, 'hasMap': MAP,
            'image': ORIGIN + '/video/brand/ua-art/share-preview-20260928.jpg',
            'address': {'@type': 'PostalAddress', 'streetAddress': STREET[lang],
                        'addressLocality': CITY[lang], 'addressCountry': 'UA'}}


def breadcrumbs(items):
    """items: [(name, absolute url), ...] from home to the current page."""
    return {'@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': i, 'name': name, 'item': url}
        for i, (name, url) in enumerate(items, 1)]}


def car(facts):
    """Car offer from public card facts; a missing fact is left out, never guessed."""
    value = {'@type': ['Product', 'Car'], '@id': facts['url'] + '#car', 'name': facts['name'],
             'url': facts['url'], 'sku': facts['code']}
    if facts.get('image'):
        value['image'] = [facts['image']]
    if facts.get('key'):
        value['brand'] = {'@type': 'Brand', 'name': facts['key'][0]}
        value['model'] = facts['key'][1]
    if facts.get('year'):
        value['vehicleModelDate'] = str(facts['year'])
    if facts.get('mileage_km') is not None:
        value['mileageFromOdometer'] = {'@type': 'QuantitativeValue', 'value': facts['mileage_km'],
                                        'unitCode': 'KMT'}
    if facts.get('price_usd'):
        value['offers'] = {'@type': 'Offer', 'url': facts['url'], 'price': facts['price_usd'],
                           'priceCurrency': 'USD', 'itemCondition': 'https://schema.org/UsedCondition',
                           'availability': 'https://schema.org/InStock' if facts.get('stage') == 4
                           else 'https://schema.org/PreOrder',
                           'seller': {'@id': ORIGIN + '/#dealer'}}
    return value


def item_list(cars):
    return {'@type': 'ItemList', 'itemListElement': [
        {'@type': 'ListItem', 'position': i, 'url': c['url'], 'name': c['name']}
        for i, c in enumerate(cars, 1)]}


def script(*nodes):
    """One JSON-LD graph; '</' is escaped so page text can never close the script."""
    graph = json.dumps({'@context': 'https://schema.org', '@graph': list(nodes)},
                       ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    return '<script type="application/ld+json" id="%s">%s</script>' % (SCRIPT_ID, graph.replace('</', '<\\/'))
