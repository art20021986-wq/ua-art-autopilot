import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cars_ui_transform import transform_cars_ui, scan_reachable_call_graph  # noqa: E402


class CarsUiTransformTests(unittest.TestCase):
    def test_direct_simple_media_call_transforms_cleanly(self):
        src = (
            "async def admin_car_view(message, bot):\n"
            "    await message.reply_photo(open('car.jpg', 'rb'), caption='Car')\n"
            "    await message.reply_video(open('car.mp4', 'rb'))\n"
        )
        result = transform_cars_ui(src, ['admin_car_view'])
        self.assertEqual(result['status'], 'OK')
        candidate = result['candidate']
        self.assertNotIn('open(', candidate)
        self.assertIn('reply_text', candidate)
        compile(candidate, '<test>', 'exec')

    def test_reachable_private_helper_exclusive_to_admin_transforms_cleanly(self):
        # Historical fixture name was 'nested helper media call blocks'.
        # The correct required behavior is that a helper reachable only
        # from an admin route, containing an exact direct media
        # expression, is rewritten cleanly (status OK), not blocked.
        src = (
            "def _send_car_photo(message):\n"
            "    message.reply_photo(open('car.jpg', 'rb'))\n"
            "\n"
            "def admin_car_edit(message):\n"
            "    _send_car_photo(message)\n"
        )
        result = transform_cars_ui(src, ['admin_car_edit'])
        self.assertEqual(result['status'], 'OK')
        candidate = result['candidate']
        self.assertNotIn('open(', candidate)
        self.assertNotIn('reply_photo', candidate)
        self.assertIn('reply_text', candidate)
        compile(candidate, '<test>', 'exec')

    def test_shared_helper_with_external_caller_blocks(self):
        src = (
            "def _send_car_photo(message):\n"
            "    message.reply_photo(open('car.jpg', 'rb'))\n"
            "\n"
            "def admin_car_edit(message):\n"
            "    _send_car_photo(message)\n"
            "\n"
            "def customer_car_view(message):\n"
            "    _send_car_photo(message)\n"
        )
        result = transform_cars_ui(src, ['admin_car_edit'])
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('shared_helper_called_by', result['reason'])

    def test_media_group_count_and_async_await_ok(self):
        src = (
            "async def admin_car_edit(message):\n"
            "    await message.reply_media_group([open('a.jpg', 'rb'), open('b.jpg', 'rb')])\n"
        )
        result = transform_cars_ui(src, ['admin_car_edit'])
        self.assertEqual(result['status'], 'OK')
        self.assertIn('2 item', result['candidate'])
        self.assertIn('await', result['candidate'])

    def test_open_call_outside_media_expression_blocks(self):
        src = (
            "def admin_car_delete(message):\n"
            "    f = open('car.jpg', 'rb')\n"
            "    message.reply_text('deleted')\n"
        )
        result = transform_cars_ui(src, ['admin_car_delete'])
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('unresolved_callable:open', result['reason'])

    def test_getattr_dynamic_dispatch_blocks(self):
        src = (
            "def admin_car_list(message):\n"
            "    getattr(message, 'reply_photo')(open('car.jpg', 'rb'))\n"
        )
        result = transform_cars_ui(src, ['admin_car_list'])
        self.assertEqual(result['status'], 'BLOCKED')

    def test_attribute_alias_assignment_blocks(self):
        src = (
            "def admin_car_list(message):\n"
            "    fn = message.reply_photo\n"
            "    fn(open('car.jpg', 'rb'))\n"
        )
        result = transform_cars_ui(src, ['admin_car_list'])
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('attribute_alias_reference', result['reason'])

    def test_lambda_wrapped_media_call_blocks(self):
        src = (
            "def admin_car_list(message):\n"
            "    handlers = [lambda: message.reply_photo(open('car.jpg', 'rb'))]\n"
            "    handlers[0]()\n"
        )
        result = transform_cars_ui(src, ['admin_car_list'])
        self.assertEqual(result['status'], 'BLOCKED')

    def test_callback_container_media_reference_blocks(self):
        src = (
            "def admin_car_list(message):\n"
            "    callbacks = {'photo': message.reply_photo}\n"
            "    callbacks['photo'](open('car.jpg', 'rb'))\n"
        )
        result = transform_cars_ui(src, ['admin_car_list'])
        self.assertEqual(result['status'], 'BLOCKED')

    def test_return_alias_of_media_method_blocks(self):
        src = (
            "def admin_car_list(message):\n"
            "    return message.reply_photo\n"
        )
        result = transform_cars_ui(src, ['admin_car_list'])
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('attribute_alias_reference', result['reason'])

    def test_side_effectful_media_argument_helper_blocks(self):
        src = (
            "def _prepare_photo():\n"
            "    log_side_effect()\n"
            "    return b'data'\n"
            "\n"
            "def admin_car_view(message):\n"
            "    message.reply_photo(_prepare_photo())\n"
        )
        result = transform_cars_ui(src, ['admin_car_view'])
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('unsafe_media_argument_side_effect', result['reason'])

    def test_protected_customer_function_untouched_when_not_reachable(self):
        src = (
            "def customer_car_view(message):\n"
            "    message.reply_photo(open('x.jpg', 'rb'))\n"
            "\n"
            "def admin_car_view(message):\n"
            "    message.reply_photo(open('y.jpg', 'rb'))\n"
        )
        result = transform_cars_ui(src, ['admin_car_view'])
        self.assertEqual(result['status'], 'OK')
        candidate_tree = ast.parse(result['candidate'])
        funcs = {n.name: n for n in candidate_tree.body if isinstance(n, ast.FunctionDef)}
        customer_src = ast.dump(funcs['customer_car_view'])
        admin_src = ast.dump(funcs['admin_car_view'])
        self.assertIn('reply_photo', customer_src)
        self.assertNotIn('reply_photo', admin_src)

    def test_missing_entry_point_blocks(self):
        src = (
            "def admin_car_view(message):\n"
            "    message.reply_photo(open('x.jpg', 'rb'))\n"
        )
        result = transform_cars_ui(src, ['admin_car_missing'])
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('missing_entry_points', result['reason'])

    def test_candidate_compiles_for_all_ok_cases(self):
        src = (
            "async def admin_car_view(message, bot):\n"
            "    await message.reply_photo(open('car.jpg', 'rb'))\n"
            "\n"
            "def admin_car_list(message):\n"
            "    message.reply_document(open('doc.pdf', 'rb'))\n"
        )
        result = transform_cars_ui(src, ['admin_car_view', 'admin_car_list'])
        self.assertEqual(result['status'], 'OK')
        compile(result['candidate'], '<test>', 'exec')


if __name__ == '__main__':
    unittest.main()
