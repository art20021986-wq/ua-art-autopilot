"""Bindings verified against the current client_ui and team_bot interfaces."""
import asyncio
from .crm import FOLDER_LABEL, detail_view
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


def staff_allowed(staff, allowed_roles):
    return bool(staff and staff['active'] and staff['role'] in allowed_roles)


def manager_recipients(db):
    # Same manager-first, owner-fallback policy as team_bot.notify_managers,
    # with a fresh activity/role check before each delivery attempt.
    def active(role):
        return [user_id for user_id in db.staff_ids_by_role(role)
                if staff_allowed(db.get_staff(user_id), (role,))]
    return active(db.ROLE_MANAGER) or active(db.ROLE_OWNER)


def folder_button(staff, allowed_roles):
    from telegram import InlineKeyboardButton
    if not staff_allowed(staff, allowed_roles):
        return []
    return [InlineKeyboardButton(FOLDER_LABEL, callback_data='orders:list')]


def team(app, runtime, *, who, allowed_roles, recipients):
    if not app.job_queue:
        raise ValueError('The existing CRM job queue is required for order delivery')
    if app.job_queue.get_jobs_by_name(JOB_NAME):
        raise ValueError('Order delivery is already registered')

    def authorize(update):
        return bool(update.effective_user and update.effective_chat
                    and update.effective_chat.type == 'private'
                    and staff_allowed(who(update), allowed_roles))

    adapter = CRMAdapter(runtime.service.repository, runtime.service.catalog,
                         authorize=authorize)
    adapter.register(app, group=first_group(app))

    async def deliver(row):
        # Use the host's current recipient policy; re-evaluate it on every
        # attempt. This message belongs to the CRM bot that handles orders:*.
        targets = list(dict.fromkeys(recipients()))
        if not targets:
            raise RuntimeError('No active order recipient')
        view = detail_view(row, runtime.service.catalog)
        repository = runtime.service.repository
        request_id = row['data']['request_id']
        sent = await asyncio.to_thread(repository.notification_recipients_sent, request_id)

        async def send(chat_id):
            await app.bot.send_message(
                chat_id=chat_id, text=view['text'], parse_mode='HTML',
                reply_markup=_markup([[('Открыть заявку', f'orders:open:{row["id"]}')]]),
            )
            await asyncio.to_thread(repository.notification_recipient_sent, request_id, chat_id)

        # A failing/blocked recipient must not prevent the others from receiving
        # the order. Known successful deliveries are durable and are not retried.
        results = await asyncio.gather(*(send(target) for target in targets if target not in sent),
                                       return_exceptions=True)
        failures = [result for result in results if isinstance(result, BaseException)]
        if failures:
            raise RuntimeError('Order delivery remains pending for a recipient') from failures[0]

    async def job(context):
        await dispatch_once(runtime.service.repository, deliver)

    app.job_queue.run_repeating(job, interval=5, first=1, name=JOB_NAME)
    return adapter
