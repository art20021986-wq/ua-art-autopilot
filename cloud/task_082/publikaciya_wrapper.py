"""UA ART Autopilot — TASK 082 bounded wrapper around publikaciya.opublikovat.

This wrapper does not modify the original publication function. It only
adds a post-success hook that triggers a full catalog rebuild through
catalog_guard.rebuild_all(), and guarantees that a guard failure never
corrupts the previously valid catalog (fail-closed: keep old catalog on
any rebuild error).

This module performs NO direct filesystem writes to production catalog
paths. It returns rebuild results; the bounded installer described in
install_procedure.md is responsible for the atomic backup/verify/rollback
file transaction and for the start_safe.py restart.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from . import catalog_guard


class PublicationGuardError(Exception):
    pass


def wrap_opublikovat(
    original_opublikovat: Callable[..., Any],
    *,
    load_all_crm_cars: Callable[[], List["catalog_guard.CrmCarRecord"]],
    load_all_published_pages: Callable[[], Dict[str, "catalog_guard.PublishedPageInfo"]],
    apply_catalog_transaction: Callable[[str], bool],
) -> Callable[..., Any]:
    """Return a bounded wrapper function for `publikaciya.opublikovat`.

    Parameters
    ----------
    original_opublikovat:
        The existing, unmodified publish function. Called first, unchanged.
    load_all_crm_cars:
        Callable returning a fresh live snapshot of CRM car records
        (status, vin, ua_code, title_base, description_snippet) at call
        time — must be a fresh read, not cached, per fail-closed audit
        requirement.
    load_all_published_pages:
        Callable returning a fresh mapping ua_code -> PublishedPageInfo,
        reflecting the CURRENT state of already-published individual pages
        and media sync, at call time.
    apply_catalog_transaction:
        Callable that receives the fully assembled catalog HTML string and
        performs the atomic backup + write + verify + rollback transaction
        for BOTH catalog files as a single unit, returning True on success
        and False (with internal rollback already performed) on failure.
        This callable is where the actual production write happens, and it
        must live in the bounded installer executed on PythonAnywhere/by
        the controller — never inside this wrapper directly.

    Returns
    -------
    A callable with the same signature contract as `original_opublikovat`,
    plus the guarded catalog rebuild side effect after success.
    """

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        result = original_opublikovat(*args, **kwargs)

        # Only trigger the catalog rebuild if the original publish call
        # succeeded. We treat any exception from original_opublikovat as
        # already propagated (it raises before reaching here); a falsy
        # return value is treated conservatively as "do not touch catalog".
        if result is False:
            return result

        try:
            cars = load_all_crm_cars()
            pages = load_all_published_pages()
            rebuild = catalog_guard.rebuild_all(cars, pages)
            cards = rebuild["cards"]
            html = catalog_guard.assemble_catalog_html(cards)
            ok = apply_catalog_transaction(html)
            if not ok:
                # apply_catalog_transaction is required to have already
                # rolled back both files to their preimage on failure.
                raise PublicationGuardError(
                    "Catalog transaction failed; both files restored to preimage"
                )
        except Exception as exc:  # noqa: BLE001 - deliberate fail-closed catch
            # Individual page publication already succeeded and is out of
            # this wrapper's bounded scope to roll back. The catalog itself
            # remains at its last valid state because apply_catalog_transaction
            # guarantees rollback on failure, and we never write partial
            # catalog content here.
            # The exception is swallowed here only after the transaction
            # callable's own rollback guarantee; re-raise so callers/logging
            # upstream are aware.
            raise PublicationGuardError(str(exc)) from exc

        return result

    return wrapped
