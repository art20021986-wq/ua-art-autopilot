"""A client's bought cars for «Мій кабінет» (owner 2026-11-12).

The one place that links the client's page to the contract accounting (session «Договор купли-продажи», by the
client's phone). Until that accounting is installed there are no records, so the page shows «Поки немає».
Each car: {'title', 'year', 'vin', 'lot_id', 'stage'} — only what the client may see.
"""


def purchased(phone):
    """The client's bought cars, newest first; [] while the contract accounting is not installed."""
    return []
