"""Enquiry desk in the CRM bot (ORDER-PROCESS-001): «Клиенты» → «Заявки с сайта» with status, reply timer,
manager note, «В работе» / «Остановить» / «Перенести в Клиенты», and reminders on the last day and after it.

Telegram glue only: enquiries come from the order package (read), work state from ua_lead_desk_store, texts
from ua_lead_desk_view, working days from ua_lead_calendar. Every action checks the caller's role first.
"""
import asyncio
import datetime
import logging

import ua_lead_calendar as cal
import ua_lead_desk_view as view
from ua_lead_desk_store import IN_WORK, STOPPED

log = logging.getLogger(__name__)
NOTE_WAIT = 'lead_desk_note'
JOB = 'ua-lead-desk-reminders'
REMIND_HOURS = range(9, 20)  # Kyiv time: no messages at night
MAX_PAGES = 25


def _markup(buttons):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([[InlineKeyboardButton(b[0], url=b[2]) if len(b) == 3 and b[1] is None
                                  else InlineKeyboardButton(b[0], callback_data=b[1]) for b in row if b]
                                 for row in buttons if row])


class Desk:
    def __init__(self, repository, catalog, store, *, authorize, staff_ids, menu_callback, clock):
        self.repository, self.catalog, self.store = repository, catalog, store
        self.authorize, self.staff_ids, self.menu_callback, self.clock = authorize, staff_ids, menu_callback, clock

    # --- screens -------------------------------------------------------------------------------------------
    def _list(self, before):
        rows, cursor = self.repository.list_requests(before=before)
        return view.list_view(rows, self.store.many([r['id'] for r in rows]), self.clock(), self.store.track_from(),
                              cursor, self.menu_callback)

    def _detail(self, order_id):
        from ua_order.crm import detail_view
        row = self.repository.detail(order_id)
        return view.detail_view(detail_view(row, self.catalog)['text'], row, self.store.get(order_id),
                                self.clock(), self.store.track_from())

    def _model_label(self, data):
        if data.get('other_model'):
            return data['other_model']
        try:
            return self.catalog.model(data['purchase_country_code'], data['model'])['labels']['ru']
        except (KeyError, TypeError):
            return ''

    def _to_client(self, order_id, actor):
        import db
        state = self.store.get(order_id)
        if not state['client_id']:
            row = self.repository.detail(order_id)
            card = view.client_card(row, state['note'], self._model_label(row['data']))
            self.store.set_client(order_id, db.create_card('clients', card, actor), actor)
        return self._detail(order_id)

    async def _show(self, query, screen):
        from telegram.error import BadRequest
        try:
            await query.edit_message_text(screen['text'], parse_mode='HTML', reply_markup=_markup(screen['buttons']))
        except BadRequest as exc:
            if 'not modified' in str(exc).lower():
                return
            await query.message.reply_text(screen['text'], parse_mode='HTML', reply_markup=_markup(screen['buttons']))

    async def callback(self, update, context):
        from telegram.ext import ApplicationHandlerStop
        from ua_order.storage import NotFound
        query = update.callback_query
        context.user_data.pop(NOTE_WAIT, None)
        if not await asyncio.to_thread(self.authorize, update):
            await query.answer('Недостаточно прав', show_alert=True)
            raise ApplicationHandlerStop
        await query.answer()
        parts, actor = query.data.split(':'), update.effective_user.id
        try:
            if parts[1] == 'list':
                screen = await asyncio.to_thread(self._list, int(parts[2]) if len(parts) == 3 else None)
            elif parts[1] == 'open':
                screen = await asyncio.to_thread(self._detail, int(parts[2]))
            elif parts[1] == 'st' and parts[3] in (IN_WORK, STOPPED):
                await asyncio.to_thread(self.store.set_status, int(parts[2]), parts[3], actor)
                screen = await asyncio.to_thread(self._detail, int(parts[2]))
            elif parts[1] == 'client':
                screen = await asyncio.to_thread(self._to_client, int(parts[2]), actor)
            elif parts[1] == 'note':
                context.user_data[NOTE_WAIT] = int(parts[2])
                await query.message.reply_text('Напишите заметку к заявке одним сообщением. '
                                               'Она заменит прежнюю. Чтобы отменить — нажмите любую кнопку.')
                raise ApplicationHandlerStop
            else:
                raise NotFound()
        except (NotFound, ValueError, IndexError):
            screen = {'text': 'Заявка не найдена', 'buttons': [[('К заявкам', 'leads:list')]]}
        await self._show(query, screen)
        raise ApplicationHandlerStop

    async def note(self, update, context):
        """The next text after «✏️ Заметка» is the note; any other message goes on to the other handlers."""
        from telegram.ext import ApplicationHandlerStop
        order_id = context.user_data.pop(NOTE_WAIT, None)
        if order_id is None or not await asyncio.to_thread(self.authorize, update):
            return
        await asyncio.to_thread(self.store.set_note, order_id, update.effective_message.text or '',
                                update.effective_user.id)
        screen = await asyncio.to_thread(self._detail, order_id)
        await update.effective_message.reply_text('✅ Заметка сохранена\n\n' + screen['text'], parse_mode='HTML',
                                                  reply_markup=_markup(screen['buttons']))
        raise ApplicationHandlerStop

    async def cancel_note(self, update, context):
        context.user_data.pop(NOTE_WAIT, None)

    # --- reminders -----------------------------------------------------------------------------------------
    def _due(self):
        """(row, kind) for tracked new enquiries on their last day or past the deadline, each kind sent once."""
        now, track_from, before, due = self.clock(), self.store.track_from(), None, []
        for _ in range(MAX_PAGES):
            rows, before = self.repository.list_requests(before=before)
            for row in rows:
                if row['created_at'] < track_from:
                    return due
                kind = view.stage(row, self.store.get(row['id']), now, track_from)
                if kind in ('last_day', 'overdue') and self.store.claim_reminder(row['id'], kind):
                    due.append((row, kind))
            if not before:
                break
        return due

    async def remind(self, context):
        if datetime.datetime.fromtimestamp(self.clock(), cal.KYIV).hour not in REMIND_HOURS:
            return
        try:
            due = await asyncio.to_thread(self._due)
            recipients = await asyncio.to_thread(self.staff_ids)
        except Exception as exc:
            log.warning('lead desk reminders: %s', exc)
            return
        for row, kind in due:
            message = view.reminder(row, kind)
            for chat in recipients:
                try:
                    await context.bot.send_message(chat, message['text'], parse_mode='HTML',
                                                   reply_markup=_markup(message['buttons']))
                except Exception as exc:
                    log.warning('lead desk reminder %s to %s: %s', row['number'], chat, exc)

    def register(self, app, *, group):
        from telegram.ext import CallbackQueryHandler, MessageHandler, filters
        if group in app.handlers:
            raise ValueError('Reserve an unused handler group')
        app.add_handler(CallbackQueryHandler(self.callback, pattern=r'^leads:'), group=group)
        app.add_handler(CallbackQueryHandler(self.cancel_note), group=group)
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.note), group=group)
        app.add_handler(MessageHandler(filters.COMMAND, self.cancel_note), group=group)
        if app.job_queue is not None and not app.job_queue.get_jobs_by_name(JOB):
            app.job_queue.run_repeating(self.remind, interval=900, first=120, name=JOB)
