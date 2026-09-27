"""Adapters for the project's existing python-telegram-bot applications.

No bot is created here. Registration is explicit; the host supplies existing
staff authorization, rate limiting, media root and the approved consent text.
"""
import asyncio
import copy
from pathlib import Path
import re
import sqlite3

from . import bot_flow, crm, legacy
from .contract import Conflict, Invalid, decode
from .storage import NotFound, StorageUnavailable
from .service import Principal


def _markup(rows):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([[InlineKeyboardButton(label,**({'url':data} if data.startswith('https://www.uaart.com.ua/video/podbor.html?') else {'callback_data':data})) for label,data in row] for row in rows])


async def _menu(bot, chat, context, key, view, *, html=False):
    from telegram.error import BadRequest
    parts = view.get('parts', [view['text']])
    previous = context.user_data.get(key+'_parts') or ([context.user_data[key]] if context.user_data.get(key) else [])
    message_ids = []
    for index, text in enumerate(parts):
        options=dict(chat_id=chat, text=text,
                     reply_markup=_markup(view['buttons']) if index==len(parts)-1 else None,
                     parse_mode='HTML' if html else None)
        message_id=previous[index] if index<len(previous) else None
        if message_id:
            try:
                await bot.edit_message_text(message_id=message_id,**options)
                message_ids.append(message_id)
                continue
            except BadRequest as exc:
                reason=str(exc).lower()
                if 'message is not modified' in reason:
                    message_ids.append(message_id)
                    continue
                if 'message to edit not found' not in reason: raise
        message=await bot.send_message(**options)
        message_ids.append(message.message_id)
        # Retain partial progress if a later part needs a network retry.
        context.user_data[key+'_parts']=message_ids+previous[len(message_ids):]
    for old in previous[len(parts):]:
        try: await bot.delete_message(chat_id=chat,message_id=old)
        except BadRequest as exc:
            if 'message to delete not found' not in str(exc).lower(): raise
    context.user_data[key]=message_ids[0]
    context.user_data[key+'_parts']=message_ids


