"""Transport-independent validation; only the server supplies identity and time."""
import hashlib
import json
import re
import unicodedata
from uuid import UUID

from .catalog import COUNTRIES, LANGUAGES

SCHEMA = 'ua_order_request.v1'
MAX_BYTES = 32 * 1024
FIELDS = frozenset(('schema_version', 'request_id', 'config_version',
                   'purchase_country_code', 'model', 'other_model', 'budget',
                   'vehicle_type', 'delivery_country', 'delivery_city',
                   'customer_name', 'contact', 'comment', 'lang', 'source_path', 'consent'))


class Invalid(ValueError):
    def __init__(self, field):
        self.field = field
        super().__init__(field)


class Conflict(ValueError):
    pass


def text(value, field, minimum=0, maximum=80):
    if not isinstance(value, str):
        raise Invalid(field)
    value = unicodedata.normalize('NFC', value).strip()
    if not minimum <= len(value) <= maximum or any(
            unicodedata.category(c) in ('Cc', 'Cs') and c not in '\n\t' for c in value):
        raise Invalid(field)
    return value


def decode(raw):
    if len(raw) > MAX_BYTES:
        raise Invalid('body_size')
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise Invalid('duplicate_field')
            result[k] = v
        return result
    try:
        data = json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(Invalid('json')))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise Invalid('json') from exc
    if not isinstance(data, dict):
        raise Invalid('json')
    return data


def normalize(data, catalog, consent_version, *, verified_contact=False):
    if isinstance(data, dict) and data.get('schema_version') == 'ua_order_request.v2':
        from .preferences import normalize as normalize_preferences
        return normalize_preferences(data, catalog, consent_version)
    if not isinstance(data, dict) or set(data) - FIELDS:
        raise Invalid('fields')
    if data.get('schema_version') != SCHEMA:
        raise Invalid('schema_version')
    try:
        request_id = str(UUID(data.get('request_id', '')))
    except (ValueError, AttributeError, TypeError) as exc:
        raise Invalid('request_id') from exc
    if data.get('config_version') != catalog.version:
        raise Invalid('config_version')
    country = data.get('purchase_country_code')
    lang = data.get('lang', 'uk')
    if country not in COUNTRIES:
        raise Invalid('purchase_country_code')
    if lang not in LANGUAGES:
        raise Invalid('lang')
    model = text(data.get('model', ''), 'model', maximum=120)
    other = text(data.get('other_model', ''), 'other_model', maximum=120)
    if bool(model) == bool(other) or (model and not catalog.model(country, model)):
        raise Invalid('model')
    if other and len(other) < 2:
        raise Invalid('other_model')
    budget = data.get('budget')
    if not isinstance(budget, dict) or set(budget) != {'code', 'currency'}:
        raise Invalid('budget')
    if not isinstance(budget['code'], str) or budget['code'] not in catalog.choices('budgets') or budget['currency'] != 'USD':
        raise Invalid('budget')
    if not isinstance(data.get('vehicle_type'), str) or data.get('vehicle_type') not in catalog.choices('vehicle_types'):
        raise Invalid('vehicle_type')
    contact = data.get('contact')
    if not isinstance(contact, dict) or set(contact) - {'phone', 'whatsapp', 'telegram'}:
        raise Invalid('contact')
    clean_contact = {}
    for key, raw in contact.items():
        value = text(raw, 'contact', maximum=80)
        if not value:
            continue
        if key in ('phone', 'whatsapp'):
            if not re.fullmatch(r'\+?[0-9 ()-]+', value):
                raise Invalid('contact')
            value = re.sub(r'[ ()-]', '', value)
            if not re.fullmatch(r'\+?[0-9]{7,15}', value):
                raise Invalid('contact')
        else:
            value = value.removeprefix('@')
            if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]{4,31}', value):
                raise Invalid('contact')
            value = value.lower()
        clean_contact[key] = value
    if not clean_contact and not verified_contact:
        raise Invalid('contact')
    consent = data.get('consent')
    if (not consent_version or not isinstance(consent, dict)
            or type(consent.get('accepted')) is not bool
            or consent != {'accepted': True, 'version': consent_version}):
        raise Invalid('consent')
    # A path contains neither contact details, query strings nor an external URL.
    source_path = data.get('source_path', '/video/podbor.html')
    if source_path not in ('/podbor.html', '/site/podbor.html', '/video/podbor.html', '/telegram'):
        raise Invalid('source_path')
    return dict(schema_version=SCHEMA, request_id=request_id, config_version=catalog.version,
                purchase_country_code=country, model=model, other_model=other,
                budget=dict(budget), vehicle_type=data['vehicle_type'],
                delivery_country=text(data.get('delivery_country'), 'delivery_country', 2),
                delivery_city=text(data.get('delivery_city'), 'delivery_city', 2),
                customer_name=text(data.get('customer_name'), 'customer_name', 2),
                contact=clean_contact, comment=text(data.get('comment', ''), 'comment', maximum=2000),
                lang=lang, source_path=source_path, consent=dict(data['consent']))


def encoded(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(data):
    return hashlib.sha256(encoded(data).encode()).hexdigest()
