"""Pure source-pinned fence for legacy whole-catalog publication.

Does not read or write production. The caller installs the resulting source
only with the rest of the reviewed price-sync bundle and existing Gate B.
"""
import ast
import hashlib
import textwrap


SOURCE_SHA256 = "3d80712290e0881ebe7583231b532de422f808e6f18b5f6a90566d9e1eed3e0d"


HELPER = '''# TASK088_PRICE_PUBLICATION_FENCE_V1
@contextlib.contextmanager
def _task088_price_quiescence():
    """Hold the CRM write fence through legacy rendering, writes and rollback.

    The enclosing caller already holds _exclusive_lock(). A price worker uses
    that shared lock directly and does not enter this legacy full-render path.
    No schema installation, price mutation, claim release or retry occurs here.
    """
    import uaart_price_sync_outbox as _task088_outbox
    if DB.is_symlink() or not DB.is_file():
        raise PublishError("TASK088_CRM_DATABASE_FILE_REQUIRED")
    connection = None
    try:
        # mode=rw refuses to silently create a replacement CRM database.
        # Fail immediately when another CRM writer owns the DB; never wait or
        # retry an uncertain publication. RESERVED permits the legacy reader
        # connections while preventing new price commits until this exit.
        connection = sqlite3.connect(DB.as_uri() + "?mode=rw", uri=True,
                                     timeout=0, isolation_level=None)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("PRAGMA query_only=ON")
        schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (_task088_outbox.TABLE,)).fetchone()
        if schema is None or schema[0] != _task088_outbox._DDL:
            raise PublishError("TASK088_PRICE_OUTBOX_SCHEMA_REQUIRED")
        table = _task088_outbox.TABLE
        unresolved = connection.execute(
            "SELECT 1 FROM " + table + " AS event "
            "WHERE state IN ('PENDING','CLAIMED','STOPPED') OR "
            "(state IN ('RECONCILED','SUPERSEDED') AND revision=("
            "SELECT MAX(newer.revision) FROM " + table + " AS newer "
            "WHERE newer.car_id=event.car_id)) LIMIT 1").fetchone()
        if unresolved is not None:
            raise PublishError("TASK088_UNVERIFIED_PRICE_INTENTS_BLOCK_FULL_PUBLICATION")
        # Also reject an untracked price writer that changed CRM after the
        # last verified price event. A green historical receipt is not proof
        # of the current row. Cars without any price event retain the normal
        # manual first-publication route.
        latest = connection.execute(
            "SELECT event.state,event.ukraine_usd,event.georgia_usd,"
            "cars.id,cars.price_uah,cars.price_georgia FROM " + table + " AS event "
            "LEFT JOIN cars ON cars.id=event.car_id WHERE event.revision=("
            "SELECT MAX(newer.revision) FROM " + table + " AS newer "
            "WHERE newer.car_id=event.car_id)").fetchall()
        for state, expected_ua, expected_ge, car_id, actual_ua, actual_ge in latest:
            if car_id is None or state != "PUBLISHED":
                raise PublishError("TASK088_VERIFIED_CURRENT_PRICE_EVENT_REQUIRED")
            if (type(actual_ua) is not int or not 0 <= actual_ua < 2**63
                    or (actual_ge is not None and
                        (type(actual_ge) is not int or not 0 <= actual_ge < 2**63))):
                raise PublishError("TASK088_CURRENT_CRM_PRICE_FORMAT_INVALID")
            ua = "%d.00" % actual_ua
            ge = None if actual_ge is None else "%d.00" % actual_ge
            if (ua, ge) != (expected_ua, expected_ge):
                raise PublishError("TASK088_UNTRACKED_CRM_PRICE_CHANGE")
        yield
    except sqlite3.Error as exc:
        raise PublishError("TASK088_CRM_PUBLICATION_FENCE_UNAVAILABLE") from exc
    finally:
        if connection is not None:
            try:
                if connection.in_transaction:
                    connection.rollback()
            finally:
                connection.close()


'''


def _function(source, name, transform):
    nodes = [node for node in ast.parse(source).body
             if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(nodes) != 1:
        raise ValueError("EXACT_FUNCTION_REQUIRED:" + name)
    node = nodes[0]
    lines = source.splitlines(keepends=True)
    original = "".join(lines[node.lineno - 1:node.end_lineno])
    changed = transform(original)
    return "".join(lines[:node.lineno - 1]) + changed + "".join(lines[node.end_lineno:])


def _fence_body(source):
    function = ast.parse(source).body[0]
    lines = source.splitlines(keepends=True)
    first = function.body[0].lineno - 1
    return ("".join(lines[:first]) + "    with _task088_price_quiescence():\n"
            + textwrap.indent("".join(lines[first:]), "    "))


def _fence_catalog(source):
    anchor = "    with _exclusive_lock():"
    if source.count(anchor) != 1:
        raise ValueError("CATALOG_SHARED_LOCK_ANCHOR_REQUIRED")
    return source.replace(anchor, "    with _exclusive_lock(), _task088_price_quiescence():", 1)


def patch_source(source):
    if type(source) is not str or hashlib.sha256(source.encode("utf-8")).hexdigest() != SOURCE_SHA256:
        raise ValueError("CURRENT_PUBLISH_TRANSACTION_GUARD_SOURCE_SHA256_MISMATCH")
    result = _function(source, "_publish_locked", _fence_body)
    result = _function(result, "rebuild_catalog", _fence_catalog)
    anchor = "def _publish_locked("
    if result.count(anchor) != 1:
        raise ValueError("PUBLISH_LOCKED_ANCHOR_REQUIRED")
    result = result.replace(anchor, HELPER + anchor, 1)
    compile(result, "<candidate-publish-transaction-guard>", "exec")
    return result
