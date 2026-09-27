"""Atomic draft creation and fill through the existing CRM connection queue."""
from crm_explicit_fields import LABELS, normalize_vin


def record_source(db, actor, source):
    """Persist the incoming item before acknowledging/scheduling OCR."""
    with db.connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute('SELECT id FROM inbox WHERE tg_chat_id=? AND tg_message_id=? ORDER BY id LIMIT 1',
                                 (source['chat_id'], source['message_id'])).fetchone()
        if row:
            return row[0]
        return connection.execute(
            'INSERT INTO inbox (from_user_id,kind,text,file_id,media_group,tg_chat_id,tg_message_id,status,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
            (actor, source['kind'], source.get('text'), source.get('file_id'), source.get('media_group'),
             source['chat_id'], source['message_id'], db.ST_NEW, db.now())).lastrowid


def save(db, schema, data, actor, source, current_id=None):
    """One transaction for inbox, VIN lookup, draft fields and audit.

    Existing published/archived cars are opened unchanged. Existing non-empty
    values are never overwritten. Telegram message identity makes replay inert.
    """
    facts = {k: v for k, v in data.items() if k in LABELS and v is not None}
    vin = normalize_vin(facts.get('vin'))
    if facts.get('vin') and not vin:
        raise ValueError('INVALID_VIN')
    if vin:
        facts['vin'] = vin
    with db.connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        prior = connection.execute(
            'SELECT card_id FROM inbox WHERE tg_chat_id=? AND tg_message_id=? AND card_type=? AND card_id IS NOT NULL ORDER BY id LIMIT 1',
            (source['chat_id'], source['message_id'], 'cars')).fetchone()
        if prior:
            card = connection.execute('SELECT * FROM cars WHERE id=?', (prior[0],)).fetchone()
            if not card:
                raise ValueError('REPLAY_CARD_REMOVED')
            return dict(card), {}, False
        card = None
        if vin:
            # Normalize all legacy representations without changing stored VINs.
            matches = [r for r in connection.execute('SELECT * FROM cars') if normalize_vin(r['vin']) == vin]
            if len(matches) > 1:
                raise ValueError('VIN_DUPLICATE_CONFLICT')
            card = dict(matches[0]) if matches else None
        elif current_id:
            row = connection.execute('SELECT * FROM cars WHERE id=?', (current_id,)).fetchone()
            card = dict(row) if row else None
        if not card and not vin:
            raise ValueError('VIN_REQUIRED')
        created = card is None
        now = db.now()
        changes = {}
        if created:
            values = dict(facts, auto_number=schema.next_auto_number(connection),
                          created_by=actor, created_at=now,
                          review_status=db.ST_APPROVED_OWNER, published=0)
            columns = list(values)
            cursor = connection.execute('INSERT INTO cars (' + ','.join(columns) + ') VALUES ('
                                        + ','.join('?' for _ in columns) + ')', list(values.values()))
            card_id = cursor.lastrowid
            changes = facts
        else:
            card_id = card['id']
            if (not card.get('published') and card.get('review_status') != db.ST_ARCHIVED
                    and card.get('status') not in {'archived', 'sold'}):
                changes = {k: v for k, v in facts.items() if k != 'vin' and card.get(k) in (None, '')}
                if changes:
                    connection.execute('UPDATE cars SET ' + ','.join(k+'=?' for k in changes)
                                       + ',updated_at=? WHERE id=?', [*changes.values(), now, card_id])
        # Keep the screenshot in the inbox, never in sale photos or descriptions.
        inbox = connection.execute('SELECT id FROM inbox WHERE tg_chat_id=? AND tg_message_id=? ORDER BY id LIMIT 1',
                                   (source['chat_id'], source['message_id'])).fetchone()
        if inbox:
            connection.execute('UPDATE inbox SET card_type=?,card_id=?,status=? WHERE id=?',
                               ('cars', card_id, db.ST_APPROVED_OWNER, inbox[0]))
        else:
            connection.execute(
                'INSERT INTO inbox (from_user_id,kind,text,file_id,media_group,tg_chat_id,tg_message_id,status,created_at,card_type,card_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                (actor, source['kind'], source.get('text'), source.get('file_id'), source.get('media_group'),
                 source['chat_id'], source['message_id'], db.ST_APPROVED_OWNER, now, 'cars', card_id))
        if created:
            connection.execute(
                'INSERT INTO audit (actor_id,action,entity_type,entity_id,field,old_value,new_value,created_at) VALUES (?,?,?,?,?,?,?,?)',
                (actor, 'explicit_intake_create', 'cars', card_id, 'auto_number', None, values['auto_number'], now))
        for field, value in changes.items():
            connection.execute(
                'INSERT INTO audit (actor_id,action,entity_type,entity_id,field,old_value,new_value,created_at) VALUES (?,?,?,?,?,?,?,?)',
                (actor, 'explicit_intake_fill', 'cars', card_id, field, None, str(value), now))
        result = dict(connection.execute('SELECT * FROM cars WHERE id=?', (card_id,)).fetchone())
    return result, changes, created
