"""The CRM staff role change of STAFF-FULL-ACCESS-001 (owner 2026-11-24): the manager becomes «👑 Владелец».

The same two writes as the CRM's own db.set_staff_role: one staff row's role and one audit row. Runs on the
connection the installer already holds under the writer locks, so nothing else writes meanwhile. The target is the
one active staff member with the given username and role; anything else stops the install. No id leaves the server.
"""
import hashlib

USERNAME = 'beetle204'
FROM, TO = 'admin', 'owner'
ACTION = 'staff_role'
# Rows checked one by one in verify(); the audit id counter moves with its one new row.
SKIP = ('INSERT INTO "staff" ', 'INSERT INTO "audit" ', 'INSERT INTO "sqlite_sequence" VALUES(\'audit\',')


class RoleError(RuntimeError):
    pass


def _one(connection, sql, args):
    rows = connection.execute(sql, args).fetchall()
    if len(rows) != 1:
        raise RoleError('ROLE_TARGET_COUNT:%d' % len(rows))
    return rows[0][0]


def target(connection, role=FROM):
    """The user id of the one active staff member @USERNAME with `role`."""
    return _one(connection, "SELECT user_id FROM staff WHERE active=1 AND role=? "
                            "AND lower(ltrim(coalesce(username,''),'@'))=?", (role, USERNAME))


def owner(connection):
    """The one active owner before the change: the actor of the audit row, as in the CRM bot."""
    return _one(connection, "SELECT user_id FROM staff WHERE active=1 AND role=?", (TO,))


def _set(connection, user_id, old, new, actor, stamp):
    if connection.execute('UPDATE staff SET role=? WHERE user_id=? AND role=? AND active=1',
                          (new, user_id, old)).rowcount != 1:
        raise RoleError('ROLE_UPDATE')
    connection.execute('INSERT INTO audit (actor_id, action, entity_type, entity_id, field, old_value, new_value, '
                       'created_at) VALUES (?,?,?,?,?,?,?,?)', (actor, ACTION, 'staff', user_id, 'role', old, new, stamp))


def promote(connection, stamp):
    """FROM → TO for the target; returns the user id (kept on the server only)."""
    actor, user_id = owner(connection), target(connection)
    _set(connection, user_id, FROM, TO, actor, stamp)
    return user_id, actor


def demote(connection, user_id, actor, stamp):
    """Rollback: TO → FROM for the same person, logged the same way."""
    _set(connection, user_id, TO, FROM, actor, stamp)


def snapshot(connection):
    """Everything in the CRM except staff and audit (one digest), plus those two tables in full."""
    rest = hashlib.sha256()
    for line in connection.iterdump():  # the same logical dump the installer already compares
        if line.startswith(SKIP):
            continue
        rest.update(line.encode() + b'\n')
    staff = {r[0]: r for r in connection.execute('SELECT * FROM staff')}
    audit = connection.execute('SELECT * FROM audit ORDER BY id').fetchall()
    return {'rest': rest.hexdigest(), 'staff': staff, 'audit': audit}


def verify(before, after, user_id, old, new):
    """Only the one role changed and exactly one audit row of that change was added."""
    if after['rest'] != before['rest']:
        raise RoleError('CRM_OTHER_DATA_CHANGED')
    if set(after['staff']) != set(before['staff']):
        raise RoleError('STAFF_ROWS_CHANGED')
    if any(after['staff'][key] != row for key, row in before['staff'].items() if key != user_id):
        raise RoleError('STAFF_OTHER_ROW_CHANGED')
    changed = [i for i, (a, b) in enumerate(zip(before['staff'][user_id], after['staff'][user_id])) if a != b]
    if len(changed) != 1 or before['staff'][user_id][changed[0]] != old or after['staff'][user_id][changed[0]] != new:
        raise RoleError('STAFF_ROLE_NOT_EXACT')
    added = after['audit'][len(before['audit']):]
    if after['audit'][:len(before['audit'])] != before['audit'] or len(added) != 1:
        raise RoleError('AUDIT_NOT_ONE_ROW')
    row = added[0]
    if (row[2], row[3], row[4], row[5], row[6], row[7]) != (ACTION, 'staff', user_id, 'role', old, new):
        raise RoleError('AUDIT_ROW')
