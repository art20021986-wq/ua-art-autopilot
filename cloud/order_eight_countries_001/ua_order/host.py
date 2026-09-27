"""Explicit composition for customer intake, the owner inbox and the website."""
from functools import lru_cache
import logging

from . import bindings, runtime
from .contract import Invalid, decode
from .web import WebAdapter, mount

UNAVAILABLE = object()
log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def current():
    try:
        return runtime.load()
    except Exception as exc:
        # Isolate this optional feature from inventory and the existing bots.
        # Details belong in the release preflight, never expose secrets to users.
        log.error('Order feature unavailable; configuration check failed (%s)', type(exc).__name__)
        return UNAVAILABLE


def customer_label():
    return 'Подобрать авто под заказ' if current() else 'Подобрать под заказ из Кореи'


def register_customer(app, *, owner_id):
    loaded = current()
    if loaded is UNAVAILABLE:
        return _unavailable_customer(app)
    if loaded is None:
        return None
    adapter = bindings.customer(app, loaded)
    bindings.owner_inbox(app, loaded, owner_id=owner_id)
    return adapter


def mount_application(application):
    loaded = current()
    if loaded is None:
        return application
    if loaded is UNAVAILABLE:
        def unavailable(env, start_response):
            body = b'{"error":"temporarily_unavailable"}'
            start_response('503 Service Unavailable', [
                ('Content-Type', 'application/json; charset=utf-8'),
                ('Cache-Control', 'no-store'), ('Content-Length', str(len(body))),
            ])
            return [body]
        return mount(application, unavailable)
    adapter = WebAdapter(
        loaded.service, loaded.sessions, origin=loaded.origin,
        consent_text=loaded.consent_text, allow_request=loaded.allow_request,
        bot_token=loaded.bot_token,
    )
    return mount(application, adapter)


def _unavailable_customer(app):
    from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, CommandHandler, MessageHandler, filters

    async def unavailable(update, context):
        message = update.effective_message
        if message and message.web_app_data:
            try:
                payload = decode(message.web_app_data.data.encode())
            except Invalid:
                return
            if payload.get('t') != 'podbor' and payload.get('schema_version') not in ('ua_order_request.v1', 'ua_order_request.v2'):
                return
        text = 'Підбір тимчасово недоступний. Спробуйте пізніше.'
        if update.callback_query:
            await update.callback_query.answer(text, show_alert=True)
        elif message:
            await message.reply_text(text)
        raise ApplicationHandlerStop

    group = bindings.first_group(app)
    app.add_handler(CommandHandler('order', unavailable), group=group)
    app.add_handler(CallbackQueryHandler(unavailable,
        pattern=bindings.CUSTOMER_ENTRY + r'|^order:open$|^ord:'), group=group)
    app.add_handler(MessageHandler(filters.Regex(r'^/start(?:@\w+)? (?:z_|or_)'), unavailable), group=group)
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, unavailable), group=group)
    return unavailable
