# Patch notes for /home/Carix/local_ocr.py (TASK 061)

Claude/Cloud does not have direct access to production and did not read or
modify the live `/home/Carix/local_ocr.py`. Per repository rules, this cloud/
deliverable contains the exact, minimal, additive patch instructions that the
owner-approved PythonAnywhere installer must apply. No production file was
touched by this task.

## Required additive change

Add one new function to `local_ocr.py` (do not remove or rename any existing
function; this is purely additive so existing callers keep working):

```python
from ai_card_recognition import recognize as _ai_card_recognize

def recognize_card_fields(ocr_text, allowed_keys=None):
    """
    Wrapper used by team_bot.py to turn raw OCR/caption/transcription text
    into a filtered dict of CRM field candidates using deterministic,
    zero-token local parsing (TASK 061 CRM-AI-CARD-001).
    """
    return _ai_card_recognize(ocr_text or "", allowed_keys)
```

`ai_card_recognition.py` (delivered in this task as
`cloud/task_061/ai_card_recognition.py`) must be copied unmodified to
`/home/Carix/ai_card_recognition.py` alongside `local_ocr.py`.

## Backup / rollback requirement for the installer

1. `cp /home/Carix/local_ocr.py /home/Carix/local_ocr.py.bak_task061`
2. Apply the additive function above at end of file.
3. Copy `ai_card_recognition.py` into `/home/Carix/`.
4. Run `python3 -m py_compile /home/Carix/local_ocr.py /home/Carix/ai_card_recognition.py`.
5. If compile fails, restore: `cp /home/Carix/local_ocr.py.bak_task061 /home/Carix/local_ocr.py` and abort.
6. Only after a clean compile, proceed to the team_bot.py patch.
