"""Signs of an attack and the owner's report (Russian, plain words) from the bot watch numbers; no I/O."""
import statistics

SPIKE = 3          # a day with this many times the usual page views by people …
SPIKE_FLOOR = 1500  # … and at least this many
ERRORS = 50        # server errors a day
ORDERS = 20        # order submissions a day (usually a few)
LEFT_OUT = 500     # counter beacons the guard left out in a day


def signs(days):
    """[(day, text)] for each day that looks like an attack."""
    found = []
    order = sorted(days)
    for n, day in enumerate(order):
        d = days[day]
        before = [days[x]['people_pages'] for x in order[max(0, n - 7):n]]
        usual = statistics.median(before) if before else None
        if usual and d['people_pages'] >= SPIKE * usual and d['people_pages'] >= SPIKE_FLOOR:
            found.append((day, 'открытий страниц в %.0f раз больше обычного (%d против ~%d)' % (
                d['people_pages'] / usual, d['people_pages'], usual)))
        if d['heavy_addresses']:
            busiest = d['busiest'] or {}
            found.append((day, 'один адрес открыл %d страниц (сеть %s, браузер: %s)' % (
                busiest.get('requests', 0), busiest.get('network', '?'), busiest.get('agent', '?')[:60])))
        if d['errors_5xx'] >= ERRORS:
            found.append((day, 'ошибок сервера: %d' % d['errors_5xx']))
        if d['order_submits'] >= ORDERS:
            found.append((day, 'отправок заявки: %d' % d['order_submits']))
        if d['beacons'] - d['recorded'] >= LEFT_OUT:
            found.append((day, 'счётчик отсеял %d отметок роботов' % (d['beacons'] - d['recorded'])))
    return found


def markdown(days, title, run_id, last=3):
    shown = sorted(days)[-last:]
    found = signs(days)
    recent = [(day, text) for day, text in found if day in shown]
    lines = ['# %s' % title, '',
             '**Итог: %s**' % ('⚠️ есть признаки атаки' if recent else '✅ признаков атаки нет'), '']
    for day, text in recent:
        lines.append('- %s: %s' % (day, text))
    if recent:
        lines.append('')
    lines += ['| День (UTC) | Запросов всего | Адресов | Честные роботы | Страниц у людей | Самый активный адрес (страниц) | '
              'Ошибки сервера | Отметки счётчика / записано | Заявки |',
              '|---|---|---|---|---|---|---|---|---|']
    for day in shown:
        d = days[day]
        busiest = d['busiest'] or {'network': '—', 'requests': 0}
        lines.append('| %s | %d | %d | %d | %d | %d (%s) | %d | %d / %d | %d |' % (
            day, d['requests'], d['addresses'], d['robot_requests'], d['people_pages'], busiest['requests'],
            busiest['network'],
            d['errors_5xx'], d['beacons'], d['recorded'], d['order_submits']))
    lines += ['', 'Как читать: «честные роботы» — поисковики (Google, Bing, ChatGPT и др.), они нужны. «Отметки счётчика / '
              'записано» — сколько отметок пришло и сколько счётчик записал; разница — отсеянные роботы. Признак атаки — '
              'резкий рост запросов, один адрес с тысячами запросов, много ошибок сервера или заявок.',
              '', 'Источник: журнал сервера и счётчик сайта, только чтение (запуск %s).' % run_id, '']
    return '\n'.join(lines), recent
