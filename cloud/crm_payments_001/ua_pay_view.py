"""Texts and buttons of «💳 Платежи» in the CRM bot (CRM-PAYMENTS-001). Pure functions, no I/O.

Buttons are (label, callback_data) rows. Callback data: 'cp:o:<id>' screen, 'cp:pay:<id>' choose a payment to mark,
'cp:pk:<id>:<kind>' enter the amount, 'cp:pf:<id>:<kind>' paid in full, 'cp:inv:<id>' choose an invoice,
'cp:ik:<id>:<kind>' issue logistics/customs, 'cp:lot:<id>' paste the lot link, 'cp:ok:<id>' confirm the read price,
'cp:price:<id>' type the price, 'cp:msg:<id>' text for the client, 'cp:hist:<id>' history, 'cp:ph:<id>' photos;
'co:o:<id>' is the order card (ua_crm_orders).
"""
import datetime
from html import escape

import ua_pay_rules as rules

BUTTON = '💳 Платежи'
LOT_BUTTON = '🔗 Вставить ссылку на лот'
MARK = {'paid': '✅', 'open': '🕓', 'late': '⛔', 'final': '⛔', 'none': '○'}


def money(value):
    value = round(float(value), 2)
    text = '{:,.2f}'.format(value).replace(',', ' ').replace('.', ',')
    return (text[:-3] if text.endswith(',00') else text) + ' $'


def d(day):
    return day.strftime('%d.%m.%Y') if day else ''


def order_buttons(order, car):
    """Rows added to the order card: the payments, and the lot link once the car is bought and not entered."""
    rows = [[(BUTTON, 'cp:o:%d' % order['id'])]]
    if order['stage'] != 'contract' and not (car and car.get('confirmed')):
        rows.append([(LOT_BUTTON, 'cp:lot:%d' % order['id'])])
    return rows


def _car_line(order, car):
    if not car:
        return escape(order.get('subject') or 'Авто ещё не внесено')
    parts = [car.get('title'), car.get('year'), car.get('vin') and 'VIN ' + car['vin'],
             car.get('lot_id') and 'лот ' + car['lot_id']]
    return escape(' · '.join(p for p in parts if p))


def payment_line(kind, payment, today, nbu_rate):
    st = rules.state(payment, today)
    title = rules.TITLES[kind]
    if st == 'none':
        return '%s %d. %s — счёт ещё не выставлен' % (MARK[st], kind, title), 0.0
    amount, paid = payment['amount'], payment['paid']
    head = '%s %d. %s %s' % (MARK[st], kind, title, money(amount))
    if st == 'paid':
        when = datetime.datetime.fromtimestamp(payment['paid_at']).strftime('%d.%m') if payment.get('paid_at') else ''
        return head + ' — оплачено' + (' ' + when if when else ''), 0.0
    debt = amount - paid
    part = ' (оплачено %s, остаток %s)' % (money(paid), money(debt)) if paid else ''
    due = payment.get('due')
    if due is None:
        return head + part + ' — без срока', 0.0
    if st == 'open':
        left = rules.working_days_between(today, due)
        return head + part + ' — до %s (осталось %d раб. дн.)' % (d(due), left), 0.0
    s = rules.sanctions(debt, due, today, nbu_rate)
    extra = rules.extra_deadline(due)
    lines = [head + part + ' — срок был %s, <b>просрочка %d раб. дн.</b>' % (d(due), s['work_days']),
             '   пеня (2 × ставка НБУ): %s · 36 %% годовых: %s' % (money(s['penalty']), money(s['annual'])),
             '   штраф 5 %%: %s' % (money(s['fine']) if s['fine'] else 'с %d-го раб. дня' % (rules.FINE_AFTER + 1)),
             ('   доп. срок до %s' % d(extra)) if st == 'late' else '   <b>доп. срок истёк %s — договор можно считать '
                                                                     'расторгнутым (п. 6.5), решение за владельцем</b>'
             % d(extra)]
    return '\n'.join(lines), debt + s['total']


