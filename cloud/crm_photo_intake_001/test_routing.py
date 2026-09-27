import asyncio
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import crm_photo_intake as intake
import test_intake as fixtures
from test_intake import PHOTO, MAPS


class Stop(Exception):
    pass


class Filter:
    def __and__(self, other): return self
    def __or__(self, other): return self
    def __invert__(self): return self


class Message:
    def __init__(self, ident=123, text=None, photo=True):
        self.chat_id=10; self.message_id=ident; self.text=text
        self.caption=None; self.media_group_id=None; self.document=None
        self.photo=[SimpleNamespace(file_id='test-photo',file_size=100)] if photo else []
        self.replies=[]
    async def reply_text(self,text,**kwargs):
        self.replies.append(text); return self
    async def edit_text(self,text,**kwargs):
        self.replies.append(text)


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store=fixtures.StoreTests(); self.store.setUp()
        db=self.store.db
        db.ROLE_OWNER='owner'; db.get_staff=lambda uid:dict(user_id=uid,role='owner',active=1)
        tg=ModuleType('telegram'); ext=ModuleType('telegram.ext')
        tg.InlineKeyboardButton=lambda *args,**kwargs:(args,kwargs)
        tg.InlineKeyboardMarkup=lambda rows:rows
        ext.ApplicationHandlerStop=Stop
        ext.MessageHandler=lambda f,callback:SimpleNamespace(callback=callback)
        f=Filter(); ext.filters=SimpleNamespace(PHOTO=f,TEXT=f,COMMAND=f,Document=SimpleNamespace(IMAGE=f))
        self.imports=patch.dict('sys.modules',{'telegram':tg,'telegram.ext':ext});self.imports.start()
        self.tasks=[]
        def add_handler(handler,group): self.handler=handler.callback;self.group=group
        def create_task(coroutine,**kwargs): self.tasks.append(asyncio.create_task(coroutine))
        app=SimpleNamespace(add_handler=add_handler,create_task=create_task)
        self.ai=SimpleNamespace(is_stopped=lambda:False)
        self.ai_filter=SimpleNamespace(ALLOWED=intake.parse.__globals__['LABELS'],S=self.store.schema,
              ORDER=list(intake.parse.__globals__['LABELS']),LABELS={k:k for k in intake.parse.__globals__['LABELS']},
              FUEL=MAPS['fuel'],GEARBOX=MAPS['gearbox'],DRIVE=MAPS['drive'],COLOR=MAPS['color'])
        async def get_file(fid):
            async def download_as_bytearray(): return b'test-image'
            return SimpleNamespace(download_as_bytearray=download_as_bytearray)
        self.context=SimpleNamespace(user_data={},bot=SimpleNamespace(get_file=get_file))
        intake.register(app,db,self.ai_filter,SimpleNamespace(),self.ai)
        self.ocr=patch.object(intake,'photo_text',return_value=PHOTO);self.ocr.start()

    async def asyncTearDown(self):
        await asyncio.gather(*self.tasks)
        self.ocr.stop();self.imports.stop();self.store.tearDown()

    async def dispatch(self,msg,stop=True):
        update=SimpleNamespace(effective_message=msg,effective_user=SimpleNamespace(id=7))
        if stop:
            with self.assertRaises(Stop):await self.handler(update,self.context)
        else: await self.handler(update,self.context)

    def cards(self):
        with self.store.db.connect() as c:return [dict(r) for r in c.execute('SELECT * FROM cars')]

    async def test_photo_saves_then_followup_fills_same_card(self):
        await self.dispatch(Message())
        await asyncio.gather(*self.tasks)
        await self.dispatch(Message(124,'Марка: Kia\nМодель: K5',False))
        await asyncio.gather(*self.tasks)
        self.assertEqual(len(self.cards()),1)
        self.assertEqual(self.cards()[0]['model'],'K5')
        self.assertEqual(self.cards()[0]['mileage_km'],109353)
        self.assertEqual(self.group,-3)

    async def test_followup_arriving_before_photo_completion_is_queued(self):
        await self.dispatch(Message())
        await self.dispatch(Message(124,'Марка: Kia',False))
        await asyncio.gather(*self.tasks)
        self.assertEqual(self.cards()[0]['brand'],'Kia')

    async def test_inactive_owner_cannot_write(self):
        self.store.db.get_staff=lambda uid:dict(user_id=uid,role='owner',active=0)
        await self.dispatch(Message(),stop=False)
        self.assertEqual(self.tasks,[])

    async def test_selected_media_or_field_editor_keeps_routing(self):
        for key in ('car_media_wait','car_wait','card','ai_draft'):
            self.context.user_data={key:{'card_id':1}}
            await self.dispatch(Message(),stop=False)
        self.assertEqual(self.tasks,[])

    async def test_photo_without_vin_never_fills_last_car(self):
        card,_,_=self.store.write()
        self.context.user_data={'car_last':card['id'],intake.STATE:card['id']}
        self.ocr.stop();self.ocr=patch.object(intake,'photo_text',return_value='Model K5');self.ocr.start()
        await self.dispatch(Message(124))
        await asyncio.gather(*self.tasks)
        self.assertIsNone(self.cards()[0]['model'])

    async def test_old_navigation_not_overwritten_while_processing(self):
        original_save=intake.save
        def navigating_save(*args):
            self.context.user_data['car_last']=99
            return original_save(*args)
        with patch.object(intake,'save',side_effect=navigating_save):
            await self.dispatch(Message())
            await asyncio.gather(*self.tasks)
        self.assertEqual(self.context.user_data['car_last'],99)


if __name__=='__main__':unittest.main()
