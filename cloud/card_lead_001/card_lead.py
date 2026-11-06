"""Enquiry from a car card on the site: name, phone and the card's car code (LEAD-FOLDERS-001).

Installed as ua_order/card_lead.py. The card's single button «Связаться с менеджером» opens the same short
dialog as the order page (name + phone); contract.normalize and crm hand this schema here, as they do for
quick.v1, so storage and notification stay schema-independent.
"""
from html import escape
import re
from uuid import UUID

from .contract import Invalid, text
from .quick import phone
from .catalog import LANGUAGES

SCHEMA = 'ua_order_request.card.v1'
FIELDS = frozenset(('schema_version', 'request_id', 'config_version', 'car_code', 'customer_name', 'contact', 'lang',
                    'source_path', 'consent'))
CODE = re.compile(r'UA-[0-9]{4,6}')
# The card page itself, in any of its published versions (/video/, /video/ua/, /video/ru/, /site/).
PAGE = re.compile(r'/(?:video|site)/(?:(?:ua|ru)/)?(UA-[0-9]{4,6})\.html')
KIND = 'Связаться с менеджером (карточка авто)'


def normalize(data, catalog, consent_version):
    if set(data) != FIELDS:
        raise Invalid('fields')
    try:
        request_id = str(UUID(data['request_id']))
    except (ValueError, AttributeError, TypeError) as exc:
        raise Invalid('request_id') from exc
    if data['config_version'] != catalog.version:
        raise Invalid('config_version')
    code = data['car_code']
    if not isinstance(code, str) or not CODE.fullmatch(code):
        raise Invalid('car_code')
    page = PAGE.fullmatch(data['source_path']) if isinstance(data['source_path'], str) else None
    if not page or page.group(1) != code:
        raise Invalid('source_path')
    if data['lang'] not in LANGUAGES:
        raise Invalid('lang')
    contact = data['contact']
    if not isinstance(contact, dict) or set(contact) != {'phone'}:
        raise Invalid('contact')
    if not consent_version or data['consent'] != {'accepted': True, 'version': consent_version}:
        raise Invalid('consent')
    return dict(schema_version=SCHEMA, request_id=request_id, config_version=catalog.version, car_code=code,
                customer_name=text(data['customer_name'], 'customer_name', 2), contact={'phone': phone(contact['phone'])},
                lang=data['lang'], source_path=data['source_path'], consent=dict(data['consent']))


def label(data):
    """What the enquiry is about, for one-line lists: the car code."""
    return data['car_code']


def detail(row):
    data = row['data']
    fields = [('Заявка', row['number']), ('Тип', KIND), ('Клиент', data['customer_name']),
              ('Телефон', data['contact']['phone']), ('Авто', data['car_code']), ('Страница', data['source_path'])]
    return {'text': '\n'.join(f'<b>{escape(key)}:</b> {escape(value)}' for key, value in fields),
            'buttons': [[('К заявкам', 'orders:list')]]}
