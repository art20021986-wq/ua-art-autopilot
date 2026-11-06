"""Leads of the client bot desk in one shape (LEAD-FOLDERS-001): where each came from, who, what about.

Two sources, both read only: the order package enquiries (site order form, short forms, the car card button, the
client bot's order flow) and the client bot's own car enquiries («Бронь», «Вопрос по машине») that visits.py keeps.
A lead is named by a stable text key: 'or:<id>' or 'bot:<hash of user, time and kind>'.
"""
from dataclasses import dataclass
import datetime
import hashlib

import ua_lead_folders as folders

MAX_PAGES = 25
BOT_KINDS = {'бронь': ('Бронь в боте', folders.STOCK), 'вопрос': ('Вопрос в боте', folders.STOCK),
             'подбор под заказ': ('Подбор в боте', folders.GENERAL)}


@dataclass(frozen=True)
class Lead:
    key: str
    folder: str
    created_at: int
    name: str
    phone: str
    telegram: str
    subject: str  # the car, model or country the lead is about
    source: str  # where it came from, readable
    detail: str  # full HTML text for the lead card


def _clean(value):
    return ' '.join(str(value or '').split())


def from_enquiry(row, catalog, detail_view):
    """An order package enquiry (repository.detail/list_requests row)."""
    data = row['data']
    contact = data.get('contact') or {}
    folder = folders.of_enquiry(data)
    if data.get('schema_version') == folders.CARD_SCHEMA:
        subject, source = data['car_code'], 'Карточка авто на сайте'
    else:
        subject = _model(data, catalog) or folders.label(folder)
        source = 'Заявка %s' % ('из бота' if row.get('channel') == 'telegram_bot' else 'с сайта')
    telegram = contact.get('telegram') or (contact.get('value') if contact.get('method') == 'telegram' else '')
    phone = contact.get('phone') or (contact.get('value') if contact.get('method') in ('phone', 'viber', 'whatsapp') else '')
    return Lead(key='or:%d' % row['id'], folder=folder, created_at=int(row['created_at']),
                name=_clean(data.get('customer_name')) or 'без имени', phone=_clean(phone), telegram=_clean(telegram),
                subject=_clean(subject), source='%s %s' % (source, row['number']),
                detail=detail_view(row, catalog)['text'])


def _model(data, catalog):
    if data.get('other_model'):
        return data['other_model']
    try:
        return catalog.model(data['purchase_country_code'], data['model'])['labels']['ru']
    except (KeyError, TypeError):
        return ''


def from_bot(entry, zone):
    """A client bot enquiry from visits.all_leads(), or None for what is not a lead (a car view)."""
    kind = str(entry.get('kind') or '')
    head, _, car = kind.partition(' · ')
    if head not in BOT_KINDS:
        return None
    source, folder = BOT_KINDS[head]
    moment = datetime.datetime.strptime('%s %s' % (entry.get('date', ''), entry.get('time', '')), '%Y-%m-%d %H:%M')
    created = int(moment.replace(tzinfo=zone).timestamp())
    digest = hashlib.sha256(('%s|%s|%s|%s' % (entry.get('uid'), entry.get('date'), entry.get('time'), kind)).encode())
    username = entry.get('username')
    telegram = '@' + username if username else ''
    name = _clean(entry.get('name')) or 'без имени'
    detail = '\n'.join(line for line in (
        '<b>Откуда:</b> %s' % source, '<b>Авто:</b> %s' % _escape(car) if car else '',
        '<b>Клиент:</b> %s' % _escape(name), '<b>Telegram:</b> %s' % _escape(telegram) if telegram else '',
        '<a href="tg://user?id=%s">Написать клиенту в Telegram</a>' % int(entry['uid'])) if line)
    return Lead(key='bot:' + digest.hexdigest()[:16], folder=folder, created_at=created, name=name, phone='',
                telegram=telegram, subject=_clean(car), source=source, detail=detail)


def _escape(value):
    from html import escape
    return escape(str(value))


class Sources:
    """All leads, newest first. `repository`, `catalog`, `detail_view` come from the order package; `bot_leads` is
    visits.all_leads; `zone` is the zone of its date and time (the server's clock: UTC)."""

    def __init__(self, repository, catalog, detail_view, bot_leads, zone):
        self.repository, self.catalog, self.detail_view = repository, catalog, detail_view
        self.bot_leads, self.zone = bot_leads, zone

    def all(self):
        leads, before = [], None
        for _ in range(MAX_PAGES):
            rows, before = self.repository.list_requests(before=before)
            leads.extend(from_enquiry(row, self.catalog, self.detail_view) for row in rows)
            if not before:
                break
        for entry in self.bot_leads():
            try:
                lead = from_bot(entry, self.zone)
            except (KeyError, ValueError, TypeError):
                lead = None  # a malformed old record is not a lead; it is never fatal
            if lead:
                leads.append(lead)
        return sorted(leads, key=lambda lead: lead.created_at, reverse=True)

    def get(self, key):
        if key.startswith('or:'):
            return from_enquiry(self.repository.detail(int(key[3:])), self.catalog, self.detail_view)
        found = next((lead for lead in self.all() if lead.key == key), None)
        if found is None:
            raise LookupError('lead')
        return found
