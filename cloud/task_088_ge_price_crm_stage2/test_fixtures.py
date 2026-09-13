"""Static fixture data for the production installation safety tests.

The source string is parsed and transformed by patcher; this module never
executes it. Dynamic handler fixtures live in the separate local test package.
"""

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
