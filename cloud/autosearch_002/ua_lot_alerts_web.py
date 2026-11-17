"""Автопоиск на сайте (AUTOSEARCH-002, владелец 17.11): ответы /api/auction/alerts* для вошедшего пользователя.

ua_auction_web проверяет вход, Origin и JSON и передаёт сюда (action, данные, вошедший логин):
  GET  alerts          -> только менеджеру: его клиенты, их запросы, сообщения для групп WhatsApp (приветствие и новые
                          подходящие лоты, ещё не отправленные), списки для формы (из опубликованного lots.json)
  POST alerts/add      {client, group_link, условия} -> запрос на поиск для своего клиента (до 10 у клиента)
  POST alerts/delete   {id}                          -> удалить запрос своего клиента
  POST alerts/sent     {id, lot?}                    -> менеджер отправил в группу приветствие (без lot) или лот
  POST alerts/seen     {lot, title}                  -> вошедший клиент открыл лот на korea.html (учёт просмотров)
Менеджер — логин сайта с правами из CRM-бота («👔 Права менеджера на сайте»); видит клиентов, которых оформил его
сотрудник CRM, владелец — всех. Владелец 17.11: менеджеру Telegram «пока не нужен» — всё в кабинете на сайте.
Только стандартная библиотека.
"""
import os
import threading

import ua_lot_alerts as alerts
import ua_lot_alerts_whatsapp as whatsapp

GET = ('alerts',)
POST = ('alerts/add', 'alerts/delete', 'alerts/sent', 'alerts/seen')
SHOWN = 10  # новых лотов на запрос за раз; остальные — числом
_cache, _lock = {}, threading.Lock()


def _lots(path=None):
    """(лоты, списки для формы) опубликованного списка; пересчёт только при новом файле."""
    path = str(path or alerts.LOTS)
    try:
        stamp = os.stat(path).st_mtime_ns
    except OSError:
        return [], {'makers': {}, 'years': [], 'fuels': [], 'colors': []}
    with _lock:
        if _cache.get('stamp') != (path, stamp):
            _, lots = alerts.read_lots(path)
            makers = {}
            for lot in lots:
                if lot.get('maker') and lot.get('title'):
                    makers.setdefault(lot['maker'], set()).add(lot['title'])
            _cache.update(stamp=(path, stamp), lots=lots, options={
                'makers': {maker: sorted(titles) for maker, titles in sorted(makers.items())},
                'years': sorted({lot['year'] for lot in lots if lot.get('year')}),
                'fuels': [f for f in alerts.FUELS if any(lot.get('fuel') == f for lot in lots)],
                'colors': [c for c in alerts.COLORS if any(lot.get('color') == c for lot in lots)]})
        return _cache['lots'], _cache['options']


def options(path=None):
    return _lots(path)[1]


def _clients(right):
    import ua_auction_clients as store
    return alerts.own_clients(right, store.all_clients(), alerts.manager_phones())


def _message(request, name, kind, text, lot=None):
    return {'id': request['id'], 'client_name': name, 'kind': kind, 'lot': lot, 'text': text,
            'share': whatsapp.share_url(text), 'group_link': request['group_link']}


def messages(own, people, lots):
    """Неотправленные сообщения по запросам: сначала приветствие, затем новые подходящие лоты (до SHOWN на запрос)."""
    result, more = [], {}
    for request in own:
        name = people[request['client_phone']]
        if not request['welcomed']:
            result.append(_message(request, name, 'welcome', whatsapp.welcome(alerts.describe(request['criteria']))))
            continue  # лоты — после приветствия
        found = [lot for lot in lots if alerts.matches(request['criteria'], lot)]
        fresh = set(alerts.unposted(request['id'], [lot['id'] for lot in found]))
        new = sorted((lot for lot in found if lot['id'] in fresh), key=lambda lot: lot.get('auction_start', ''))
        result += [_message(request, name, 'lot', whatsapp.lot(lot), lot['id']) for lot in new[:SHOWN]]
        if len(new) > SHOWN:
            more[request['id']] = len(new) - SHOWN
    return result, more


def _state(right):
    people = {c['phone']: '%s %s' % (c['surname'], c['name']) for c in _clients(right)}
    own = [r for r in alerts.requests() if r['client_phone'] in people]
    counts = alerts.posted_counts()
    lots, form = _lots()
    pending, more = messages(own, people, lots)
    return {'manager': right['staff_name'], 'limit': alerts.MAX_REQUESTS, 'options': form,
            'clients': [{'phone': phone, 'name': name} for phone, name in sorted(people.items(), key=lambda x: x[1])],
            'requests': [{'id': r['id'], 'client': r['client_phone'], 'client_name': people[r['client_phone']],
                          'criteria': r['criteria'], 'group_link': r['group_link'], 'sent': counts.get(r['id'], 0),
                          'more': more.get(r['id'], 0)} for r in own],
            'messages': pending}


def handle(action, data, client):
    """(статус, тело) для вошедшего логина."""
    try:
        if action == 'alerts/seen':
            alerts.record_view(client['phone'], data['lot'], data.get('title', ''))
            return '200 OK', {'ok': True}
        right = alerts.manager(client['phone'])
        if right is None:
            return '403 Forbidden', {'error': 'manager'}
        if action == 'alerts/add':
            if str(data.get('client')) not in {c['phone'] for c in _clients(right)}:
                return '400 Bad Request', {'error': 'client'}
            alerts.add_request(str(data['client']), right['staff_id'], data.get('group_link'), data)
        elif action == 'alerts/delete':
            alerts.delete_request(data['id'], {c['phone'] for c in _clients(right)})
        elif action == 'alerts/sent':
            mine = {c['phone'] for c in _clients(right)}
            request = next((r for r in alerts.requests() if r['id'] == int(data['id'])), None)
            if request is None or request['client_phone'] not in mine:
                return '400 Bad Request', {'error': 'request'}
            if data.get('lot'):
                alerts.record_posted(request['id'], [str(data['lot'])[:40]])
            else:
                alerts.mark_welcomed(request['id'])
        return '200 OK', _state(right)
    except alerts.AlertError as error:
        return '400 Bad Request', {'error': str(error)}
    except (KeyError, TypeError, ValueError):
        return '400 Bad Request', {'error': 'request'}
