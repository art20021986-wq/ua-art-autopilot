"""Customer intake and the owner's private inbox in the client bot."""
import asyncio
from .crm import detail_view
from .notifications import dispatch_once
from .telegram import CRMAdapter, CustomerAdapter, _markup

# All these entrances are present in client_ui.register (27 September 2026).
CUSTOMER_ENTRY = r'^(?:c_order$|c_ans:|lead_start|buycar:|ready$|custom_order$)'
CUSTOMER_EXIT = r'^(?:c_menu$|c_cars$|c_car:|c_bron:|c_vopros:|c_terms$|c_contacts$|show_cars$|show_transit$|adm_mycars$|show_terms$|contact_manager$)'
CUSTOMER_COMMANDS = ('start', 'cancel', 'cars', 'terms', 'help', 'mycar')
JOB_NAME = 'ua_order_outbox'


def first_group(app):
    # Imported host modules may add their own groups. Reserve an earlier unused
    # group only after all host registrations have finished; never clear them.
    return min(app.handlers, default=0) - 1


def customer(app, runtime):
    adapter = CustomerAdapter(
        runtime.service, runtime.strings, runtime.consent_text,
        media_root=runtime.media_root, allow_update=runtime.allow_update,
        menu_callback='c_menu',
    )
    adapter.register(app, group=first_group(app), entry_pattern=CUSTOMER_ENTRY,
                     exit_pattern=CUSTOMER_EXIT, exit_commands=CUSTOMER_COMMANDS)
    return adapter


def owner_inbox(app, runtime, *, owner_id):
    owner_id = int(owner_id)
    if owner_id <= 0:
        raise ValueError('A private owner chat is required for order delivery')
    if not app.job_queue:
        raise ValueError('The existing client job queue is required for order delivery')
    if app.job_queue.get_jobs_by_name(JOB_NAME):
        raise ValueError('Order delivery is already registered')

    def authorize(update):
        return bool(update.effective_user and update.effective_chat
                    and update.effective_chat.type == 'private'
                    and update.effective_user.id == owner_id
                    and update.effective_chat.id == owner_id)

    adapter = CRMAdapter(runtime.service.repository, runtime.service.catalog,
                         authorize=authorize, menu_callback='v_start')
    adapter.register(app, group=first_group(app))

    async def deliver(row):
        # The same client bot owns both the notification and its callback.
        view = detail_view(row, runtime.service.catalog)
        repository = runtime.service.repository
        request_id = row['data']['request_id']
        sent = await asyncio.to_thread(repository.notification_recipients_sent, request_id)

        if owner_id not in sent:
            await app.bot.send_message(
                chat_id=owner_id, text=view['text'], parse_mode='HTML',
                reply_markup=_markup([[('Открыть заявку', f'orders:open:{row["id"]}')]]),
            )
            await asyncio.to_thread(repository.notification_recipient_sent, request_id, owner_id)

    async def job(context):
        await dispatch_once(runtime.service.repository, deliver)

    app.job_queue.run_repeating(job, interval=5, first=1, name=JOB_NAME)
    return adapter
