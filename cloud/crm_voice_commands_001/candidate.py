"""Build the exact replacement cars_ui.py from the installed one (pure text, no I/O).

1. Voice corrections name the gearbox «gearbox» (the CRM field); «transmission» matched no field,
   so «измени коробку …» on a filled gearbox answered «Не распознал поле CRM».
2. Saving a delivery stage moves from the stage button handler into save_stage(), used by the
   buttons and by voice; the button behaviour and texts stay the same.
3. A voice note that names where the car is («Автомобиль находится в Киеве») saves the stage
   through voice_stage before the field parser runs.
"""
MARKER = 'CRM-VOICE-STAGE-001'

GEARBOX_OLD = '        "transmission": r"кпп|коробк|трансмис|transmission|automatic|manual|автомат|механик",\n'
GEARBOX_NEW = ('        "gearbox": r"кпп|коробк|трансмис|transmission|automatic|manual|автомат|механик",'
               '  # %s: CRM field\n' % MARKER)

SAVE_ANCHOR = '# UA-CARDS-STAGE-ANCHOR-001-V1.1 · stage changes never force price/ETA prompts.\n'
SAVE_STAGE = '''# %s: one place saves a delivery stage (stage buttons and voice).
async def save_stage(cid, code, actor_id):
    """Save the stage; return (card, error text or None, site sync note)."""
    card_before = card_of(cid)
    if not card_before:
        return None, "Карточка не найдена.", None
    set_field(cid, "status", code, actor_id)
    if code == "ge_waiting" and not card_before.get("ge_arrived"):
        set_field(cid, "ge_arrived", _date.today().isoformat(), actor_id)
    card = card_of(cid)
    if card.get("status") != code:
        return card, "Не удалось сохранить этап. Сейчас в карточке: %%s" %% S.status_label(card.get("status")), None
    return card, None, await _ua004_sync_current_stage(card)


''' % MARKER

STAGE_SET_OLD = '''    code = storage_status(requested)
    card_before = card_of(cid)
    if not card_before:
        await q.message.reply_text("Карточка не найдена.")
        raise ApplicationHandlerStop
    set_field(cid, "status", code, q.from_user.id)

    if code == "ge_waiting" and not card_before.get("ge_arrived"):
        set_field(cid, "ge_arrived", _date.today().isoformat(), q.from_user.id)
    card = card_of(cid)
    saved = card.get("status")
    if saved != code:
        await q.message.reply_text(
            "Не удалось сохранить этап. Сейчас в карточке: %s"
            % S.status_label(saved),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                "← Вернуться к карточке", callback_data="car_open:%d" % cid)]]))
        raise ApplicationHandlerStop

    _ua004_sync_note = await _ua004_sync_current_stage(card)
'''
STAGE_SET_NEW = '''    card, error, _ua004_sync_note = await save_stage(cid, storage_status(requested), q.from_user.id)
    if error:
        rows = [[InlineKeyboardButton("← Вернуться к карточке", callback_data="car_open:%d" % cid)]] if card else None
        await q.message.reply_text(error, reply_markup=InlineKeyboardMarkup(rows) if rows else None)
        raise ApplicationHandlerStop
    saved = card.get("status")
'''

VOICE_OLD = '        if card and voice_object:\n'
VOICE_NEW = VOICE_OLD + '''            import voice_stage  # %s: «автомобиль в Киеве» -> delivery stage
            if await voice_stage.apply(thinking, card, input_text, user_id, save_stage, S.status_label):
                raise ApplicationHandlerStop
''' % MARKER

EDITS = ((GEARBOX_OLD, GEARBOX_NEW), (SAVE_ANCHOR, SAVE_STAGE + SAVE_ANCHOR),
         (STAGE_SET_OLD, STAGE_SET_NEW), (VOICE_OLD, VOICE_NEW))


class CandidateError(RuntimeError):
    pass


def cars_ui(source):
    if MARKER in source:
        raise CandidateError('ALREADY_APPLIED')
    for number, (old, new) in enumerate(EDITS):
        if source.count(old) != 1:
            raise CandidateError('ANCHOR:%d' % number)
        source = source.replace(old, new, 1)
    return source
