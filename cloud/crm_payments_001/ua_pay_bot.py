"""CRM bot: «💳 Платежи» in the order card of «👤 Клиенты» (CRM-PAYMENTS-001, owner «да» 2026-11-12).

Telegram glue only: rules in ua_pay_rules, tables in ua_pay_store, texts in ua_pay_view, the lot page in ua_pay_lot.
The order card (ua_crm_orders_view.detail_view, LEAD-FOLDERS / LEAD-GROUPS) gets the «💳 Платежи» row and, once the
car is bought and not entered, «🔗 Вставить ссылку на лот» — by wrapping that function at start; its file is not
changed. Staff with the owner, administrator or manager role use it (owner: managers see the sums and mark payments).
Reminders go to the owner and to the order's manager only, 9–19 Kyiv time, each once; the client gets nothing from
the bot (owner: the manager forwards the ready text). A failure only logs; the CRM keeps working.
"""
import asyncio
import datetime
import json
import logging
import re
import urllib.request

import ua_lead_calendar as cal
import ua_pay_lot as lot
import ua_pay_rules as rules
import ua_pay_store as payst
import ua_pay_view as view

log = logging.getLogger(__name__)
WAIT = 'crm_pay_wait'
JOB = 'crm_pay_reminders'
REMIND_HOURS = range(9, 19)
NBU_DISCOUNT_URL = 'https://bank.gov.ua/NBUStatService/v1/statdirectory/discount-rate?json'
_STORE = None


def _store():
    global _STORE
    if _STORE is None:
        import db
        _STORE = payst.PayStore(db.connect)
        _STORE.initialize()
    return _STORE


def _today():
    return datetime.datetime.now(cal.KYIV).date()


def _rate():
    return float(_store().meta('nbu_rate', payst.NBU_RATE_DEFAULT))


def parse_nbu_rate(payload):
    """NBU JSON list -> the latest discount rate as a fraction (0.155), or ValueError."""
    best = None
    for row in payload if isinstance(payload, list) else []:
        for key in ('value', 'rate'):
            try:
                value = float(row.get(key))
            except (TypeError, ValueError):
                continue
            stamp = str(row.get('dt') or row.get('exchangedate') or row.get('startdate') or '')
            if 0.5 <= value <= 100 and (best is None or stamp >= best[0]):
                best = (stamp, value)
    if best is None:
        raise ValueError('NBU_DISCOUNT_RATE')
    return round(best[1] / 100, 6)


def refresh_nbu_rate():
    req = urllib.request.Request(NBU_DISCOUNT_URL, headers={'User-Agent': 'UA-ART-crm/1'})
    with urllib.request.urlopen(req, timeout=30) as r:
        rate = parse_nbu_rate(json.load(r))
    _store().set_meta('nbu_rate', rate)
    _store().set_meta('nbu_rate_at', _today().isoformat())
    return rate


def allowed(update):
    import db
    user = update.effective_user
    staff = db.get_staff(user.id) if user else None
    return bool(staff and staff['active'] and staff['role'] in (db.ROLE_OWNER, db.ROLE_ADMIN, db.ROLE_MANAGER))


def markup(rows):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([[InlineKeyboardButton(b[0], callback_data=b[1]) for b in row] for row in rows if row])


def _order(order_id):
    from ua_crm_orders import _book
    return _book().get(int(order_id))


def _screen(order_id):
    order = _order(order_id)
    return view.screen(order, _store().car(order['id']), _store().payments(order['id']), _today(), _rate())


# --- the order card ----------------------------------------------------------------------------------------------
def patch_order_card():
    """Add the payments rows to ua_crm_orders_view.detail_view (once)."""
    import ua_crm_orders_view as orders_view
    original = orders_view.detail_view
    if getattr(original, '_crm_pay', False):
        return

    def detail_view(order, zone):
        result = original(order, zone)
        try:
            rows = view.order_buttons(order, _store().car(order['id']))
            result = dict(result, buttons=rows + list(result['buttons']))
        except Exception as exc:
            log.warning('crm pay: order card buttons skipped: %s', exc)
        return result

    detail_view._crm_pay = True
    orders_view.detail_view = detail_view


