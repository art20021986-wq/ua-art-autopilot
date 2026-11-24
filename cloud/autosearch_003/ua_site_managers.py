"""Менеджеры сайта (AUTOSEARCH-003, владелец 17.11): отдельные логины, создаются в CRM-боте как клиенты аукционов.

Владелец: «Менеджера я добавляю по такому же принципу, как клиента… номер телефона, email — всё то же, что вводим
клиенту»; «Работа менеджера — не в боте CRM, а на сайте». Одна ответственность — записи менеджеров. Те же поля, тот же
пароль (scrypt с солью, показывается один раз), та же проверка входа, что у клиентов (ua_auction_clients), — но своя
база /home/Carix/auction_clients/managers.db: менеджер не клиент и в списках клиентов не появляется.
Телефон, уже занятый клиентом, менеджеру не дают (один логин — один человек).
"""
from pathlib import Path

import ua_auction_clients as clients

DB = Path('/home/Carix/auction_clients/managers.db')
ManagerError = clients.ClientError
phone = clients.phone


def create(surname, name, phone_number, email, city, staff_id, db=None):
    """Новый менеджер -> (запись, пароль показывается один раз). `staff_id` — кто из CRM создал."""
    if clients.get(phone_number) is not None:
        raise ManagerError('phone_exists')
    return clients.create(surname, name, phone_number, email, city, staff_id, db or DB)


def get(phone_number, db=None):
    return clients.get(phone_number, db or DB)


def all_managers(db=None):
    return clients.all_clients(db or DB)


def reset_password(phone_number, db=None):
    return clients.reset_password(phone_number, db or DB)


def set_blocked(phone_number, blocked, db=None):
    return clients.set_blocked(phone_number, blocked, db or DB)


def verify(phone_number, password, db=None):
    """Менеджер для верного входа активного менеджера, иначе None."""
    return clients.verify(phone_number, password, db or DB)


def session_key(phone_number, db=None):
    return clients.session_key(phone_number, db or DB)
