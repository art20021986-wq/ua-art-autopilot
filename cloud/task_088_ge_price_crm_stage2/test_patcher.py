"""In-memory transformation tests; no live source or database is executed."""
import ast
import unittest
import patcher as p

FIXTURE = '''from __future__ import annotations
EDITABLE = [("vin", "VIN"), ("price_uah", "Цена Украины"), ("price_georgia", "Цена Грузии")]
MONEY = {"price_uah", "price_georgia"}
NUMERIC = {"price_uah", "price_georgia"}
def unrelated():
    return "keep all other functionality"
def apply_value(card_id, field, raw, actor_id):
    """Existing validation."""
    return legacy_apply(card_id, field, raw, actor_id)
async def auto_catch(msg, card, actor_id, context):
    """Existing auto parser."""
    return await legacy_auto(msg, card, actor_id, context)
async def catch_message(update, context):
    msg = update.message
    user_id = update.effective_user.id
    input_text = msg.text
    thinking = None
    wait = context.user_data.get("car_wait")
    if not wait:
        return await auto_catch(msg, card, user_id, context)
    return legacy_route(wait, input_text)
'''


class PatcherTests(unittest.TestCase):
    def test_candidate_preserves_unrelated_code_and_original_handler_statements(self):
        result, evidence = p.build_candidate(FIXTURE, expected_sha256=p.digest(FIXTURE))
        self.assertEqual(evidence['status'], 'CANDIDATE_ONLY')
        self.assertEqual(evidence['installation'], 'NOT_PERFORMED')
        self.assertEqual(evidence['changed_functions'], list(p.TARGETS))
        self.assertEqual(ast.dump(p.function(FIXTURE,'unrelated')), ast.dump(p.function(result,'unrelated')))
        body = p.function(result, 'catch_message').body
        explicit = next(i for i,n in enumerate(body) if isinstance(n, ast.If) and '_task088_apply_selected_price' in ast.unparse(n))
        general = next(i for i,n in enumerate(body) if isinstance(n, ast.If) and ast.unparse(n.test) == 'not wait')
        self.assertLess(explicit, general)
        self.assertIn('wait[\'field\']', ast.unparse(body[explicit]))
        self.assertNotIn('ALTER TABLE', result)

    def test_fingerprint_prevents_unreviewed_live_patch(self):
        with self.assertRaisesRegex(p.Refused, 'LIVE_SOURCE_SHA_MISMATCH'):
            p.build_candidate(FIXTURE)

    def test_generic_ukraine_route_retains_original_history_behavior(self):
        result, _ = p.build_candidate(FIXTURE, expected_sha256=p.digest(FIXTURE))
        node = p.function(result, 'apply_value')
        added = next(n for n in node.body if isinstance(n, ast.If))
        self.assertEqual(ast.unparse(added.test), "field == 'price_georgia'")
        catch = p.function(result, 'catch_message')
        branch = next(n for n in catch.body if isinstance(n, ast.If) and '_task088_apply_selected_price' in ast.unparse(n))
        self.assertIn("('price_uah', 'price_georgia')", ast.unparse(branch.test))

    def test_missing_stage1_binding_refuses(self):
        source = FIXTURE.replace('("price_georgia", "Цена Грузии")', '("cost_purchase", "Purchase")')
        with self.assertRaisesRegex(p.Refused, 'STAGE1_PRICE_BINDINGS_REQUIRED'):
            p.build_candidate(source, expected_sha256=p.digest(source))

    def test_unknown_catch_structure_refuses(self):
        source = FIXTURE.replace('    thinking = None\n', '')
        with self.assertRaisesRegex(p.Refused, 'CATCH_INPUT_ANCHOR'):
            p.build_candidate(source, expected_sha256=p.digest(source))

    def test_repeat_refuses_without_changing_candidate(self):
        result, _ = p.build_candidate(FIXTURE, expected_sha256=p.digest(FIXTURE))
        with self.assertRaisesRegex(p.Refused, 'PARTIAL_OR_EXISTING_STAGE2'):
            p.build_candidate(result, expected_sha256=p.digest(result))


if __name__ == '__main__':
    unittest.main()
