"""Автопоиск в «Мій кабінет» (AUTOSEARCH-001): ответы /api/auction/alerts* для вошедшего клиента.

ua_auction_web проверяет вход, Origin и JSON и передаёт сюда (action, данные, клиент):
  GET  alerts          -> поиски клиента, Telegram подключён или нет, списки для формы (из опубликованного lots.json)
  POST alerts/add      {условия}  -> сохранить поиск (до 10)
  POST alerts/delete   {"id"}     -> удалить свой поиск
  POST alerts/telegram {}         -> одноразовая ссылка t.me/<клиентский бот>?start=<код> (15 мин)
  POST alerts/unlink   {}         -> отключить Telegram
  POST alerts/seen     {"lot", "title"} -> клиент открыл лот на korea.html (учёт просмотров, владелец 17.11)
Только стандартная библиотека.
"""
import os
import threading

import ua_lot_alerts as alerts

BOT = 'UA_artcompany_LLC_bot'
GET = ('alerts',)
POST = ('alerts/add', 'alerts/delete', 'alerts/telegram', 'alerts/unlink', 'alerts/seen')
_cache, _lock = {}, threading.Lock()


def options(path=None):
    """Марки -> модели, годы, топливо, цвета из опубликованного списка; пересчёт только при новом файле."""
    path = str(path or alerts.LOTS)
    try:
        stamp = os.stat(path).st_mtime_ns
    except OSError:
        return {'makers': {}, 'years': [], 'fuels': [], 'colors': []}
    with _lock:
        if _cache.get('stamp') != (path, stamp):
            _, lots = alerts.read_lots(path)
            makers = {}
            for lot in lots:
                if lot.get('maker') and lot.get('title'):
                    makers.setdefault(lot['maker'], set()).add(lot['title'])
            _cache.update(stamp=(path, stamp), value={
                'makers': {maker: sorted(titles) for maker, titles in sorted(makers.items())},
                'years': sorted({lot['year'] for lot in lots if lot.get('year')}),
                'fuels': [f for f in alerts.FUELS if any(lot.get('fuel') == f for lot in lots)],
                'colors': [c for c in alerts.COLORS if any(lot.get('color') == c for lot in lots)]})
        return _cache['value']


def _state(phone):
    counts = alerts.sent_counts(phone)
    return {'searches': [{'id': s['id'], 'criteria': s['criteria'], 'sent': counts.get(s['id'], 0)}
                         for s in alerts.searches(phone)],
            'telegram': alerts.chat(phone) is not None, 'limit': alerts.MAX_SEARCHES}


def handle(action, data, client):
    """(статус, тело) для вошедшего клиента."""
    phone = client['phone']
    try:
        if action == 'alerts':
            return '200 OK', dict(_state(phone), options=options())
        if action == 'alerts/add':
            alerts.add_search(phone, data)
        elif action == 'alerts/delete':
            alerts.delete_search(phone, data['id'])
        elif action == 'alerts/telegram':
            return '200 OK', {'url': 'https://t.me/%s?start=%s' % (BOT, alerts.new_code(phone))}
        elif action == 'alerts/unlink':
            alerts.unlink(phone)
        elif action == 'alerts/seen':
            alerts.record_view(phone, data['lot'], data.get('title', ''))
            return '200 OK', {'ok': True}
        return '200 OK', _state(phone)
    except alerts.AlertError as error:
        return '400 Bad Request', {'error': str(error)}
    except (KeyError, TypeError, ValueError):
        return '400 Bad Request', {'error': 'request'}