# --- callbacks ---------------------------------------------------------------------------------------------------
def _action(parts, actor, user_data):
    """Screen for a callback (runs in a thread)."""
    action, order_id = parts[1], int(parts[2])
    order = _order(order_id)
    store, today = _store(), _today()
    if action == 'o':
        return _screen(order_id)
    if action == 'pay':
        return view.choose_payment(order, store.payments(order_id), today)
    if action == 'pk':
        kind = int(parts[3])
        user_data[WAIT] = ('amount', order_id, kind)
        return view.amount_prompt(order, kind, store.payments(order_id)[kind])
    if action == 'pf':
        kind = int(parts[3])
        payment = store.payments(order_id)[kind]
        if payment['paid'] < payment['amount']:
            store.pay(order_id, kind, payment['amount'] - payment['paid'], actor)
        return dict(_screen(order_id), notice='✅ Оплата отмечена')
    if action == 'inv':
        return view.choose_invoice(order, store.payments(order_id))
    if action == 'ik':
        kind = int(parts[3])
        user_data[WAIT] = ('invoice', order_id, kind)
        return {'text': view.INVOICE_PROMPT[kind], 'buttons': [[('⬅️ Назад', 'cp:o:%d' % order_id)]]}
    if action == 'lot':
        user_data[WAIT] = ('lot', order_id, None)
        return {'text': view.LOT_PROMPT, 'buttons': [[('⬅️ Назад', 'cp:o:%d' % order_id)]]}
    if action == 'ok':
        car = store.car(order_id)
        if not car or not car.get('price_usd'):
            raise LookupError('car')
        due = store.confirm_price(order_id, car['price_usd'], today, actor)
        return dict(_screen(order_id), notice='✅ Цена подтверждена. Платёж № 2 — до %s' % view.d(due))
    if action == 'price':
        user_data[WAIT] = ('price', order_id, None)
        return {'text': view.PRICE_PROMPT, 'buttons': [[('⬅️ Назад', 'cp:o:%d' % order_id)]]}
    if action == 'msg':
        payments = store.payments(order_id)
        open_kinds = [k for k in rules.KINDS if k in payments and rules.state(payments[k], today) != 'paid']
        if not open_kinds:
            return {'text': 'Все выставленные платежи оплачены.', 'buttons': [[('⬅️ Назад', 'cp:o:%d' % order_id)]]}
        kind = max(open_kinds, key=lambda k: (rules.state(payments[k], today) in ('late', 'final'), k))
        text = view.client_notice(order, kind, payments[kind], today, _rate())
        return {'text': 'Текст для клиента — перешлите его:\n\n' + text,
                'buttons': [[('⬅️ Назад', 'cp:o:%d' % order_id)]], 'plain': True}
    if action == 'hist':
        return view.history(order, store.history(order_id))
    raise LookupError('action')


async def callback(update, context):
    from telegram.ext import ApplicationHandlerStop
    from telegram.error import BadRequest
    query = update.callback_query
    context.user_data.pop(WAIT, None)
    if not await asyncio.to_thread(allowed, update):
        await query.answer('Недостаточно прав', show_alert=True)
        raise ApplicationHandlerStop
    await query.answer()
    parts = query.data.split(':')
    try:
        if parts[1] == 'ph':
            await _photos(query, int(parts[2]))
            raise ApplicationHandlerStop
        screen = await asyncio.to_thread(_action, parts, update.effective_user.id, context.user_data)
    except (LookupError, ValueError, IndexError, KeyError):
        screen = {'text': 'Заказ или платёж не найден', 'buttons': [[('К папкам', 'cards_clients')]]}
    text = (screen.pop('notice') + '\n\n' if 'notice' in screen else '') + screen['text']
    mode = None if screen.get('plain') else 'HTML'
    try:
        await query.edit_message_text(text, parse_mode=mode, reply_markup=markup(screen['buttons']))
    except BadRequest as exc:
        if 'not modified' not in str(exc).lower():
            await query.message.reply_text(text, parse_mode=mode, reply_markup=markup(screen['buttons']))
    raise ApplicationHandlerStop


async def _photos(query, order_id):
    from telegram import InputMediaPhoto
    car = await asyncio.to_thread(_store().car, order_id)
    photos = (car or {}).get('photos') or []
    if not photos:
        await query.message.reply_text('Фото нет.')
        return
    try:
        await query.message.reply_media_group([InputMediaPhoto(url) for url in photos[:10]])
    except Exception as exc:
        log.warning('crm pay photos %s: %s', order_id, exc)
        await query.message.reply_text('Фото не загрузились. Ссылка на лот: %s' % car.get('lot_url'))


# --- text input --------------------------------------------------------------------------------------------------
_NUMBER = re.compile(r'\d[\d\s]*(?:[.,]\d{1,2})?')
_DATE = re.compile(r'(\d{1,2})\.(\d{1,2})\.(\d{4})')


def number(text):
    match = _NUMBER.search((text or '').replace('$', ''))
    if not match:
        raise ValueError('number')
    value = float(match.group(0).replace(' ', '').replace(',', '.'))
    if value <= 0:
        raise ValueError('number')
    return value


def _input(wait, text, actor):
    """The answer to a prompt -> (notice, screen) (runs in a thread)."""
    kind_of, order_id, kind = wait
    store, today = _store(), _today()
    if kind_of == 'amount':
        store.pay(order_id, kind, number(text), actor)
        return '✅ Оплата отмечена', _screen(order_id)
    if kind_of == 'price':
        due = store.confirm_price(order_id, number(text), today, actor) if store.car(order_id) else None
        if due is None:
            raise LookupError('car')
        return '✅ Цена принята. Платёж № 2 — до %s' % view.d(due), _screen(order_id)
    if kind_of == 'invoice':
        ferry = None
        rest = text
        if kind == 3:
            found = _DATE.search(text or '')
            if not found:
                raise ValueError('ferry')
            ferry = datetime.date(int(found.group(3)), int(found.group(2)), int(found.group(1)))
            rest = text[found.end():]
        amount = number(rest) if _NUMBER.search(rest or '') else (rules.LOGISTICS_USD if kind == 3 else None)
        if amount is None:
            raise ValueError('amount')
        due = store.issue(order_id, kind, amount, today, actor, ferry)
        return '✅ Счёт выставлен. Оплата до %s' % view.d(due), _screen(order_id)
    if kind_of == 'lot':
        car = lot.fetch(text)
        store.set_car(order_id, car, actor)
        return None, view.car_found(_order(order_id), store.car(order_id))
    raise LookupError('wait')


