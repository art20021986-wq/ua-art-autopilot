"""Lead desk in the client bot (LEAD-FOLDERS-001, owner 2026-11-06): leads by folder of where they came from,
status, reply timer, note, reminders, and «Оформить договор» (number → file → confirm), after which the lead is an
order in the CRM bot.

Telegram glue only: leads from ua_lead_sources, their state from ua_lead_desk_store, orders in ua_order_book,
contract files in ua_contract_files, texts from ua_lead_desk_view. Only the authorized staff chat sees any of it.
The client bot's screens (vitrina.py) show the owner the «📥 Лиды» button (BUTTON, CALLBACK) and let a message the
desk waits for come here (pending()).
"""
import asyncio
import datetime
import logging

import ua_contract_files as files
import ua_lead_calendar as cal
import ua_lead_desk_view as view
from ua_lead_desk_store import CONTRACT, IN_WORK, STOPPED

log = logging.getLogger(__name__)
WAIT = 'lead_desk_wait'
BUTTON, CALLBACK = '📥 Лиды', 'ld:home'
JOB = 'ua-lead-desk-reminders'
REMIND_HOURS = range(9, 20)  # Kyiv time: no messages at night


def markup(buttons):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([[InlineKeyboardButton(b[0], callback_data=b[1]) for b in row] for row in buttons if row])


class Desk:
    def __init__(self, sources, store, book, *, authorize, recipients, clock, files_root=None):
        self.sources, self.store, self.book = sources, store, book
        self.authorize, self.recipients, self.clock, self.files_root = authorize, recipients, clock, files_root

    # --- screens -------------------------------------------------------------------------------------------
    def _contracts_this_month(self):
        now = datetime.datetime.fromtimestamp(self.clock(), cal.KYIV)
        start = int(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())
        return sum(order['created_at'] >= start for order in self.book.all())

    def _snapshot(self):
        leads, states = self.sources.all(), self.store.all()
        header = view.stats(leads, states, self.clock(), self.store.track_from(), self._contracts_this_month())
        return leads, states, header

    def screen(self, action, key):
        if action == 'home':
            leads, states, header = self._snapshot()
            return view.folders_view(header, leads, states)
        if action == 'f':
            if key not in view.folders.FOLDERS:
                raise LookupError('folder')
            return view.list_view(key, self.sources.all(), self.store.all(), self.clock(), self.store.track_from())
        return self.detail(key)

    def detail(self, key):
        return view.detail_view(self.sources.get(key), self.store.get(key), self.clock(), self.store.track_from())

    def make_order(self, key, number, file_name, actor):
        number = number.strip()[:60]
        lead = self.sources.get(key)
        self.book.create(view.order_values(lead, number, file_name), actor)
        self.store.set_status(key, CONTRACT, actor)
        return view.done_view(lead, number)

    async def _show(self, query, screen):
        from telegram.error import BadRequest
        try:
            await query.edit_message_text(screen['text'], parse_mode='HTML', reply_markup=markup(screen['buttons']),
                                          disable_web_page_preview=True)
        except BadRequest as exc:
            if 'not modified' not in str(exc).lower():
                await query.message.reply_text(screen['text'], parse_mode='HTML', reply_markup=markup(screen['buttons']),
                                               disable_web_page_preview=True)

    # --- handlers ------------------------------------------------------------------------------------------
    async def callback(self, update, context):
        from telegram.ext import ApplicationHandlerStop
        query = update.callback_query
        if not self.authorize(update):
            await query.answer('Недостаточно прав', show_alert=True)
            raise ApplicationHandlerStop
        await query.answer()
        parts = query.data.split(':', 2)
        action, rest, actor = parts[1], parts[2] if len(parts) == 3 else '', update.effective_user.id
        waiting = context.user_data.pop(WAIT, None)
        try:
            if action == 'st':
                status, key = rest.split(':', 1)
                if status not in (IN_WORK, STOPPED):
                    raise LookupError('status')
                await asyncio.to_thread(self.store.set_status, key, status, actor)
                screen = await asyncio.to_thread(self.detail, key)
            elif action == 'note':
                context.user_data[WAIT] = {'kind': 'note', 'key': rest}
                await query.message.reply_text(view.NOTE_PROMPT)
                raise ApplicationHandlerStop
            elif action == 'contract':
                lead = await asyncio.to_thread(self.sources.get, rest)
                context.user_data[WAIT] = {'kind': 'number', 'key': rest}
                await query.message.reply_text(view.ASK_NUMBER % lead.name)
                raise ApplicationHandlerStop
            elif action == 'ok':
                if not waiting or waiting.get('kind') != 'confirm' or waiting['key'] != rest:
                    raise LookupError('contract')
                screen = await asyncio.to_thread(self.make_order, rest, waiting['number'], waiting['file'], actor)
            elif action == 'cancel':
                screen = await asyncio.to_thread(self.detail, rest)
            elif action in ('home', 'f', 'o'):
                screen = await asyncio.to_thread(self.screen, action, rest)
            else:
                raise LookupError('action')
        except (LookupError, ValueError):
            screen = {'text': 'Лид не найден', 'buttons': [[('К папкам', 'ld:home')]]}
        await self._show(query, screen)
        raise ApplicationHandlerStop

    async def message(self, update, context):
        """The staff's next message after «✏️ Заметка» or a contract step; any other message goes on."""
        from telegram.ext import ApplicationHandlerStop
        waiting = context.user_data.get(WAIT)
        if not waiting or not self.authorize(update):
            return
        message, actor = update.effective_message, update.effective_user.id
        if waiting['kind'] == 'note' and message.text:
            context.user_data.pop(WAIT, None)
            await asyncio.to_thread(self.store.set_note, waiting['key'], message.text, actor)
            screen = await asyncio.to_thread(self.detail, waiting['key'])
            await message.reply_text('✅ Заметка сохранена\n\n' + screen['text'], parse_mode='HTML',
                                     reply_markup=markup(screen['buttons']), disable_web_page_preview=True)
        elif waiting['kind'] == 'number' and message.text and message.text.strip():
            waiting.update(kind='file', number=message.text.strip()[:60])
            await message.reply_text(view.ASK_FILE)
        elif waiting['kind'] == 'file' and (message.document or message.photo):
            name = await self._save_file(context, waiting['key'], message)
            if not name:
                await message.reply_text(view.BAD_FILE)
            else:
                waiting.update(kind='confirm', file=name)
                lead = await asyncio.to_thread(self.sources.get, waiting['key'])
                screen = view.confirm_view(lead, waiting['number'])
                await message.reply_text(screen['text'], parse_mode='HTML', reply_markup=markup(screen['buttons']))
        elif waiting['kind'] == 'file':
            await message.reply_text(view.BAD_FILE)
        else:
            return
        raise ApplicationHandlerStop

    async def cancel(self, update, context):
        """Any other button ends a started note or contract."""
        context.user_data.pop(WAIT, None)

    async def _save_file(self, context, key, message):
        if message.document:
            document = message.document
            ext = files.extension(document.file_name, document.mime_type)
            if not ext or (document.file_size or 0) > files.MAX_BYTES:
                return None
            file_id = document.file_id
        else:
            ext, file_id = 'jpg', message.photo[-1].file_id
        telegram_file = await context.bot.get_file(file_id)
        data = bytes(await telegram_file.download_as_bytearray())
        return await asyncio.to_thread(files.save, key, data, ext, root=self.files_root)

    # --- reminders -----------------------------------------------------------------------------------------
    def _due(self):
        now, track_from, due = self.clock(), self.store.track_from(), []
        states = self.store.all()
        for lead in view.active(self.sources.all(), states):
            if lead.created_at < track_from:
                continue
            kind = view.stage(lead, states.get(lead.key) or {'status': 'new'}, now, track_from)
            if kind in ('last_day', 'overdue') and self.store.claim_reminder(lead.key, kind):
                due.append((lead, kind))
        return due

    async def remind(self, context):
        if datetime.datetime.fromtimestamp(self.clock(), cal.KYIV).hour not in REMIND_HOURS:
            return
        try:
            due = await asyncio.to_thread(self._due)
        except Exception as exc:
            log.warning('lead desk reminders: %s', exc)
            return
        for lead, kind in due:
            message = view.reminder(lead, kind)
            for chat in self.recipients():
                try:
                    await context.bot.send_message(chat, message['text'], parse_mode='HTML',
                                                   reply_markup=markup(message['buttons']))
                except Exception as exc:
                    log.warning('lead desk reminder %s to %s: %s', lead.key, chat, exc)

    def register(self, app, *, group):
        from telegram.ext import CallbackQueryHandler, MessageHandler, filters
        if group in app.handlers:
            raise ValueError('Reserve an unused handler group')
        app.add_handler(CallbackQueryHandler(self.callback, pattern=r'^ld:'), group=group)
        app.add_handler(CallbackQueryHandler(self.cancel), group=group)
        app.add_handler(MessageHandler((filters.TEXT & ~filters.COMMAND) | filters.Document.ALL | filters.PHOTO,
                                       self.message), group=group)
        if app.job_queue is not None and not app.job_queue.get_jobs_by_name(JOB):
            app.job_queue.run_repeating(self.remind, interval=900, first=120, name=JOB)