def screen(order, car, payments, today, nbu_rate):
    lines = ['<b>💳 Платежи · договор № %s · %s</b>' % (escape(order['contract_no']), escape(order.get('name') or '')),
             _car_line(order, car), '']
    due_now = 0.0
    for kind in rules.KINDS:
        text, owed = payment_line(kind, payments.get(kind), today, nbu_rate)
        lines.append(text)
        p = payments.get(kind)
        if p and rules.state(p, today) == 'open' and p.get('due') and (p['due'] - today).days <= 30:
            owed = p['amount'] - p['paid']
        due_now += owed
    lines += ['', 'К оплате сейчас: <b>%s</b> (в гривне по курсу НБУ на день оплаты)' % money(due_now),
              '<i>Учётная ставка НБУ в расчёте: %s %%. Инфляционные — при претензии.</i>' % str(round(nbu_rate * 100, 2))
              .replace('.', ',')]
    buttons = [[('✅ Отметить оплату', 'cp:pay:%d' % order['id']), ('🧾 Выставить счёт', 'cp:inv:%d' % order['id'])],
               [('📨 Текст уведомления клиенту', 'cp:msg:%d' % order['id']), ('📋 История', 'cp:hist:%d' % order['id'])]]
    if car and car.get('photos'):
        buttons.append([('📷 Фото авто', 'cp:ph:%d' % order['id'])])
    if order['stage'] != 'contract' and not (car and car.get('confirmed')):
        buttons.append([(LOT_BUTTON, 'cp:lot:%d' % order['id'])])
    buttons.append([('⬅️ К заказу', 'co:o:%d' % order['id'])])
    return {'text': '\n'.join(lines), 'buttons': buttons}


def choose_payment(order, payments, today):
    rows = [[('%d. %s' % (k, rules.TITLES[k]), 'cp:pk:%d:%d' % (order['id'], k))] for k in rules.KINDS
            if payments.get(k) and rules.state(payments[k], today) != 'paid']
    rows.append([('⬅️ Назад', 'cp:o:%d' % order['id'])])
    text = 'Какой платёж оплачен?' if len(rows) > 1 else 'Нет выставленных неоплаченных платежей.'
    return {'text': text, 'buttons': rows}


def amount_prompt(order, kind, payment):
    debt = payment['amount'] - payment['paid']
    return {'text': '%d. %s — остаток %s.\nНапишите сумму оплаты в $ одним сообщением (например 1500) или нажмите '
                    '«Полностью». Отменить — любая кнопка.' % (kind, rules.TITLES[kind], money(debt)),
            'buttons': [[('Полностью %s' % money(debt), 'cp:pf:%d:%d' % (order['id'], kind))],
                        [('⬅️ Назад', 'cp:o:%d' % order['id'])]]}


def choose_invoice(order, payments):
    rows = []
    if 2 in payments and 3 not in payments:
        rows.append([('3. Логистика', 'cp:ik:%d:3' % order['id'])])
    if 3 in payments and 4 not in payments:
        rows.append([('4. Таможенные платежи', 'cp:ik:%d:4' % order['id'])])
    for k in (3, 4):
        if k in payments and payments[k]['paid'] < payments[k]['amount']:
            rows.append([('Изменить счёт: %s' % rules.TITLES[k], 'cp:ik:%d:%d' % (order['id'], k))])
    rows.append([('⬅️ Назад', 'cp:o:%d' % order['id'])])
    text = ('Какой счёт выставить?' if len(rows) > 1 else
            'Сначала внесите авто по ссылке на лот и подтвердите цену — тогда откроется счёт на логистику.')
    return {'text': text, 'buttons': rows}


INVOICE_PROMPT = {
    3: 'Логистика: напишите дату погрузки на паром и сумму, например «04.12.2026 3450». Без суммы — 3 450 $.\n'
       'Срок оплаты: 10 рабочих дней с сегодня, но не позже дня до парома.',
    4: 'Таможенные платежи: напишите сумму в $ по расчёту, например «2850». Срок оплаты: 5 рабочих дней с сегодня.'}
LOT_PROMPT = ('Вставьте ссылку на лот (например https://jpauto.auction/vehicle-detail/kr/20261106043479) или номер '
              'лота — CRM сама заполнит марку, модель, год, VIN, пробег и фото. Отменить — любая кнопка.')
PRICE_PROMPT = 'Напишите цену покупки авто в $ (за сколько куплено на аукционе), например 14200.'


def car_found(order, car):
    lines = ['<b>Авто по лоту %s</b>' % escape(car['lot_id']), escape(car['title'] or '—'),
             'Год: %s · пробег: %s · цвет: %s' % (escape(car['year'] or '—'), escape(car['mileage'] or '—'),
                                                  escape(car['color'] or '—')),
             'VIN: %s · фото: %d' % (escape(car['vin'] or '—'), len(car['photos']))]
    buttons = []
    if car.get('price_usd'):
        lines.append('Итоговая цена на аукционе: <b>%s</b>%s' % (money(car['price_usd']), car.get('price_krw') and
                                                                 ' (%s KRW по курсу НБУ)' % '{:,}'.format(
                                                                     car['price_krw']).replace(',', ' ') or ''))
        buttons.append([('✅ Цена верна — %s' % money(car['price_usd']), 'cp:ok:%d' % order['id'])])
    else:
        lines.append('Итоговую цену на странице лота не нашёл — введите её вручную.')
    buttons += [[('✏️ Ввести цену вручную', 'cp:price:%d' % order['id'])], [('⬅️ Назад', 'cp:o:%d' % order['id'])]]
    lines.append('После подтверждения цены откроется платёж № 2: 7 рабочих дней на оплату.')
    return {'text': '\n'.join(lines), 'buttons': buttons}


