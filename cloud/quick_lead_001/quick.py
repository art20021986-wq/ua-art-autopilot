"""Short enquiry from a model page: name, phone and the page's model; readable in the owner inbox.

Installed as ua_order/quick.py. contract.normalize and crm.detail_view hand this schema here,
as they already do for v2; storage and notification stay schema-independent.
"""
from html import escape
import re
from uuid import UUID

from .catalog import COUNTRIES, LANGUAGES
from .contract import Invalid, text

SCHEMA = 'ua_order_request.quick.v1'
FIELDS = frozenset(('schema_version', 'request_id', 'config_version', 'purchase_country_code', 'model',
                    'customer_name', 'contact', 'lang', 'source_path', 'consent'))
# Only the site's model landing pages carry this form.
SOURCE_PATH = re.compile(r'/video/seo/(?:ua|ru)/[a-z0-9-]{1,100}\.html')


def phone(value):
    """International form; a Ukrainian number typed locally (0XX…, 380…) gets its +380 prefix."""
    value = text(value, 'contact', 7, 30)
    if not re.fullmatch(r'\+?[0-9 ()-]+', value):
        raise Invalid('contact')
    digits = re.sub(r'[ ()-]', '', value)
    if re.fullmatch(r'0[0-9]{9}', digits):
        digits = '+38' + digits
    elif re.fullmatch(r'380[0-9]{9}', digits):
        digits = '+' + digits
    if not re.fullmatch(r'\+[1-9][0-9]{6,14}', digits):
        raise Invalid('contact')
    return digits


def normalize(data, catalog, consent_version):
    if set(data) != FIELDS:
        raise Invalid('fields')
    try:
        request_id = str(UUID(data['request_id']))
    except (ValueError, AttributeError, TypeError) as exc:
        raise Invalid('request_id') from exc
    if data['config_version'] != catalog.version:
        raise Invalid('config_version')
    country, lang = data['purchase_country_code'], data['lang']
    if country not in COUNTRIES:
        raise Invalid('purchase_country_code')
    if lang not in LANGUAGES:
        raise Invalid('lang')
    if not isinstance(data['model'], str) or not catalog.model(country, data['model']):
        raise Invalid('model')
    contact = data['contact']
    if not isinstance(contact, dict) or set(contact) != {'phone'}:
        raise Invalid('contact')
    if not consent_version or data['consent'] != {'accepted': True, 'version': consent_version}:
        raise Invalid('consent')
    if not isinstance(data['source_path'], str) or not SOURCE_PATH.fullmatch(data['source_path']):
        raise Invalid('source_path')
    return dict(schema_version=SCHEMA, request_id=request_id, config_version=catalog.version,
                purchase_country_code=country, model=data['model'],
                customer_name=text(data['customer_name'], 'customer_name', 2),
                contact={'phone': phone(contact['phone'])}, lang=lang,
                source_path=data['source_path'], consent=dict(data['consent']))


def detail(row, catalog):
    data = row['data']
    country = catalog.country(data['purchase_country_code'])
    model = catalog.model(data['purchase_country_code'], data['model'])
    fields = [('Заявка', row['number']), ('Тип', 'Короткая заявка со страницы модели'),
              ('Клиент', data['customer_name']), ('Телефон', data['contact']['phone']),
              ('Страна подбора', country['name']['ru']), ('Модель', model['labels']['ru'] if model else data['model']),
              ('Страница', data['source_path'])]
    return {'text': '\n'.join(f'<b>{escape(key)}:</b> {escape(value)}' for key, value in fields),
            'buttons': [[('К заявкам', 'orders:list')]]}
