"""Storage-independent errors and persisted enquiry views."""
import json


class NotFound(LookupError):
    pass


class StorageUnavailable(RuntimeError):
    """An operation did not produce a confirmed durable result."""


def receipt(row):
    return {'request_id': row['request_id'], 'number': f'OR-{row["id"]:06d}',
            'status': 'saved'}


def detail(row):
    return dict(id=row['id'], number=f'OR-{row["id"]:06d}', created_at=row['created_at'],
                channel=row['channel'], data=json.loads(row['payload']),
                telegram_user_id=row['owner'].split(':', 1)[1]
                if row['owner'].startswith('telegram:') else None)