async def text_input(update, context):
    """The next text after a payments prompt; any other message goes on to the other handlers."""
    from telegram.ext import ApplicationHandlerStop
    wait = context.user_data.pop(WAIT, None)
    if wait is None or not await asyncio.to_thread(allowed, update):
        return
    message = update.effective_message
    try:
        notice, screen = await asyncio.to_thread(_input, wait, message.text or '', update.effective_user.id)
    except ValueError:
        context.user_data[WAIT] = wait
        await message.reply_text('Не понял ответ. ' + {
            'amount': 'Напишите сумму в $, например 1500.', 'price': 'Напишите цену в $, например 14200.',
            'invoice': 'Пример: «04.12.2026 3450» (логистика) или «2850» (таможня).',
            'lot': 'Нужна ссылка вида https://jpauto.auction/vehicle-detail/kr/… или номер лота.'}[wait[0]])
        raise ApplicationHandlerStop
    except Exception as exc:
        log.warning('crm pay input %s: %s', wait, exc)
        await message.reply_text('Не получилось: %s. Попробуйте ещё раз или напишите владельцу.' % (
            'страница лота не открылась' if wait[0] == 'lot' else 'ошибка'),
            reply_markup=markup([[('💳 Платежи', 'cp:o:%d' % wait[1])]]))
        raise ApplicationHandlerStop
    await message.reply_text((notice + '\n\n' if notice else '') + screen['text'], parse_mode='HTML',
                             reply_markup=markup(screen['buttons']))
    raise ApplicationHandlerStop


async def cancel(update, context):
    context.user_data.pop(WAIT, None)


# --- reminders ---------------------------------------------------------------------------------------------------
def due_reminders(today):
    """[(order, message)] to send now; each reminder is claimed once (runs in a thread)."""
    store, out = _store(), []
    if store.meta('nbu_rate_at') != today.isoformat():
        try:
            refresh_nbu_rate()
        except Exception as exc:
            store.set_meta('nbu_rate_at', today.isoformat())  # one try a day; the stored rate stays
            log.warning('crm pay: NBU discount rate not read: %s', exc)
    rate = _rate()
    for order in store.orders():
        payments = store.payments(order['id'])
        car = store.car(order['id'])
        if order['stage'] != 'contract' and not (car and car.get('confirmed')):
            if store.claim_reminder('car:%d:%s' % (order['id'], today.isoformat())):
                out.append((order, view.remind_car(order)))
        for kind in (2, 3, 4):
            payment = payments.get(kind)
            if not payment or payment['due'] is None or payment['paid'] >= payment['amount']:
                continue
            due, st = payment['due'], rules.state(payment, today)
            when = None
            if st == 'open' and rules.working_days_between(today, due) == 3:
                when = 'pre3'
            elif st == 'open' and today == due:
                when = 'due'
            elif st == 'late':
                when = 'late'
            elif st == 'final':
                when = 'final'
            if when and store.claim_reminder('%s:%d:%d:%s' % (when, order['id'], kind, due.isoformat())):
                out.append((order, view.remind_payment(order, kind, payment, when, today, rate)))
    return out


def recipients(order):
    import db
    chats = set(db.staff_ids_by_role(db.ROLE_OWNER))
    manager = order.get('created_by')
    staff = db.get_staff(manager) if manager else None
    if staff and staff['active']:
        chats.add(manager)
    return chats


async def remind(context):
    now = datetime.datetime.now(cal.KYIV)
    if now.hour not in REMIND_HOURS:
        return
    try:
        due = await asyncio.to_thread(due_reminders, now.date())
    except Exception as exc:
        log.warning('crm pay reminders: %s', exc)
        return
    for order, message in due:
        for chat in await asyncio.to_thread(recipients, order):
            try:
                await context.bot.send_message(chat, message['text'], parse_mode='HTML',
                                               reply_markup=markup(message['buttons']))
            except Exception as exc:
                log.warning('crm pay reminder %s to %s: %s', order['id'], chat, exc)


def register(app):
    from telegram.ext import CallbackQueryHandler, MessageHandler, filters
    patch_order_card()
    group = min(app.handlers, default=0) - 1  # an unused group before the other handlers
    app.add_handler(CallbackQueryHandler(callback, pattern=r'^cp:'), group=group)
    app.add_handler(CallbackQueryHandler(cancel), group=group)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_input), group=group)
    app.add_handler(MessageHandler(filters.COMMAND, cancel), group=group)
    if app.job_queue is not None and not app.job_queue.get_jobs_by_name(JOB):
        app.job_queue.run_repeating(remind, interval=900, first=180, name=JOB)
    return group
