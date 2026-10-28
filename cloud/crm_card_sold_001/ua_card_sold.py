"""Отметка «Продано»: карточка остаётся в CRM, машина уходит из каталога сайта.

Единственная ответственность модуля — порядок действий, при котором сайт и
CRM не расходятся. Каталог сайта обновляет существующий издатель
(publikaciya.obnovit_katalog), как при «Скрыть от клиентов». Если каталог
не обновился, карточка возвращается как была. Зависимости передаются явно,
поэтому модуль проверяется без бота и без сервера.
"""
from __future__ import annotations

from typing import NamedTuple

FIELDS = ('published', 'status')


class Result(NamedTuple):
    sold: bool
    text: str


def mark_sold(cid, actor_id, *, db, publisher):
    cid = int(cid)
    card = db.get_card('cars', cid)
    if not card:
        return Result(False, 'Карточка не найдена.')
    nomer = card.get('auto_number') or '#%d' % cid
    before = {field: card.get(field) for field in FIELDS}
    # Снять с показа раньше смены статуса: каталог не увидит «проданную» машину.
    db.update_card_field('cars', cid, 'published', 0, actor_id)
    db.update_card_field('cars', cid, 'status', 'sold', actor_id)
    # Каталог пересобирается всегда: так повторное нажатие убирает и машину,
    # оставшуюся на сайте после прежней отметки.
    try:
        ok, detail = publisher.obnovit_katalog()
    except Exception as exc:
        ok, detail = False, exc
    if ok is not True:
        after = db.get_card('cars', cid) or {}
        for field in reversed(FIELDS):
            if after.get(field) != before[field]:
                db.update_card_field('cars', cid, field, before[field], actor_id)
        return Result(False, 'Не получилось убрать %s с сайта (%s). Карточка не изменена, '
                             'попробуйте ещё раз.' % (nomer, detail or 'каталог не прошёл проверку'))
    return Result(True, 'Отмечено: %s продана. Из каталога убрана.' % nomer)
