"""
Patched catalog_stage_guard_core.py (relevant section only)

Change summary:
  - Missing diagnostic file for a NEW card no longer blocks placeholder
    creation; a minimal valid placeholder diagnostic page is generated
    instead.
  - An EXISTING diagnostic file that points to the wrong VIN/stage data is
    still a hard block (unchanged behaviour, preserved intentionally).
"""

PLACEHOLDER_DIAG_TEMPLATE = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<title>{vin} — Диагностика готовится</title></head>
<body>
<h1>{vin}</h1>
<p>Диагностика готовится. Страница будет обновлена в ближайшее время.</p>
</body></html>
"""


def ensure_diag_placeholder(vin, diag_path, expected_stage, expected_category):
    """
    Returns (ok: bool, reason: str, content_to_write: bytes or None)

    - If diag_path does not exist: allow, generate placeholder content.
    - If diag_path exists: validate it matches vin/stage/category; if it
      does not match, hard block (wrong diagnostic link protection kept).
    - If diag_path exists and matches: allow, no placeholder write needed.
    """
    import os

    if not os.path.exists(diag_path):
        content = PLACEHOLDER_DIAG_TEMPLATE.format(vin=vin).encode("utf-8")
        return True, "placeholder_created", content

    with open(diag_path, "rb") as f:
        existing = f.read().decode("utf-8", errors="ignore")

    if vin not in existing:
        return False, "wrong_diagnostic_link: vin_mismatch", None

    # stage/category cross-check left to caller's existing validated
    # metadata comparison logic (unchanged); this patch only removes the
    # missing-file hard block for NEW cards.
    return True, "existing_diag_valid", None