class CustomerAdapter:
    def __init__(self, service, strings, consent_text, *, media_root, allow_update,
                 menu_callback=None):
        self.service, self.strings, self.consent_text=service, strings, consent_text
        self.media_root=Path(media_root).resolve()
        self.allow_update=allow_update
        self.menu_callback=menu_callback
        if not callable(allow_update): raise ValueError('A rate limiter is required')

    def _actor(self, update, context):
        if not update.effective_user or not update.effective_chat or update.effective_chat.type != 'private':
            raise Invalid('private_chat')
        return Principal(f'telegram:{update.effective_user.id}', 'telegram_bot',
                         f'{context.bot.id}:{update.update_id}')

    async def show(self, update, context):
        state=context.user_data['order_flow']
        view=bot_flow.view(state,self.service.catalog,self.strings,self.consent_text)
        if self.menu_callback:
            label={'uk':'До головного меню','ru':'В главное меню','ka':'მთავარ მენიუში'}[state['data']['lang']]
            view['buttons'].append([(label,self.menu_callback)])
        await _menu(context.bot,update.effective_chat.id,context,'order_menu_id',view)
        old=context.user_data.get('order_photo_id')
        selected=view['photo']
        if selected == context.user_data.get('order_photo_path'):
            return
        if old:
            from telegram.error import BadRequest
            try: await context.bot.delete_message(update.effective_chat.id,old)
            except BadRequest as exc:
                if 'message to delete not found' not in str(exc).lower(): raise
            context.user_data.pop('order_photo_id',None)
            context.user_data.pop('order_photo_path',None)
        if selected:
            path=(self.media_root/selected).resolve()
            if not path.is_relative_to(self.media_root) or not path.is_file():
                return  # The menu remains usable; deployment checks missing media.
            cache=context.bot_data.setdefault('order_photo_cache',{})
            model=self.service.catalog.model(state['data']['purchase_country_code'],state['data']['model'])
            media=model['media']
            caption=f'{media["alt"][state["data"]["lang"]]}\n{media["artist"]} · {media["license"]}\n{media["source"]}'
            if selected in cache:
                message=await context.bot.send_photo(update.effective_chat.id,cache[selected],caption=caption)
            else:
                with path.open('rb') as photo:
                    message=await context.bot.send_photo(update.effective_chat.id,photo,caption=caption)
                cache[selected]=message.photo[-1].file_id
            context.user_data['order_photo_id']=message.message_id
            context.user_data['order_photo_path']=selected

    async def start(self, update, context):
        from telegram.ext import ApplicationHandlerStop
        self._actor(update,context)
        if update.callback_query:
            await update.callback_query.answer()
        if not self.allow_update(update): raise ApplicationHandlerStop
        context.user_data.pop('podbor',None)
        text='' if update.callback_query else (update.effective_message.text or '')
        value=text.split(maxsplit=1)[1] if ' ' in text else ''
        data=None
        try:
            if value.startswith('or_'):
                data=await asyncio.to_thread(self.service.repository.redeem_draft,value[3:],f'telegram:{update.effective_user.id}')
            elif value:
                data=legacy.deep_link(value)
            state=bot_flow.create(self.service.catalog,data=data)
            if data:
                state['step']='review' if value.startswith('or_') else 'models'
            context.user_data['order_flow']=state
            await self.show(update,context)
        except NotFound:
            await update.effective_message.reply_text(self.strings['uk']['stale'])
        raise ApplicationHandlerStop

    async def callback(self, update, context):
        from telegram.ext import ApplicationHandlerStop
        query=update.callback_query
        actor=self._actor(update,context)
        await query.answer()  # Acknowledge before database work or network photos.
        state=context.user_data.get('order_flow')
        parts=query.data.split(':',4)
        if not state or len(parts)!=5 or parts[1]!=state['nonce'] or parts[2]!=str(state['revision']):
            receipt=None
            if len(parts)==5:
                try:
                    receipt=await asyncio.to_thread(self.service.repository.receipt_for_owner,parts[1],actor.owner)
                except NotFound: pass
            reply=f'{self.strings["uk"]["saved"]}: {receipt["number"]}' if receipt else self.strings['uk']['stale']
            await context.bot.send_message(update.effective_chat.id,reply)
            raise ApplicationHandlerStop
        if not self.allow_update(update): raise ApplicationHandlerStop
        try:
            if parts[3]=='submit':
                if state['step']!='review': raise Invalid('step')
                if not state['receipt']:
                    payload=copy.deepcopy(state['data'])
                    payload['consent']={'accepted':True,'version':self.service.consent_version}
                    state['receipt']=await asyncio.to_thread(self.service.submit,payload,actor)
            else:
                bot_flow.transition(state,parts[3],parts[4],self.service.catalog)
            await self.show(update,context)
        except (Invalid,Conflict,sqlite3.Error,StorageUnavailable):
            await context.bot.send_message(update.effective_chat.id,self.strings[state['data']['lang']]['invalid'])
        raise ApplicationHandlerStop

    async def message(self, update, context):
        from telegram.ext import ApplicationHandlerStop
        state=context.user_data.get('order_flow')
        if not state or state['receipt']: return
        self._actor(update,context)
        if not self.allow_update(update): raise ApplicationHandlerStop
        try:
            bot_flow.enter_text(state,update.effective_message.text or '')
            await self.show(update,context)
        except Invalid:
            await update.effective_message.reply_text(self.strings[state['data']['lang']]['invalid'])
        raise ApplicationHandlerStop

    async def webapp(self, update, context):
        from telegram.ext import ApplicationHandlerStop
        actor=self._actor(update,context)
        try:
            payload=decode(update.effective_message.web_app_data.data.encode())
            if payload.get('t')!='podbor' and payload.get('schema_version') not in ('ua_order_request.v1','ua_order_request.v2'):
                return
            if not self.allow_update(update): raise ApplicationHandlerStop
            if payload.get('t')=='podbor':
                state=bot_flow.create(self.service.catalog,data=legacy.draft(payload,self.service.catalog))
                state['step']='delivery_country' if state['data']['model'] or state['data']['other_model'] else 'models'
            else:
                state=bot_flow.create(self.service.catalog,data=payload)
                state['receipt']=await asyncio.to_thread(self.service.submit,payload,actor)
            context.user_data['order_flow']=state
            await self.show(update,context)
        except (Invalid,Conflict,sqlite3.Error,StorageUnavailable):
            await update.effective_message.reply_text(self.strings['uk']['invalid'])
        raise ApplicationHandlerStop

    async def clear(self, update, context):
        context.user_data.pop('order_flow',None)

    def register(self, app, *, group, entry_pattern=None, exit_pattern=None,
                 exit_commands=('start','cancel')):
        from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters
        if app.concurrent_updates > 1:
            raise ValueError('Bind to sequential updates or add the host per-user queue first')
        if group in app.handlers:
            raise ValueError('The host must reserve an unused handler group')
        app.add_handler(CommandHandler('order',self.start),group=group)
        app.add_handler(CallbackQueryHandler(self.start,pattern=r'^order:open$'),group=group)
        if entry_pattern:
            app.add_handler(CallbackQueryHandler(self.start,pattern=entry_pattern),group=group)
        app.add_handler(MessageHandler(filters.Regex(r'^/start(?:@\w+)? (?:z_|or_)'),self.start),group=group)
        app.add_handler(CallbackQueryHandler(self.callback,pattern=r'^ord:'),group=group)
        app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA,self.webapp),group=group)
        app.add_handler(CommandHandler(exit_commands,self.clear),group=group)
        if exit_pattern:
            # Clear only our state, then let the existing host screen handle it.
            app.add_handler(CallbackQueryHandler(self.clear,pattern=exit_pattern),group=group)
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,self.message),group=group)


class CRMAdapter:
    def __init__(self, repository, catalog, *, authorize, menu_callback='menu'):
        self.repository,self.catalog,self.authorize=repository,catalog,authorize
        self.menu_callback=menu_callback

    async def callback(self,update,context):
        from telegram.ext import ApplicationHandlerStop
        query=update.callback_query
        # The host's authorization is checked before every database read.
        if not self.authorize(update):
            await query.answer('Недостаточно прав',show_alert=True)
            raise ApplicationHandlerStop
        await query.answer()
        value=query.data
        try:
            if re.fullmatch(r'orders:list(?::[1-9][0-9]{0,17})?',value):
                before=int(value.rsplit(':',1)[1]) if value.count(':')==2 else None
                view=await asyncio.to_thread(crm.list_view,self.repository,self.catalog,
                                             before=before,menu_callback=self.menu_callback)
            elif re.fullmatch(r'orders:open:[1-9][0-9]{0,17}',value):
                row=await asyncio.to_thread(self.repository.detail,int(value.rsplit(':',1)[1]))
                view=crm.detail_view(row,self.catalog)
            else: raise NotFound()
        except NotFound:
            view={'text':'Заявка не найдена','buttons':[[('К заявкам','orders:list')]]}
        await _menu(context.bot,update.effective_chat.id,context,'order_crm_menu_id',view,html=True)
        raise ApplicationHandlerStop

    def register(self,app,*,group):
        from telegram.ext import CallbackQueryHandler
        if group in app.handlers: raise ValueError('Reserve an unused handler group')
        app.add_handler(CallbackQueryHandler(self.callback,pattern=r'^orders:'),group=group)
