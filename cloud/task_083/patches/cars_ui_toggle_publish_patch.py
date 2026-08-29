"""
Patched cars_ui.py -> toggle_publish (relevant section only)

Change summary:
  - Inspects the structured result from publish_car_transactional / the
    publisher instead of assuming success.
  - Never reports "Машина видна клиентам в каталоге." unless ok=True AND
    readback_ok=True AND http_immediate_ok=True.
  - On failure, reports one clear final message and leaves published state
    exactly as it was before the attempt (publisher already guarantees
    preimage restore; this UI layer must not additionally flip CRM flags on
    a failed attempt).
"""


def toggle_publish(car_row, publish_fn):
    """
    publish_fn: callable() -> dict result from publish_car_transactional
                (already wired with all required paths/builders)

    Returns a single user-facing message string. Never mutates CRM
    published/status fields here; the CRM row is only updated elsewhere
    after this function confirms real success.
    """
    result = publish_fn()

    if not result.get("ok"):
        reason = result.get("reason", "unknown_error")
        return (
            "Публикация НЕ выполнена — изменения отменены, "
            "CRM и сайт синхронизированы. Причина: %s" % reason
        )

    if not result.get("readback_ok") or not result.get("http_immediate_ok"):
        return (
            "Публикация НЕ подтверждена (проверка чтения/HTTP не пройдена) — "
            "изменения отменены, CRM и сайт синхронизированы."
        )

    return "Машина видна клиентам в каталоге."
