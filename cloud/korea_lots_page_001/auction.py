"""Access request from the «Korea online auctions» page: name and phone, optionally the chosen lot;
readable in the owner inbox.

Installed as ua_order/auction.py. contract.normalize and crm.detail_view hand this schema here,
as they already do for quick.v1 and card.v1; storage and notification stay schema-independent.
"""
from html import escape
import re
from uuid import UUID

from .catalog import LANGUAGES
from .contract import Invalid, text
from .quick import phone

SCHEMA = 'ua_order_request.auction.v1'
FIELDS = frozenset(('schema_version', 'request_id', 'config_version', 'purchase_country_code',
                    'customer_name', 'contact', 'lang', 'source_path', 'consent'))
AUCTIONS = {'korea': 'Аукционы Кореи онлайн'}  # Japan and others later (owner 2026-11-10)
SOURCE_PATHS = frozenset(('/video/korea.html',))
LOT_ID = re.compile(r'[0-9]{6,20}')  # the auction's lot id (video/korea/lots.json)


def lot(value):
    """Optional chosen lot: {'id': digits, 'title': short text}."""
    if not isinstance(value, dict) or set(value) != {'id', 'title'} or not isinstance(value['id'], str) \
            or not LOT_ID.fullmatch(value['id']):
        raise Invalid('lot')
    return {'id': value['id'], 'title': text(value['title'], 'lot', 2)}


def normalize(data, catalog, consent_version):
    if not FIELDS <= set(data) <= FIELDS | {'lot'}:
        raise Invalid('fields')
    try:
        request_id = str(UUID(data['request_id']))
    except (ValueError, AttributeError, TypeError) as exc:
        raise Invalid('request_id') from exc
    if data['config_version'] != catalog.version:
        raise Invalid('config_version')
    if data['purchase_country_code'] not in AUCTIONS:
        raise Invalid('purchase_country_code')
    if data['lang'] not in LANGUAGES:
        raise Invalid('lang')
    contact = data['contact']
    if not isinstance(contact, dict) or set(contact) != {'phone'}:
        raise Invalid('contact')
    if not consent_version or data['consent'] != {'accepted': True, 'version': consent_version}:
        raise Invalid('consent')
    if data['source_path'] not in SOURCE_PATHS:
        raise Invalid('source_path')
    value = dict(schema_version=SCHEMA, request_id=request_id, config_version=catalog.version,
                 purchase_country_code=data['purchase_country_code'],
                 customer_name=text(data['customer_name'], 'customer_name', 2),
                 contact={'phone': phone(contact['phone'])}, lang=data['lang'],
                 source_path=data['source_path'], consent=dict(data['consent']))
    if 'lot' in data:
        value['lot'] = lot(data['lot'])
    return value


def label(data):
    """Plain-text label in the CRM enquiry list (Telegram inline labels are never HTML)."""
    return 'Аукционы онлайн: ' + {'korea': 'Корея'}.get(data.get('purchase_country_code'), '—')


def detail(row, catalog):
    data = row['data']
    fields = [('Заявка', row['number']), ('Тип', 'Доступ к аукционам онлайн'),
              ('Аукционы', AUCTIONS.get(data['purchase_country_code'], data['purchase_country_code'])),
              *([('Авто', '%s (лот %s)' % (data['lot']['title'], data['lot']['id']))] if data.get('lot') else []),
              ('Клиент', data['customer_name']), ('Телефон', data['contact']['phone']),
              ('Страница', data['source_path'])]
    return {'text': '\n'.join(f'<b>{escape(str(key))}:</b> {escape(str(value))}' for key, value in fields),
            'buttons': [[('К заявкам', 'orders:list')]]}
