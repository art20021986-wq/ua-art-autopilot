"""Build the exact replacement sources from the installed ones (pure text, no I/O).

local_ocr.py: the full-page pass reads a phone screenshot as one column (--psm 4) and every
pass may use the whole remaining photo budget instead of 1.45 s (on the server a pass takes
0.3-5.7 s, so most passes were cut off and the VIN was never read).
team_bot.py: the photo branch of run_ai_draft hands over to photo_card.handle.
"""
MARKER = 'CRM-PHOTO-AUTOFILL-001'

OCR_EDITS = (
    ('            timeout=max(0.25, min(1.45, remaining)),\n',
     '            timeout=max(0.25, remaining),  # %s: whole remaining budget\n' % MARKER),
    ('    first = _ocr_one(full, binary, languages, deadline, 11)\n',
     '    first = _ocr_one(full, binary, languages, deadline, 4)  # %s: one column\n' % MARKER),
)

TEAM_OLD = '''        thinking = await msg.reply_text("🖼 ИИ распознаёт, до 15 секунд...")
        try:
            remaining = max(0.1, hard_deadline - time.monotonic())
            image = await asyncio.wait_for(download_bytes(file_id), timeout=remaining)
            remaining = max(0.5, hard_deadline - time.monotonic())
            image_data = await asyncio.wait_for(
                asyncio.to_thread(local_ocr.fields_from_image, image, allowed, remaining),
                timeout=remaining,
            )
            data.update(image_data)
            # A caption is explicit owner input and wins over an OCR ambiguity.
            if (text or "").strip():
                data.update(local_ocr.fields_from_text(text, allowed))
                data.update(fast.fast_text_data(text, ai_filter))
        except asyncio.TimeoutError:
            data = {}
            logging.warning("Local OCR hard timeout inbox=%s", inbox_id)
        except Exception as exc:
            data = {}
            logging.error("Local OCR failed inbox=%s error=%s", inbox_id, exc)
'''
TEAM_NEW = '''        import photo_card  # %s: photo -> new card by VIN
        await photo_card.handle(update, context, inbox_id, file_id, text)
        return
''' % MARKER


class CandidateError(RuntimeError):
    pass


def _apply(source, edits, name):
    if MARKER in source:
        raise CandidateError('ALREADY_APPLIED:' + name)
    for number, (old, new) in enumerate(edits):
        if source.count(old) != 1:
            raise CandidateError('ANCHOR:%s.%d' % (name, number))
        source = source.replace(old, new, 1)
    return source


def local_ocr(source):
    return _apply(source, OCR_EDITS, 'local_ocr')


def team_bot(source):
    return _apply(source, ((TEAM_OLD, TEAM_NEW),), 'team_bot')
