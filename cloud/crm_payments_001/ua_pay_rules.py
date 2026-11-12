"""Payment schedule rules of the sale contract (CRM-PAYMENTS-001, owner 2026-11-12; contract cloud/sale_contract_002).

Pure functions, no I/O. Four payments (contract p. 3.2):
  1 — service 600 $ + prepayment 1 000 $: no deadline (work starts after it);
  2 — car price minus the prepayment: 7 working days from the auction data;
  3 — logistics: 10 working days from the invoice, but not later than the day before the ferry;
  4 — customs: 5 working days from the invoice.
Late payment (p. 6.2), on the unpaid part, from the day after the due date:
  penalty = 2 × NBU discount rate per year; 36 % per year; a one-time 5 % fine once more than 5 working days late.
Inflation losses are counted only for a claim (the index is monthly) and are not shown here.
Notice the next working day after the due date, extra term 5 working days (p. 6.3) — then the contract may be
treated as terminated (p. 6.5). Working days: Monday–Saturday except public holidays (ua_lead_calendar).
"""
import datetime

import ua_lead_calendar as cal

SERVICE_USD, PREPAY_USD, LOGISTICS_USD = 600, 1000, 3450
KINDS = (1, 2, 3, 4)
TITLES = {1: 'Услуга 600 $ + передоплата 1 000 $', 2: 'Цена авто минус передоплата', 3: 'Логистика',
          4: 'Таможенные платежи'}
DAYS = {2: 7, 3: 10, 4: 5}  # working days to pay; payment 1 has no deadline
FINE_AFTER = 5  # working days late before the one-time fine
FINE_RATE = 0.05
ANNUAL_RATE = 0.36
EXTRA_DAYS = 5  # working days of the extra term after the notice


def add_working_days(day, count):
    """The date `count` working days after `day` (the day itself not counted)."""
    left = count
    while left:
        day += datetime.timedelta(days=1)
        left -= cal.is_working_day(day)
    return day


def working_days_between(first, last):
    """Working days after `first` up to and including `last` (0 when last <= first)."""
    days, day = 0, first
    while day < last:
        day += datetime.timedelta(days=1)
        days += cal.is_working_day(day)
    return days


def due_date(kind, start, ferry=None):
    """Last day to pay (inclusive) for a payment issued on `start`; None for payment 1."""
    if kind == 1:
        return None
    due = add_working_days(start, DAYS[kind])
    if kind == 3 and ferry is not None:
        due = min(due, ferry - datetime.timedelta(days=1))
    return due


def extra_deadline(due):
    """End of the extra term: the notice goes the next working day, then 5 working days (p. 6.3)."""
    return add_working_days(add_working_days(due, 1), EXTRA_DAYS)


def sanctions(debt, due, today, nbu_rate):
    """Sums for an unpaid `debt` (USD) due on `due`, as of `today`; nbu_rate is a fraction (0.155 for 15.5 %)."""
    if due is None or debt <= 0 or today <= due:
        return {'days': 0, 'work_days': 0, 'penalty': 0.0, 'annual': 0.0, 'fine': 0.0, 'total': 0.0}
    days = (today - due).days
    work_days = working_days_between(due, today)
    penalty = debt * 2 * nbu_rate / 365 * days
    annual = debt * ANNUAL_RATE / 365 * days
    fine = debt * FINE_RATE if work_days > FINE_AFTER else 0.0
    return {'days': days, 'work_days': work_days, 'penalty': round(penalty, 2), 'annual': round(annual, 2),
            'fine': round(fine, 2), 'total': round(penalty + annual + fine, 2)}


def state(payment, today):
    """'paid', 'none' (not issued yet), 'open' (not due), 'late' (past due), 'final' (extra term over)."""
    if payment is None or payment.get('amount') is None:
        return 'none'
    if payment['paid'] >= payment['amount']:
        return 'paid'
    due = payment.get('due')
    if due is None or today <= due:
        return 'open'
    return 'final' if today > extra_deadline(due) else 'late'
