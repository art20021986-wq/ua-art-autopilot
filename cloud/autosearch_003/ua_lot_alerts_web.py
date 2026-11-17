"""Автопоиск на сайте (AUTOSEARCH-003, владелец 17.11): ответы /api/auction/alerts* для вошедшего пользователя.

ua_auction_web проверяет вход, Origin и JSON и передаёт сюда (action, данные, вошедший логин):
  GET  alerts          -> только менеджеру сайта: его клиенты, их запросы, сообщения для групп WhatsApp (приветствие и
                          новые подходящие лоты, ещё не отправленные), списки для формы (из опубликованного lots.json)
  POST alerts/contact  {name, phone}                 -> менеджер добавляет своего клиента (ПІБ и телефон)
  POST alerts/add      {contact, group_link, условия} -> запрос на поиск для своего клиента (до 10 у клиента)
  POST alerts/delete   {id}                          -> удалить свой запрос
  POST alerts/sent     {id, lot?}                    -> менеджер отправил в группу приветствие (без lot) или лот
  POST alerts/seen     {lot, title}                  -> вошедший клиент открыл лот на korea.html (учёт просмотров)
Менеджер сайта — отдельный логин (ua_site_managers, role «manager»); работает только на сайте (владелец 17.11).
Только стандартная библиотека.
"""
import os
import threading

import ua_lot_alerts as alerts
import ua_lot_alerts_whatsapp as whatsapp

GET = ('alerts',)
POST = ('alerts/contact', 'alerts/add', 'alerts/delete', 'alerts/sent', 'alerts/seen')
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


def _message(request, name, kind, text, lot=None):
    return {'id': request['id'], 'client_name': name, 'kind': kind, 'lot': lot, 'text': text,
            'share': whatsapp.share_url(text), 'group_link': request['group_link']}


def messages(own, people, lots):
    """Неотправленные сообщения по запросам (`people`: id клиента менеджера -> ПІБ): сначала приветствие, затем новые подходящие лоты (до SHOWN на запрос)."""
    result, more = [], {}
    for request in own:
        name = people[request['contact_id']]
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


def _state(manager):
    me = manager['phone']
    people = {c['id']: c for c in alerts.contacts(me)}
    own = [r for r in alerts.requests(me) if r['contact_id'] in people]
    counts = alerts.posted_counts()
    lots, form = _lots()
    pending, more = messages(own, {k: c['name'] for k, c in people.items()}, lots)
    return {'manager': '%s %s' % (manager['surname'], manager['name']), 'limit': alerts.MAX_REQUESTS, 'options': form,
            'clients': [{'id': c['id'], 'name': c['name'], 'phone': c['phone']} for c in people.values()],
            'requests': [{'id': r['id'], 'contact': r['contact_id'], 'client_name': people[r['contact_id']]['name'],
                          'criteria': r['criteria'], 'group_link': r['group_link'], 'sent': counts.get(r['id'], 0),
                          'more': more.get(r['id'], 0)} for r in own],
            'messages': pending}


def handle(action, data, user):
    """(статус, тело) для вошедшего логина; всё, кроме учёта просмотров, — только менеджеру сайта."""
    try:
        if action == 'alerts/seen':
            alerts.record_view(user['phone'], data['lot'], data.get('title', ''))
            return '200 OK', {'ok': True}
        if user.get('role') != 'manager':
            return '403 Forbidden', {'error': 'manager'}
        me = user['phone']
        if action == 'alerts/contact':
            alerts.add_contact(me, data.get('name'), data.get('phone'))
        elif action == 'alerts/add':
            alerts.add_request(me, data['contact'], data.get('group_link'), data)
        elif action == 'alerts/delete':
            alerts.delete_request(me, data['id'])
        elif action == 'alerts/sent':
            request = alerts.own_request(me, data['id'])
            if request is None:
                return '400 Bad Request', {'error': 'request'}
            if data.get('lot'):
                alerts.record_posted(request['id'], [str(data['lot'])[:40]])
            else:
                alerts.mark_welcomed(request['id'])
        return '200 OK', _state(user)
    except alerts.AlertError as error:
        return '400 Bad Request', {'error': str(error)}
    except (KeyError, TypeError, ValueError):
        return '400 Bad Request', {'error': 'request'}