def client_notice(order, kind, payment, today, nbu_rate):
    """Ukrainian text of the contract's Annex 4 for the client (the manager forwards it)."""
    debt = payment['amount'] - payment['paid']
    due = payment.get('due')
    if due and today > due:
        extra = rules.extra_deadline(due)
        return ('Шановний(а) %s! За Договором № %s строк оплати платежу № %d (%s) сплив %s. Сума боргу: %s '
                '(у гривні за курсом НБУ на день оплати). До оплати наступний етап не виконується. Просимо сплатити '
                'борг до %s. З %s нараховуються суми за п. 6.2 Договору. Якщо оплати не буде до цієї дати, Договір '
                'вважатиметься розірваним, Автомобіль буде продано третій особі, а розрахунок і повернення залишку на '
                'Ваш рахунок — за п. 6.6. UA ART COMPANY.'
                % (order.get('name') or '', order['contract_no'], kind, _uk(kind), d(due), money(debt), d(extra),
                   d(due + datetime.timedelta(days=1))))
    return ('Шановний(а) %s! Нагадуємо: за Договором № %s платіж № %d (%s) — %s%s. Дякуємо! UA ART COMPANY.'
            % (order.get('name') or '', order['contract_no'], kind, _uk(kind), money(debt),
               ', строк оплати до %s включно' % d(due) if due else ''))


def _uk(kind):
    return {1: 'послуга супроводу та передоплата', 2: 'вартість придбання автомобіля', 3: 'логістика',
            4: 'митні платежі'}[kind]


def history(order, rows):
    names = {'issue': 'выставлен счёт', 'pay': 'оплата', 'car': 'внесено авто по лоту'}
    lines = ['<b>📋 История платежей · № %s</b>' % escape(order['contract_no'])]
    for kind, action, amount, actor, at in rows:
        when = datetime.datetime.fromtimestamp(at).strftime('%d.%m %H:%M')
        lines.append('%s · %s%s%s' % (when, names.get(action, action), ' № %d' % kind if kind else '',
                                      ' · %s' % money(amount) if amount else ''))
    if len(lines) == 1:
        lines.append('Пока пусто.')
    return {'text': '\n'.join(lines), 'buttons': [[('⬅️ Назад', 'cp:o:%d' % order['id'])]]}


# --- reminders --------------------------------------------------------------------------------------------------
def remind_car(order):
    return {'text': '⚠️ <b>Авто куплено, данных нет.</b>\nМенеджер, ты должен обязательно внести данные автомобиля: '
                    'вставь ссылку на лот — CRM сама заполнит марку, модель, год, VIN, пробег и фото.\n'
                    'Договор № %s · %s' % (escape(order['contract_no']), escape(order.get('name') or '')),
            'buttons': [[(LOT_BUTTON, 'cp:lot:%d' % order['id'])]]}


def remind_payment(order, kind, payment, when, today, nbu_rate):
    title = '%d. %s' % (kind, rules.TITLES[kind])
    debt = payment['amount'] - payment['paid']
    due = payment['due']
    head = {'pre3': '⏰ <b>Через 3 раб. дня срок оплаты</b>', 'due': '⏰ <b>Сегодня последний день оплаты</b>',
            'late': '⛔ <b>Просрочка оплаты — отправьте клиенту уведомление</b>',
            'final': '⛔ <b>Доп. срок истёк — платёж не оплачен</b>'}[when]
    lines = [head, 'Договор № %s · %s' % (escape(order['contract_no']), escape(order.get('name') or '')),
             '%s · %s до %s' % (escape(title), money(debt), d(due))]
    if kind == 3 and payment.get('ferry'):
        lines.append('Паром по плану: %s' % d(payment['ferry']))
    if when == 'late':
        lines.append('Доп. срок до %s, начисляются пеня и 36 %% годовых (п. 6.2).' % d(rules.extra_deadline(due)))
    if when == 'final':
        lines.append('Договор можно считать расторгнутым (п. 6.5). Решение — за владельцем.')
    return {'text': '\n'.join(lines), 'buttons': [[('📨 Текст уведомления клиенту', 'cp:msg:%d' % order['id'])],
                                                  [(BUTTON, 'cp:o:%d' % order['id'])]]}