def pending(app, user_id):
    """True while the desk waits for this person's next message (a note or the contract number)."""
    return bool((app.user_data.get(user_id) or {}).get(WAIT))


def register(app, *, owner_id):
    """Compose the desk in the client bot: the order package, visits, crm.db. Without the order package the desk
    is not shown (the bot works as before)."""
    import time
    from ua_order import host
    from ua_order.bindings import first_group
    from ua_order.crm import detail_view
    import db
    import visits
    from ua_lead_desk_store import Store
    from ua_lead_sources import Sources
    from ua_order_book import OrderBook
    loaded = host.current()
    if loaded is None or loaded is host.UNAVAILABLE:
        return None
    owner = int(owner_id)

    def authorize(update):
        # Staff only, in their private chat. Today: the owner (MANAGER_CHAT_ID); more staff later.
        return bool(update.effective_user and update.effective_chat and update.effective_chat.type == 'private'
                    and update.effective_user.id == owner and update.effective_chat.id == owner)

    store, book = Store(db.connect), OrderBook(db.connect)
    store.initialize()
    book.initialize()
    sources = Sources(loaded.service.repository, loaded.service.catalog, detail_view, visits.all_leads,
                      datetime.timezone.utc)
    desk = Desk(sources, store, book, authorize=authorize, recipients=lambda: [owner], clock=time.time)
    desk.register(app, group=first_group(app))
    return desk
