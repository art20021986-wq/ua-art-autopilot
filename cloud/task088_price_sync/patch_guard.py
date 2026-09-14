"""Pure source-pinned fence for legacy whole-catalog publication.

Does not read or write production. The caller installs the resulting source
only with the rest of the reviewed price-sync bundle and existing Gate B.
"""
import ast
import hashlib
import textwrap


SOURCE_SHA256 = "3d80712290e0881ebe7583231b532de422f808e6f18b5f6a90566d9e1eed3e0d"


HELPER = '''# TASK088_PRICE_PUBLICATION_FENCE_V5
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
        # FINAL v5 operator intents precede price mutation. The full generator
        # must never consume an accepted but unverified intermediate price.
        for name, ddl in ((_task088_outbox.V5_TABLE, _task088_outbox._V5_DDL),
                          (_task088_outbox.V5_AUDIT, _task088_outbox._V5_AUDIT_DDL)):
            schema = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
            if schema is None or schema[0] != ddl:
                raise PublishError("TASK088_V5_PRICE_SCHEMA_REQUIRED")
        for name, ddl in _task088_outbox._V5_TRIGGERS:
            trigger = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (name,)).fetchone()
            if trigger is None or trigger[0] != ddl:
                raise PublishError("TASK088_V5_PRICE_PROTECTION_TRIGGER_REQUIRED")
        pending = connection.execute(
            "SELECT 1 FROM " + _task088_outbox.V5_TABLE + " WHERE state!='COMPLETED' LIMIT 1").fetchone()
        if pending is not None:
            raise PublishError("TASK088_V5_UNVERIFIED_PRICE_INTENTS_BLOCK_FULL_PUBLICATION")
        import hashlib as _task088_hashlib
        import json as _task088_json
        completed = connection.execute(
            "SELECT event.event_key FROM " + _task088_outbox.V5_TABLE + " AS event "
            "WHERE event.sequence=(SELECT MAX(newer.sequence) FROM " + _task088_outbox.V5_TABLE +
            " AS newer WHERE newer.car_id=event.car_id)").fetchall()
        v5_car_ids = set()
        for (event_key,) in completed:
            event = _task088_outbox.get_operation(connection, event_key)
            v5_car_ids.add(event["car_id"])
            cursor = connection.execute("SELECT * FROM cars WHERE id=?", (event["car_id"],))
            raw_row = cursor.fetchone()
            row = dict(zip((item[0] for item in cursor.description), raw_row)) if raw_row is not None else None
            if (row is None or row.get("auto_number") != event["car_code"]
                    or str(row.get("vin") or "") != event["vin"]):
                raise PublishError("TASK088_V5_VERIFIED_CAR_IDENTITY_REQUIRED")
            def _canonical_price(value, nullable=False):
                if value is None and nullable:
                    return None
                if type(value) is not int or not 0 <= value < 2**63:
                    raise PublishError("TASK088_CURRENT_CRM_PRICE_FORMAT_INVALID")
                return "%d.00" % value
            actual_pair = (_canonical_price(row.get("price_uah")),
                           _canonical_price(row.get("price_georgia"), True))
            expected_pair = (event["ukraine_usd"], event["georgia_usd"])
            if actual_pair != expected_pair:
                raise PublishError("TASK088_V5_UNTRACKED_CRM_PRICE_CHANGE")
            selected = 0 if event["field"] == "price_uah" else 1
            if event["value"] != expected_pair[selected]:
                raise PublishError("TASK088_V5_SELECTED_PRICE_SNAPSHOT_MISMATCH")
            stamps = [event[key] for key in ("created_ms", "db_committed_ms", "verified_ms", "completed_ms")]
            if any(type(value) is not int or value < 0 for value in stamps) or stamps != sorted(stamps):
                raise PublishError("TASK088_V5_COMPLETION_CHECKPOINTS_REQUIRED")
            try:
                after = _task088_json.loads(event["after_json"])
                if (after["id"] != event["car_id"] or after["auto_number"] != event["car_code"]
                        or str(after.get("vin") or "") != event["vin"]
                        or (_canonical_price(after["price_uah"]), _canonical_price(after["price_georgia"], True)) != expected_pair):
                    raise PublishError("TASK088_V5_COMMITTED_PRICE_SNAPSHOT_REQUIRED")
                records = {fact: _task088_json.loads(payload) for fact, payload in connection.execute(
                    "SELECT fact,payload_json FROM " + _task088_outbox.V5_AUDIT + " WHERE event_key=?", (event_key,))}
                required = {"ACCEPTED", "DB_COMMITTED", "DB_READBACK", "VERIFIED", "COMPLETED"}
                if not required <= records.keys():
                    raise PublishError("TASK088_V5_COMPLETION_AUDIT_REQUIRED")
                for fact in required:
                    item = records[fact]
                    if (item["operation_id"] != event_key or item["car_id"] != event["car_id"]
                            or item["actor_id"] != event["actor_id"] or item["chat_id"] != event["chat_id"]
                            or item["field"] != event["field"] or item["requested_value"] != event["value"]):
                        raise PublishError("TASK088_V5_COMPLETION_AUDIT_IDENTITY_MISMATCH")
                proof = records["VERIFIED"]["details"]
                encoded = _task088_json.dumps(proof, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()
                if (_task088_hashlib.sha256(encoded).hexdigest() != event["receipt_sha256"]
                        or proof["operation_id"] != event_key or proof["claim_nonce"] != event["claim_nonce"]
                        or proof["car_id"] != event["car_id"] or proof["car_code"] != event["car_code"]
                        or proof["vin"] != event["vin"] or proof["actor_id"] != event["actor_id"]
                        or proof["chat_id"] != event["chat_id"] or proof["market"] != event["field"]
                        or proof["new_value"] != event["value"] or (proof["ua"], proof["ge"]) != expected_pair
                        or proof["verified_ms"] != event["verified_ms"]
                        or any(proof[key] != "PASS" for key in ("db_readback", "protected_data", "verification"))
                        or records["DB_READBACK"]["details"]["separate_connection"] is not True
                        or records["COMPLETED"]["details"]["receipt_sha256"] != event["receipt_sha256"]):
                    raise PublishError("TASK088_V5_COMPLETION_PROOF_MISMATCH")
            except (KeyError, TypeError, ValueError) as exc:
                raise PublishError("TASK088_V5_COMPLETION_PROOF_INVALID") from exc
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
            # A completed v5 operation supersedes the old published snapshot,
            # while unresolved v1 work above remains fail-closed.
            if car_id in v5_car_ids:
                continue
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
