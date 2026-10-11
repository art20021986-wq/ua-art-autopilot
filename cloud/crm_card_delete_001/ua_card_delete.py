"""Удаление карточки автомобиля: сначала с сайта, затем из CRM.

Единственная ответственность модуля — порядок удаления, при котором сайт и
CRM не расходятся. Каталог сайта обновляет существующий издатель
(publikaciya.obnovit_katalog), как при «Скрыть от клиентов». Зависимости
передаются явно, поэтому модуль проверяется без бота и без сервера.
"""
from __future__ import annotations

from typing import NamedTuple


class Result(NamedTuple):
    deleted: bool
    text: str


def delete_card(cid, actor_id, *, db, publisher):
    card = db.get_card('cars', int(cid))
    if not card:
        return Result(False, 'Карточка уже удалена.')
    nomer = card.get('auto_number') or '#%d' % int(cid)
    if card.get('published'):
        db.update_card_field('cars', int(cid), 'published', 0, actor_id)
        try:
            ok, detail = publisher.obnovit_katalog()
        except Exception as exc:
            ok, detail = False, exc
        if ok is not True:
            db.update_card_field('cars', int(cid), 'published', card.get('published'), actor_id)
            return Result(False, 'Удаление отменено: не удалось убрать %s с сайта (%s). '
                                 'Карточка не изменена.' % (nomer, detail or 'каталог не прошёл проверку'))
    with db.connect() as connection:
        connection.execute('DELETE FROM cars WHERE id=?', (int(cid),))
    db.log_action(actor_id, 'card_delete', 'cars', int(cid), 'auto_number', nomer, None)
    return Result(True, 'Карточка %s удалена и убрана с сайта.' % nomer)
