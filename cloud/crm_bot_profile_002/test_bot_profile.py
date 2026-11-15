"""ua_bot_profile against a fake bot (no network). Run: python3 cloud/crm_bot_profile_001/test_bot_profile.py"""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest

HERE = Path(__file__).resolve().parent
if importlib.util.find_spec('telegram') is None:  # CI has no python-telegram-bot: a minimal stand-in
    fake = types.ModuleType('telegram')

    class BotCommand:
        def __init__(self, command, description):
            self.command, self.description = command, description
    fake.BotCommand = BotCommand
    fake.Bot = object
    sys.modules['telegram'] = fake
spec = importlib.util.spec_from_file_location('ua_bot_profile', HERE / 'ua_bot_profile.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
NS = types.SimpleNamespace


class Bot:
    def __init__(self, description='', short='', commands=(('start', 'Меню'), ('cancel', 'Отменить текущее действие'))):
        self.d, self.s, self.c, self.calls = description, short, [NS(command=a, description=b) for a, b in commands], []

    async def get_my_description(self):
        return NS(description=self.d)

    async def get_my_short_description(self):
        return NS(short_description=self.s)

    async def get_my_commands(self):
        return self.c

    async def set_my_description(self, value):
        self.calls.append('set_description'); self.d = value

    async def set_my_short_description(self, value):
        self.calls.append('set_short'); self.s = value

    async def set_my_commands(self, value):
        self.calls.append('set_commands'); self.c = value


class Jobs:
    def __init__(self):
        self.jobs = []

    def get_jobs_by_name(self, name):
        return [j for j in self.jobs if j[2] == name]

    def run_once(self, callback, when, name):
        self.jobs.append((callback, when, name))


class ProfileTests(unittest.TestCase):
    def test_crm_sets_what_differs_then_nothing(self):
        bot = Bot()
        self.assertEqual(asyncio.run(p.apply(bot, p.CRM)), ['description', 'short_description', 'commands'])
        self.assertEqual([(c.command, c.description) for c in bot.c], [('start', '🏠 Главная'), ('cancel', '✖️ Отменить действие')])
        bot.calls.clear()
        self.assertEqual(asyncio.run(p.apply(bot, p.CRM)), [])
        self.assertEqual(bot.calls, [])

    def test_client_menu_only_main(self):
        bot = Bot(commands=())
        self.assertEqual(asyncio.run(p.apply(bot, p.CLIENT)), ['description', 'short_description', 'commands'])
        self.assertEqual([(c.command, c.description) for c in bot.c], [('start', 'Главное меню')])
        self.assertIn('Кореи и Японии', bot.d)

    def test_limits(self):
        for texts in (p.CRM, p.CLIENT):
            self.assertLessEqual(len(texts['description']), 512)
            self.assertLessEqual(len(texts['short_description']), 120)

    def test_register_once_and_failures_only_log(self):
        app = NS(job_queue=Jobs())
        p.register(app); p.register(app)
        self.assertEqual(len(app.job_queue.jobs), 1)
        self.assertEqual(app.job_queue.jobs[0][1], p.DELAY)

        class Broken(Bot):
            async def get_my_description(self):
                raise RuntimeError('network')
        saved = p.CLIENT_TOKEN_FILE
        p.CLIENT_TOKEN_FILE = '/nonexistent/bot_token.txt'
        try:
            with self.assertLogs(p.log, 'WARNING') as logs:
                asyncio.run(p._job(NS(bot=Broken())))
        finally:
            p.CLIENT_TOKEN_FILE = saved
        self.assertEqual(len(logs.records), 2)
        p.register(NS(job_queue=None))


if __name__ == '__main__':
    unittest.main()
