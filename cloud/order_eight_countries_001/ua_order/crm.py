"""A flat folder view; the adapter must authorize each open/refresh action."""
from html import escape
from . import preference_summary

FOLDER_LABEL = '📁 Авто под заказ'


def list_view(repository, catalog, *, before=None, menu_callback='menu'):
    rows, cursor = repository.list_requests(before=before)
    buttons = []
    for row in rows:
        data = row['data']
        country = preference_summary.country_label(data, catalog)
        # Telegram inline labels are plain text, never HTML.
        name = ' '.join(data['customer_name'].split())
        buttons.append([(f'{name[:45]} · {country}', f'orders:open:{row["id"]}')])
    if cursor:
        buttons.append([('Далее →', f'orders:list:{cursor}')])
    buttons.append([('Обновить', 'orders:list'), ('В меню', menu_callback)])
    return {'text': 'Авто под заказ' if rows else 'Пока нет заявок', 'buttons': buttons}


def detail_view(row, catalog):
    data = row['data']
    if data.get('schema_version') == 'ua_order_request.v2':
        return preference_summary.detail(row, catalog)
    country = preference_summary.country_label(data, catalog)
    model = catalog.model(data['purchase_country_code'], data['model']) if data['model'] else None
    fields = [('Заявка', row['number']), ('Клиент', data['customer_name']),
              ('Страна подбора', country), ('Модель', model['labels']['ru'] if model else data['other_model']),
              ('Бюджет', catalog.choices('budgets')[data['budget']['code']]['ru']),
              ('Тип', catalog.choices('vehicle_types')[data['vehicle_type']]['ru']),
              ('Доставка', f'{data["delivery_country"]}, {data["delivery_city"]}')]
    fields.extend((key, value) for key, value in data['contact'].items())
    if row['telegram_user_id']:
        fields.append(('Telegram ID', row['telegram_user_id']))
    fields.append(('Пожелания', data['comment']))
    return {'text': '\n'.join(f'<b>{escape(key)}:</b> {escape(value)}' for key, value in fields if value),
            'buttons': [[('К заявкам', 'orders:list')]]}
