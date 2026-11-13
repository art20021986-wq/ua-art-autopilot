"""ua_order_book.py: the 8 delivery stages of an order (owner «да» 2026-11-12, CRM-PAYMENTS-001), was 6.

Only the STAGES tuple changes. The old keys keep their place (orders already in a stage stay valid); two stages are
added (korea_port, truck) and three are re-labelled to the delivery path of the sale contract. Refused when the file
is not the one LEAD-FOLDERS-001 installed.
"""
import hashlib

NAME = 'ua_order_book.py'
SHA256 = '06a3b4a5f2e20eedbf0254a1dfc5c7f59f03f4915fc83ac0dd98f562707f18cb'
OLD = ("STAGES = (('contract', 'Договор подписан'), ('bought', 'Авто выкуплено'), ('transit', 'В пути'),\n"
       "          ('georgia', 'В Грузии'), ('ukraine', 'В Украине'), ('delivered', 'Выдано клиенту'))\n")
NEW = ("STAGES = (('contract', 'Договор подписан'), ('bought', 'Авто выкуплено на аукционе'),\n"
       "          ('korea_port', 'В порту Кореи'), ('transit', 'На пароме в Грузию'), ('georgia', 'В порту Грузии'),\n"
       "          ('truck', 'Автовоз до Киева'), ('ukraine', 'Растаможка и сертификация'), ('delivered', 'Выдано клиенту'))\n")


def build(source):
    if hashlib.sha256(source).hexdigest() != SHA256:
        raise ValueError('ORDER_BOOK_CHANGED')
    text = source.decode('utf-8')
    if text.count(OLD) != 1:
        raise ValueError('ORDER_BOOK_STAGES')
    return text.replace(OLD, NEW).encode('utf-8')
