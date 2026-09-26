"""Telegram adapter for the durable deletion coordinator; no import effects.

The live runtime must explicitly construct the reviewed Coordinator. This module
never creates a database schema, invents site routes, or removes media files.
"""
import asyncio
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationHandlerStop


APP_KEY = 'ua_delete_recovery_002'
JOB_NAME = 'ua-delete-recovery-002'


class CoordinatorBackend:
    """Use the real coordinator; all public methods are synchronous workers."""
    def __init__(self, coordinator):
        self.coordinator = coordinator

    def confirmation(self, car_id, actor_id):
        token = self.coordinator.confirm(car_id=car_id, actor_id=actor_id)
        view = self.coordinator.confirmation(token=token, actor_id=actor_id)
        return dict(view, token=token, version=view['snapshot_sha256'])

    def admit(self, token, actor_id):
        return self.coordinator.admit(token=token, actor_id=actor_id)

    def describe(self, operation_id):
        with closing(self.coordinator.binding.connect()) as conn:
            row = conn.execute(
                'SELECT operation_id,car_id,car_code,actor_id,state,proof_sha256 '
                'FROM ua_delete_intents WHERE operation_id=?', (operation_id,)).fetchone()
        if row is None:
            raise RuntimeError('ORIGINAL_DURABLE_INTENT_REQUIRED')
        return dict(zip(('operation_id', 'car_id', 'car_code', 'actor_id',
                         'state', 'proof_sha256'), row))

    def resume(self, operation_id):
        result = self.coordinator.resume(operation_id=operation_id)
        if (result.get('status') != 'COMPLETE' or
                result.get('operation_id') != operation_id or
                result.get('media_writes') != 0 or
                not re.fullmatch(r'[0-9a-f]{64}', str(result.get('backup_manifest_sha256', '')))):
            raise RuntimeError('COORDINATOR_COMPLETION_NOT_VERIFIED')
        current = self.describe(operation_id)
        if (current['state'] != 'COMPLETE' or
                not re.fullmatch(r'[0-9a-f]{64}', str(current['proof_sha256'] or ''))):
            raise RuntimeError('DURABLE_COMPLETION_READ_BACK_FAILED')
        return current

    def pending(self):
        return self.coordinator.pending()

    def record_startup(self, *, phase, application_running=False, updater_running=False):
        journal = Path(self.coordinator.binding.journal_root)
        config = journal / 'runtime.json'
        if (journal.resolve(strict=True) != journal or journal.stat().st_mode & 0o077 or
                config.resolve(strict=True) != config or config.is_symlink()):
            raise RuntimeError('PRIVATE_RUNTIME_STARTUP_PATH_REQUIRED')
        raw = config.read_bytes()
        if json.loads(raw) != self.coordinator.binding.config:
            raise RuntimeError('STARTUP_CONFIG_CHANGED')
        ticks = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()[19]
        value = {'version': 1, 'phase': phase, 'pid': os.getpid(), 'start_ticks': ticks,
                 'config_sha256': hashlib.sha256(raw).hexdigest(),
                 'adapter_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 'adapter_registered': True, 'deletion_job_name': JOB_NAME,
                 'application_running': application_running is True,
                 'updater_running': updater_running is True,
                 'observed_epoch': time.time(), 'live_telegram_action_verified': False}
        path = journal / 'startup.json'
        if path.is_symlink():
            raise RuntimeError('STARTUP_RECEIPT_SYMLINK')
        temporary = path.with_name('startup.tmp-' + secrets.token_hex(8))
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, 'w') as output:
                json.dump(value, output, sort_keys=True)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
            fd = os.open(journal, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            if temporary.exists():
                temporary.unlink()
        return value


class TelegramDeletionAdapter:
    def __init__(self, backend, *, get_staff, ack, logger):
        self.backend, self.get_staff = backend, get_staff
        self.ack, self.log = ack, logger
        self._lock = asyncio.Lock()
        self._tokens = set()
        self._blocked = set()
        self._scan_failed = False

    @staticmethod
    def _back():
        return InlineKeyboardMarkup([[InlineKeyboardButton(
            '← Все автомобили', callback_data='cards_cars')]])

    async def _authorized(self, query):
        staff = await asyncio.to_thread(self.get_staff, query.from_user.id)
        if not staff:
            await query.message.reply_text('Доступ к CRM не разрешён.')
            return False
        return True

    def _schedule(self, context, coroutine):
        # PTB owns task shutdown and exception propagation. Never wait for the
        # full DB/HTTP operation in a sequential Telegram update handler.
        context.application.create_task(coroutine)

    async def _notify(self, query, text, **kwargs):
        try:
            await query.message.reply_text(text, **kwargs)
        except Exception:
            # A Telegram transport failure cannot change a committed operation
            # into a deletion failure or prevent already-admitted work.
            self.log.exception('UA002 deletion status delivery failed')

    async def delete_ask(self, update, context):
        query = update.callback_query
        await self.ack(query)
        match = re.fullmatch(r'car_del:([1-9][0-9]*)', str(query.data or ''))
        if not match:
            await query.message.reply_text('Кнопка устарела. Откройте карточку заново.')
        else:
            self._schedule(context, self._ask_flow(query, int(match.group(1))))
        raise ApplicationHandlerStop

    async def _ask_flow(self, query, car_id):
        try:
            if not await self._authorized(query):
                return
            view = await asyncio.to_thread(self.backend.confirmation, car_id, query.from_user.id)
            # Full canonical VIN and full row SHA remain bound in the durable
            # token. Existing CRM policy shows only the last four VIN symbols.
            vin = ('…' + view['vin'][-4:]) if view['vin'] else 'не указан'
            message = ('Удалить карточку {code}?\nID: {cid} · VIN: {vin}\n'
                       'Версия: {version}\n'
                       'Удаление будет завершено после проверки CRM, страниц '
                       'сайта и счётчиков. Файлы фото и видео сохраняются.').format(
                           code=view['car_code'], cid=view['car_id'], vin=vin,
                           version=view['version'][:12])
            await query.message.reply_text(message, reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('Да, удалить', callback_data='car_delok:' + view['token'])],
                [InlineKeyboardButton('← Отмена', callback_data='car_open:%d' % view['car_id'])]]))
        except Exception:
            self.log.exception('UA002 deletion confirmation failed')
            await query.message.reply_text(
                'Не удалось подготовить новое удаление. Обновите список карточек; '
                'если есть незавершённая операция, проверьте её статус.',
                reply_markup=self._back())

    async def delete_ok(self, update, context):
        query = update.callback_query
        await self.ack(query)
        match = re.fullmatch(r'car_delok:([0-9a-f]{32})', str(query.data or ''))
        if not match:
            # The old numeric ID callback is intentionally never upgraded to a
            # fresh deletion request: it may refer to a reused/different row.
            await query.message.reply_text('Подтверждение устарело. Откройте карточку и нажмите «Удалить» заново.')
            raise ApplicationHandlerStop
        token = match.group(1)
        if token in self._tokens:
            await query.message.reply_text('Эта операция уже выполняется. Результат проверки будет сообщён отдельно.')
            raise ApplicationHandlerStop
        self._tokens.add(token)
        self._schedule(context, self._delete_flow(query, context, token))
        raise ApplicationHandlerStop

    async def _delete_flow(self, query, context, token):
        operation_id = None
        try:
            if not await self._authorized(query):
                return
            await self._notify(query, 'Проверяю подтверждение и резервную копию. Удаление пока не завершено.')
            async with self._lock:
                intent = await asyncio.to_thread(self.backend.admit, token, query.from_user.id)
                operation_id = intent['operation_id']
                already_complete = intent['state'] == 'COMPLETE'
                self._blocked.discard(operation_id)
                if not already_complete:
                    await self._notify(query,
                        'Удаление {code} принято. Проверяю CRM и сайт.\nОперация: {op}'.format(
                            code=intent['car_code'], op=operation_id))
                result = await asyncio.to_thread(self.backend.resume, operation_id)
            if context.user_data.get('car_last') == result['car_id']:
                context.user_data.pop('car_last', None)
            if context.user_data.get('car_voice_active') == result['car_id']:
                context.user_data.pop('car_voice_active', None)
            await self._notify(query, self._success(result, already_complete), reply_markup=self._back())
        except Exception:
            if operation_id:
                self._blocked.add(operation_id)
            self.log.exception('UA002 deletion incomplete operation=%s', operation_id)
            await self._notify(query,
                'Завершение удаления не подтверждено: проверка не пройдена. ' +
                ('Дальнейшие изменения этой операции приостановлены. ' if operation_id else
                 'Результат операции не подтверждён. ') +
                ('Повторите это подтверждение для проверки и продолжения.' if operation_id else
                 'Обновите карточку; после её изменения нужно новое подтверждение.') +
                ('\nОперация: ' + operation_id if operation_id else ''),
                reply_markup=self._back())
        finally:
            self._tokens.discard(token)

    @staticmethod
    def _success(result, already_complete=False):
        if already_complete:
            return ('✅ Удаление {code} уже было завершено. Повторное удаление не выполнялось.\n'
                    'Операция: {op}').format(code=result['car_code'], op=result['operation_id'])
        return ('✅ Завершил — {code} удалена из CRM и с сайта; счётчики проверены.\n'
                'Операция: {op}').format(code=result['car_code'], op=result['operation_id'])

    async def resume_job(self, context):
        # Never pile up scans behind a slow HTTP operation. Errors suspend the
        # affected operation in this process; restart rechecks durable jobs.
        if self._lock.locked() or self._scan_failed:
            return
        async with self._lock:
            try:
                pending = await asyncio.to_thread(self.backend.pending)
            except Exception:
                self._scan_failed = True
                self.log.exception('UA002 durable deletion queue unavailable; automatic scan paused')
                return
            try:
                await asyncio.to_thread(self.backend.record_startup, phase='RUNNING',
                    application_running=getattr(context.application, 'running', False),
                    updater_running=getattr(getattr(context.application, 'updater', None), 'running', False))
            except Exception:
                self.log.exception('UA002 startup receipt could not confirm running adapter')
            for operation_id in pending:
                if operation_id in self._blocked:
                    continue
                intent = None
                try:
                    intent = await asyncio.to_thread(self.backend.describe, operation_id)
                    result = await asyncio.to_thread(self.backend.resume, operation_id)
                    text = self._success(result)
                except Exception:
                    self._blocked.add(operation_id)
                    self.log.exception('UA002 resumed deletion incomplete operation=%s', operation_id)
                    text = ('Удаление не завершено; автоматическое продолжение приостановлено.\n'
                            'Операция: ' + operation_id)
                if intent is not None:
                    # The recipient is the exact initiating Telegram actor
                    # recorded in the durable job; never infer an owner/chat.
                    try:
                        if await asyncio.to_thread(self.get_staff, intent['actor_id']):
                            await context.application.bot.send_message(chat_id=intent['actor_id'], text=text)
                    except Exception:
                        self.log.exception('UA002 job result notification failed operation=%s', operation_id)


def register_adapter(app, *, backend, get_staff, ack, logger):
    if app.job_queue is None:
        raise RuntimeError('DURABLE_DELETION_RESTART_JOB_QUEUE_REQUIRED')
    if APP_KEY in app.bot_data:
        return app.bot_data[APP_KEY]
    adapter = TelegramDeletionAdapter(backend, get_staff=get_staff, ack=ack, logger=logger)
    # Registration is explicit; schema is checked by the runtime factory.
    job = app.job_queue.run_repeating(adapter.resume_job, interval=30, first=1,
        name=JOB_NAME, job_kwargs={'max_instances': 1, 'coalesce': True})
    try:
        backend.record_startup(phase='REGISTERED')
    except Exception:
        if job is not None:
            job.schedule_removal()
        raise
    app.bot_data[APP_KEY] = adapter
    return adapter
