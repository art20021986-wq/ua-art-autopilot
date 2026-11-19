"""KOREA-SYNC-001 (owner 2026-11-18: the tile, the ticker and the Korea page always agree): what the site shows as of a
Korea day.

Pure functions, no network: the published lot list (lots.json), the order page carousels (model-lots.json) and the
ticker cars keep only the auction days from `today` on, and a ticker car only when the lot list has it (so each ticker
card opens its lot). The job runs them after the Korea midnight, so «Сьогодні», «Завтра» and the next days stay right
between the morning runs and on Sunday.
"""
from .selection import auction_date, day_after


def current_lots(value, today):
    """lots.json without the lots of days before `today` ('YYYY/MM/DD', Korea)."""
    return dict(value, lots=[lot for lot in value.get('lots', []) if auction_date(lot) >= today])


def current_models(value, today):
    """model-lots.json without the lots of days before `today`; a model left without lots is dropped."""
    models = {}
    for key, lots in value.get('models', {}).items():
        kept = [lot for lot in lots if lot.get('start', '')[:10] >= today]
        if kept:
            models[key] = kept
    return dict(value, models=models)


def listed_items(items, lot_ids, today):
    """The ticker cars the lot list has, from `today` on, each marked «Завтра» when its day is the day after `today`."""
    tomorrow = day_after(today)
    return [dict(item, tomorrow=item['auction_start_jst'][:10] == tomorrow) for item in items
            if item['id'] in lot_ids and item['auction_start_jst'][:10] >= today]
