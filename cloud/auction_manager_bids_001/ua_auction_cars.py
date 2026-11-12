"""A client's bought cars for «Мій кабінет» (owner 2026-11-12).

The one place that links the client's page to the contract accounting (session «Договор купли-продажи» /
CRM-PAYMENTS, by the client's phone). Until that accounting is installed there are no records, so the page shows
«Поки немає». Each car, as that accounting gives it (owner 2026-11-12: amounts, deadlines and penalties are shown):
{'title', 'year', 'vin', 'lot_id', 'stage_label', 'price_usd',
 'payments': [{'kind', 'amount_usd', 'paid_usd', 'due_date', 'days_left', 'penalty_usd'}],
 'penalty': {'daily_percent', 'annual_percent', 'fine_percent', 'fine_after_working_days', 'clause'}}
(days_left in working days; the CRM-PAYMENTS module gives ua_pay_store.purchased_cars(phone) after its install).
"""


def purchased(phone):
    """The client's bought cars, newest first; [] while the contract accounting is not installed."""
    return []
