"""Автопоиск на сайте (AUTOSEARCH-002, владелец 17.11): ответы /api/auction/alerts* для вошедшего пользователя.

ua_auction_web проверяет вход, Origin и JSON и передаёт сюда (action, данные, вошедший логин):
  GET  alerts          -> только менеджеру: его клиенты, их запросы, списки для формы (из опубликованного lots.json)
  POST alerts/add      {client, group_link, условия} -> запрос на поиск для своего клиента (до 10 у клиента)
  POST alerts/delete   {id}                          -> удалить запрос своего клиента
  POST alerts/seen     {lot, title}                  -> вошедший клиент открыл лот на korea.html (учёт просмотров)
Менеджер — логин сайта с правами из CRM-бота («👔 Права менеджера на сайте»); видит клиентов, которых оформил его
сотрудник CRM, владелец — всех. Только стандартная библиотека.
"""
import os
import threading

import ua_lot_alerts as alerts

GET = ('alerts',)
POST = ('alerts/add', 'alerts/delete', 'alerts/seen')
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


def _clients(right):
    import ua_auction_clients as store
    return alerts.own_clients(right, store.all_clients(), alerts.manager_phones())


def _state(right):
    people = {c['phone']: '%s %s' % (c['surname'], c['name']) for c in _clients(right)}
    counts = alerts.found_counts()
    return {'manager': right['staff_name'], 'limit': alerts.MAX_REQUESTS,
            'clients': [{'phone': phone, 'name': name} for phone, name in sorted(people.items(), key=lambda x: x[1])],
            'requests': [{'id': r['id'], 'client': r['client_phone'], 'client_name': people[r['client_phone']],
                          'criteria': r['criteria'], 'group_link': r['group_link'], 'found': counts.get(r['id'], 0)}
                         for r in alerts.requests() if r['client_phone'] in people]}


def handle(action, data, client):
    """(статус, тело) для вошедшего логина."""
    try:
        if action == 'alerts/seen':
            alerts.record_view(client['phone'], data['lot'], data.get('title', ''))
            return '200 OK', {'ok': True}
        right = alerts.manager(client['phone'])
        if right is None:
            return '403 Forbidden', {'error': 'manager'}
        if action == 'alerts':
            return '200 OK', dict(_state(right), options=options())
        if action == 'alerts/add':
            if str(data.get('client')) not in {c['phone'] for c in _clients(right)}:
                return '400 Bad Request', {'error': 'client'}
            alerts.add_request(str(data['client']), right['staff_id'], data.get('group_link'), data)
        elif action == 'alerts/delete':
            alerts.delete_request(data['id'], {c['phone'] for c in _clients(right)})
        return '200 OK', _state(right)
    except alerts.AlertError as error:
        return '400 Bad Request', {'error': str(error)}
    except (KeyError, TypeError, ValueError):
        return '400 Bad Request', {'error': 'request'}
