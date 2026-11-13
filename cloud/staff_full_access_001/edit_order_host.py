"""ua_order/host.py: the customer registration passes on the owners function instead of one owner chat."""
NAME = 'ua_order/host.py'
EDITS = (
    ('def register_customer(app, *, owner_id):\n',
     'def register_customer(app, *, owners):\n'),
    ('    bindings.owner_inbox(app, loaded, owner_id=owner_id)\n',
     '    bindings.owner_inbox(app, loaded, owners=owners)\n'),
)
