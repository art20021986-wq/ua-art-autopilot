"""Versioned preference catalogue and v2 validation; v1 enquiries stay readable."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import json
from pathlib import Path
import re
from uuid import UUID

from .catalog import COUNTRIES, LANGUAGES
from .contract import Invalid, text

SCHEMA = 'ua_order_request.v2'
CRITERIA = ('purchase_country_code', 'make', 'models', 'budget', 'vehicle_type',
            'year', 'mileage', 'fuel', 'drive', 'engine', 'colours', 'purchase_timing')
FIELDS = frozenset(('schema_version', 'request_id', 'config_version', 'preferences_version',
    'purchase_country_code', 'purchase_country_other', 'make', 'make_other', 'model_mode',
    'models', 'other_model', 'budget', 'vehicle_type', 'delivery_country', 'delivery_city',
    'customer_name', 'contact', 'year', 'mileage', 'fuel', 'drive', 'engine', 'colours',
    'colour_other', 'purchase_timing', 'comment', 'priority', 'lang', 'source_path', 'consent'))


@lru_cache(maxsize=1)
def directory():
    return json.loads(Path(__file__).with_name('preferences.json').read_text(encoding='utf-8'))


def export():
    return dict(directory(), current_year=datetime.now(timezone.utc).year)


def choice(value, values, field):
    if not isinstance(value, str) or value not in values:
        raise Invalid(field)
    return value


def record(value, keys, field):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise Invalid(field)
    return value


def integer(value, field, minimum=0, maximum=5_000_000):
    if isinstance(value, str):
        value = value.strip()
        # One consistent thousands separator; never infer a missing multiplier.
        if not re.fullmatch(r'[0-9]+|[0-9]{1,3}([ .,\u00a0\u202f])[0-9]{3}(?:\1[0-9]{3})*', value):
            raise Invalid(field)
        value = int(re.sub(r'[ .,\u00a0\u202f]', '', value))
    if type(value) is not int or not minimum <= value <= maximum:
        raise Invalid(field)
    return value


def litres(value, field):
    if type(value) not in (str, int, float) or not re.fullmatch(r'[0-9]{1,2}(?:[.,][0-9]{1,2})?', str(value).strip()):
        raise Invalid(field)
    try:
        result = Decimal(str(value).strip().replace(',', '.'))
    except InvalidOperation as exc:
        raise Invalid(field) from exc
    if not 0 < result <= 20:
        raise Invalid(field)
    return float(result)


def interval(value, field, convert, *, allow_any=False):
    record(value, ('from', 'to', 'any') if allow_any else ('from', 'to'), field)
    if allow_any and type(value['any']) is not bool:
        raise Invalid(field)
    if allow_any and value['any']:
        if value['from'] is not None or value['to'] is not None:
            raise Invalid(field)
        return dict(value)
    result = {bound: None if value[bound] is None else convert(value[bound], field) for bound in ('from', 'to')}
    if all(x is None for x in result.values()) or (all(x is not None for x in result.values()) and result['from'] > result['to']):
        raise Invalid(field)
    if allow_any:
        result['any'] = False
    return result


def multiple(value, field, options):
    if value is None or value == []:
        return None
    if not isinstance(value, list) or len(value) > len(options):
        raise Invalid(field)
    values = [choice(x, options, field) for x in value]
    if len(set(values)) != len(values) or ('any' in values and len(values) != 1):
        raise Invalid(field)
    # Stable ordering makes retries and equality independent of click order.
    return [x for x in options if x in values]


def normalize(data, catalog, consent_version):
    if not isinstance(data, dict) or set(data) != FIELDS or data.get('schema_version') != SCHEMA:
        raise Invalid('fields')
    config = directory()
    if data['config_version'] != catalog.version or data['preferences_version'] != config['version']:
        raise Invalid('config_version')
    try:
        request_id = str(UUID(data['request_id']))
    except (ValueError, AttributeError, TypeError) as exc:
        raise Invalid('request_id') from exc
    result = dict(data, request_id=request_id)
    result['lang'] = choice(data['lang'], LANGUAGES, 'lang')
    result['source_path'] = choice(data['source_path'], ('/podbor.html','/site/podbor.html','/video/podbor.html','/telegram'), 'source_path')
    if not consent_version or type(data['consent']) is not dict or data['consent'] != {'accepted': True, 'version': consent_version} or data['consent']['accepted'] is not True:
        raise Invalid('consent')
    country = choice(data['purchase_country_code'], (*COUNTRIES, 'other', 'help'), 'purchase_country_code')
    result['purchase_country_other'] = text(data['purchase_country_other'], 'purchase_country_other', 2 if country == 'other' else 0, 80)
    if country != 'other' and result['purchase_country_other']:
        raise Invalid('purchase_country_other')
    make = choice(data['make'], (*config['makes'], 'other', 'help'), 'make')
    result['make_other'] = text(data['make_other'], 'make_other', 2 if make == 'other' else 0, 80)
    if make != 'other' and result['make_other']:
        raise Invalid('make_other')
    mode = choice(data['model_mode'], ('selected', 'any', 'other', 'help'), 'models')
    models = data['models']
    if not isinstance(models, list) or len(models) > 100:
        raise Invalid('models')
    if mode == 'selected':
        if make not in config['makes'] or not models:
            raise Invalid('models')
        result['models'] = multiple(models, 'models', config['makes'][make]['models'])
    elif models:
        raise Invalid('models')
    if (make == 'help') != (mode == 'help'):
        raise Invalid('models')
    result['other_model'] = text(data['other_model'], 'other_model', 2 if mode == 'other' else 0, 120)
    if mode != 'other' and result['other_model']:
        raise Invalid('other_model')
    budget = record(data['budget'], ('mode', 'max', 'currency'), 'budget')
    choice(budget['currency'], ('USD',), 'budget')
    choice(budget['mode'], ('limit', 'help'), 'budget')
    result['budget'] = dict(budget)
    if budget['mode'] == 'limit':
        result['budget']['max'] = integer(budget['max'], 'budget', 1, 1_000_000_000)
    elif budget['max'] is not None:
        raise Invalid('budget')
    result['vehicle_type'] = choice(data['vehicle_type'], config['options']['vehicle_type'], 'vehicle_type')
    destination = choice(data['delivery_country'], config['options']['delivery_country'], 'delivery_country')
    city = record(data['delivery_city'], ('code','other'), 'delivery_city')
    choice(city['code'], (*config['cities'][destination], 'other'), 'delivery_city')
    result['delivery_city'] = dict(code=city['code'], other=text(city['other'], 'delivery_city', 2 if city['code']=='other' else 0))
    if city['code'] != 'other' and city['other']:
        raise Invalid('delivery_city')
    result['customer_name'] = text(data['customer_name'], 'customer_name', 2, 80)
    contact = record(data['contact'], ('method','value'), 'contact')
    method = choice(contact['method'], config['options']['contact_method'], 'contact')
    value = text(contact['value'], 'contact', 5, 80)
    if method == 'telegram' and value.startswith('@'):
        if not re.fullmatch(r'@[a-zA-Z][a-zA-Z0-9_]{4,31}', value):
            raise Invalid('contact')
        value = value.lower()
    else:
        if not re.fullmatch(r'\+[0-9 ()-]+', value):
            raise Invalid('contact')
        value = re.sub(r'[ ()-]', '', value)
        if not re.fullmatch(r'\+[1-9][0-9]{6,14}', value):
            raise Invalid('contact')
    result['contact'] = dict(method=method, value=value)
    result['year'] = interval(data['year'], 'year', lambda v,f:integer(v,f,1900,datetime.now(timezone.utc).year), allow_any=True)
    mileage = record(data['mileage'], ('max','any'), 'mileage')
    if type(mileage['any']) is not bool or (mileage['any'] and mileage['max'] is not None):
        raise Invalid('mileage')
    result['mileage'] = dict(any=mileage['any'], max=None if mileage['any'] else integer(mileage['max'], 'mileage'))
    for field in ('fuel', 'drive', 'colours'):
        result[field] = multiple(data[field], field, config['options'][field])
    result['engine'] = None if data['engine'] is None else interval(data['engine'], 'engine', litres)
    result['colour_other'] = text(data['colour_other'], 'colour_other', maximum=120)
    if 'other' not in (result['colours'] or []) and result['colour_other']:
        raise Invalid('colour_other')
    result['purchase_timing'] = None if data['purchase_timing'] is None else choice(data['purchase_timing'], config['options']['purchase_timing'], 'purchase_timing')
    result['comment'] = text(data['comment'], 'comment', maximum=3000)
    priority = data['priority']
    if not isinstance(priority, dict) or set(priority) - set(CRITERIA):
        raise Invalid('priority')
    result['priority'] = {k:choice(v, ('preferred','required'), 'priority') for k,v in priority.items()}
    for field in CRITERIA:
        if result[field] is None or result[field] in ('help','any') or result[field] == ['any']:
            result['priority'].pop(field, None)
        elif field in ('year','mileage') and result[field]['any']:
            result['priority'].pop(field, None)
        elif field == 'budget' and result[field]['mode']=='help':
            result['priority'].pop(field, None)
        elif field == 'models' and mode in ('help','any'):
            result['priority'].pop(field, None)
        else:
            result['priority'].setdefault(field, 'preferred')
    return result
