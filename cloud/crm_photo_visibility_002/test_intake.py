"""Exercise the transformed callback against explicit gallery and inbox state."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from candidate_builder import patch_intake


SOURCE = '''async def save(context, db, draft, card_id, actor):
    # переносим фото и видео из входящего сообщения
    import team_bot
    foto, video = team_bot.collect_media(draft["inbox_id"])
    if foto:
        db.update_card_field("cars", card_id, "photos", foto, actor)
        db.archive(card_id, foto, actor)
    if video:
        db.update_card_field("cars", card_id, "video_h", video[0], actor)
    db.link_inbox_card(draft["inbox_id"], "cars", card_id, actor)
    db.set_inbox_status(draft["inbox_id"], "approved", actor)
    context.user_data.pop("ai_draft", None)
'''


class IntakeTests(unittest.TestCase):
    def test_ocr_photo_never_becomes_gallery_photo_and_inbox_is_linked(self):
        writes = []
        links = []
        statuses = []
        context = types.SimpleNamespace(user_data={'ai_draft': {'inbox_id': 91}})
        db = types.SimpleNamespace(
            update_card_field=lambda *args: writes.append(args),
            link_inbox_card=lambda *args: links.append(args),
            set_inbox_status=lambda *args: statuses.append(args))
        bot = types.SimpleNamespace(collect_media=lambda ident: (['technical-source'], ['video']))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'intake_fixture.py'
            path.write_text(patch_intake(SOURCE))
            spec = importlib.util.spec_from_file_location('intake_fixture', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with patch.dict(sys.modules, team_bot=bot):
                asyncio.run(module.save(context, db, {'inbox_id':91}, 33, 'owner'))
        self.assertEqual(writes, [('cars', 33, 'video_h', 'video', 'owner')])
        self.assertEqual(links, [(91, 'cars', 33, 'owner')])
        self.assertEqual(statuses, [(91, 'approved', 'owner')])
        self.assertEqual(context.user_data, {})

    def test_unexpected_callback_shape_stops_the_release(self):
        for source in (SOURCE.replace('if foto:', 'if other:'),
                       SOURCE.replace('"photos"', '"other"'),
                       SOURCE.replace('async def save', 'async def other')):
            with self.subTest(source=source), self.assertRaises(ValueError):
                patch_intake(source)


if __name__ == '__main__':
    unittest.main()
