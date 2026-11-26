"""«🇺🇦 Посетители из Украины» in the client bot «📊 Аналитика» (owner «да» 2026-11-26 to the button, the screen and the
daily summary at 09:00 Kyiv). Screens only: the numbers come from ua_visitors_ua; sending and «Назад» from vitrina;
who may see it from analitika_knopka (full rights: owner and managing administrator see the same).

Callbacks: v_an_ua (period menu), v_an_ua_p:<period>:<page>, v_an_ua_own (custom period prompt),
v_an_ua_r:<YYYYMMDD>:<YYYYMMDD>:<page>. A custom period is sent as one message «01.11–25.11» (year optional).
"""
import datetime
import re

PREFIX = 'v_an_ua'
PERIODS = (('Сегодня', 'today'), ('Вчера', 'yesterday'), ('Неделя', '7d'), ('Месяц', '30d'))
RANGE = re.compile(r'^\s*(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\s*[-–—]\s*(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\s*$')
DAILY_AT = (9, 0)


def menu():
    return [[('📅 Сегодня', PREFIX + '_p:today:0'), ('📅 Вчера', PREFIX + '_p:yesterday:0')],
            [('📅 Неделя', PREFIX + '_p:7d:0'), ('📅 Месяц', PREFIX + '_p:30d:0')],
            [('📅 Свой период', PREFIX + '_own')],
            [('⬅️ Назад', 'v_analytics')]]


def pager(base, page, pages):
    row = []
    if page > 0:
        row.append(('◀️', '%s:%d' % (base, page - 1)))
    if page + 1 < pages:
        row.append(('▶️', '%s:%d' % (base, page + 1)))
    return ([row] if row else []) + [[('🇺🇦 Другой период', PREFIX)], [('⬅️ Назад', 'v_analytics')]]


def names():
    try:
        import analitika_yadro
        return analitika_yadro.nazvanie_stranicy
    except Exception:
        return None


def parse_range(text, today):
    """(first date, last date) from «01.11–25.11» (year optional), or None."""
    m = RANGE.match(text or '')
    if not m:
        return None

    def day(d, mth, y):
        year = int(y) + (2000 if y and len(y) == 2 else 0) if y else today.year
        return datetime.date(year, int(mth), int(d))
    try:
        first, last = day(*m.group(1, 2, 3)), day(*m.group(4, 5, 6))
    except ValueError:
        return None
    if first > last or (last - first).days > 400:
        return None
    return first, last


def screen(data, now=None):
    """(text, buttons) for a report callback."""
    import ua_visitors_ua as report
    parts = data.split(':')
    if parts[0] == PREFIX + '_p' and len(parts) == 3 and parts[1] in dict((v, k) for k, v in PERIODS):
        start, end, title = report.bounds(parts[1], now)
        base, page = '%s:%s' % (parts[0], parts[1]), int(parts[2])
    elif parts[0] == PREFIX + '_r' and len(parts) == 4:
        first = datetime.datetime.strptime(parts[1], '%Y%m%d').date()
        last = datetime.datetime.strptime(parts[2], '%Y%m%d').date()
        start, end, title = report.range_bounds(first, last)
        base, page = '%s:%s:%s' % tuple(parts[:3]), int(parts[3])
    else:
        return None
    text, pages = report.build(start, end, title, page, names=names())
    return text, pager(base, min(page, pages - 1), pages)


async def vetka(bot, chat_id, kto, data):
    """True when the callback belongs here (access is checked by analitika_knopka before)."""
    import vitrina
    if data == PREFIX:
        await vitrina.poslat(bot, chat_id, '🇺🇦 <b>Посетители из Украины</b>\nВыберите период:', menu())
        return True
    if data == PREFIX + '_own':
        await vitrina.poslat(bot, chat_id, 'Пришлите период одним сообщением, например: <b>01.11–25.11</b>',
                             [[('⬅️ Назад', PREFIX)]])
        return True
    try:
        result = screen(data)
    except Exception as error:
        result = ('Отчёт временно недоступен: %s' % type(error).__name__, menu())
    if result is None:
        return False
    await vitrina.poslat(bot, chat_id, result[0], result[1])
    return True


async def on_range(update, context):
    import analitika_knopka
    import vitrina
    if not analitika_knopka.vladelec_li(update.effective_user.id):
        return
    import ua_visitors_ua as report
    found = parse_range(update.effective_message.text, datetime.datetime.now(report.kyiv()).date())
    if not found:
        return
    data = '%s_r:%s:%s:0' % (PREFIX, found[0].strftime('%Y%m%d'), found[1].strftime('%Y%m%d'))
    text, buttons = screen(data)
    await vitrina.poslat(context.bot, update.effective_chat.id, text, buttons)


async def daily(context):
    """Yesterday's report to everyone with full rights, every day at 09:00 Kyiv."""
    import analitika_knopka
    import ua_full_access
    import vitrina
    text, buttons = screen(PREFIX + '_p:yesterday:0')
    for chat in ua_full_access.ids(analitika_knopka.vladelec_id()):
        try:
            await vitrina.poslat(context.bot, chat, '🌅 Сводка за вчера\n' + text, buttons)
        except Exception:
            pass


def register(app):
    """The custom-period message (only from people with full rights; a distinctive date-range text) and the daily job."""
    from telegram.ext import MessageHandler, filters
    import ua_visitors_ua as report
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & filters.Regex(RANGE), on_range), group=-1)
    if app.job_queue:
        app.job_queue.run_daily(daily, time=datetime.time(*DAILY_AT, tzinfo=report.kyiv()), name='ua_visitors_daily')
    return True
