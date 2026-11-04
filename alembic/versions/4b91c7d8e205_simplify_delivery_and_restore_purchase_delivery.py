"""Restore purchase delivery and replace raw CDEK payloads with operation states."""
import hashlib
import json
import os

from alembic import op
import sqlalchemy as sa

revision = '4b91c7d8e205'
down_revision = '2e8c6a4d9b10'
branch_labels = None
depends_on = None

FIELDS = ('registration', 'editing', 'cancellation', 'pickup', 'waybill', 'barcode')


def compact(value):
  value = value or {}
  data = value.get('result', value)
  errors = list(data.get('errors') or [])
  requests = data.get('requests') or []
  for request in requests:
    errors.extend(request.get('errors') or [])
  latest = max(requests, key=lambda r: r.get('date_time', ''), default={})
  state = latest.get('state', value.get('state', 'accepted'))
  result = {'state': 'rejected' if errors else {'INVALID': 'rejected', 'SUCCESSFUL': 'success',
    'ACCEPTED': 'accepted'}.get(state, state.lower()),
    'errors': [{'code': str(e.get('code', 'unknown'))[:100], 'message': str(e.get('message', ''))[:500]}
      for e in errors[:20] if isinstance(e, dict)]}
  uuid = value.get('uuid') or data.get('entity', {}).get('uuid')
  if uuid:
    result['uuid'] = uuid
  if latest.get('request_uuid'):
    result['request_uuid'] = latest['request_uuid']
  return result


def upgrade():
  connection = op.get_bind()
  with op.batch_alter_table('purchases') as batch:
    batch.add_column(sa.Column('delivery', sa.JSON(), nullable=True))
  with op.batch_alter_table('delivery_shipments') as batch:
    batch.add_column(sa.Column('details', sa.JSON(), nullable=True))
    batch.add_column(sa.Column('request_hash', sa.String(64), nullable=True))
    for field in FIELDS:
      batch.add_column(sa.Column(field, sa.JSON(), nullable=True))
  metadata = sa.MetaData()
  shipments = sa.Table('delivery_shipments', metadata, autoload_with=connection)
  purchases = sa.Table('purchases', metadata, autoload_with=connection)
  # Recover older selections if they were embedded in contact_info.
  if 'contact_info' in purchases.c:
    for purchase in connection.execute(sa.select(purchases.c.id, purchases.c.contact_info)).mappings():
      legacy = (purchase['contact_info'] or {}).get('delivery')
      if isinstance(legacy, dict) and legacy:
        selection = legacy if 'module' in legacy else {'module': legacy.get('provider', 'manual'), 'data': legacy}
        connection.execute(purchases.update().where(purchases.c.id == purchase['id']).values(delivery=selection))
  for row in connection.execute(sa.select(shipments)).mappings():
    body = row['request_payload'] or {}
    old = row['operations'] or {}
    package = (body.get('packages') or [{}])[0]
    details = {key: body[key] for key in ('tariff_code', 'recipient', 'delivery_point', 'to_location') if key in body}
    details['package'] = {key: package[key] for key in ('weight', 'length', 'width', 'height') if key in package}
    details['delivery_cost'] = str(body.get('delivery_recipient_cost', {}).get('value', 0))
    details['item_costs'] = {str(item['ware_key']): str(item['cost']) for item in package.get('items', [])
      if 'ware_key' in item and 'cost' in item}
    details.update(reviewed_and_packed=True, recipient_collection_confirmed=True)
    changes = {'details': details, 'request_hash': hashlib.sha256(json.dumps(
      {k: v for k, v in body.items() if k not in ('number', 'type', 'uuid')}, sort_keys=True).encode()).hexdigest(),
      'registration': compact(row['response_payload']) if row['response_payload'] else {'state': row['status'], 'errors': []},
      'editing': {}, 'cancellation': compact(old['cancel']) if old.get('cancel') else {},
      'pickup': compact(old['intake']) if old.get('intake') else {},
      'waybill': compact(old['waybill']) if old.get('waybill') else {},
      'barcode': compact(old['barcode']) if old.get('barcode') else {}}
    for key, value in old.items():
      if key.startswith('update:'):
        changes['editing'] = compact(value)
    if changes['registration']['state'] == 'rejected':
      changes['status'] = 'rejected'
    connection.execute(shipments.update().where(shipments.c.id == row['id']).values(**changes))
    connection.execute(purchases.update().where(purchases.c.id == row['purchase_id']).values(delivery={
      'module': row['provider'], 'data': {k: details[k] for k in ('tariff_code', 'recipient', 'delivery_point', 'to_location') if k in details}}))
  with op.batch_alter_table('delivery_shipments') as batch:
    for field in ('details', *FIELDS):
      batch.alter_column(field, existing_type=sa.JSON(), nullable=False)
    for field in ('environment', 'request_payload', 'response_payload', 'operations'):
      batch.drop_column(field)
  configs = sa.Table('integration_configs', sa.MetaData(), autoload_with=connection)
  for row in connection.execute(sa.select(configs.c.code, configs.c.config)).mappings():
    data = dict(row['config'] or {})
    data.pop('environment', None)
    connection.execute(configs.update().where(configs.c.code == row['code']).values(config=data))


def downgrade():
  # Raw provider responses cannot be reconstructed; restore the old shape only.
  connection = op.get_bind()
  with op.batch_alter_table('delivery_shipments') as batch:
    batch.add_column(sa.Column('environment', sa.String(16), nullable=True))
    for field in ('request_payload', 'response_payload', 'operations'):
      batch.add_column(sa.Column(field, sa.JSON(), nullable=True))
  table = sa.Table('delivery_shipments', sa.MetaData(), autoload_with=connection)
  for row in connection.execute(sa.select(table)).mappings():
    body = dict(row['details'])
    package = body.pop('package', {})
    package.update(number='1', items=[])
    body.update(number=row['external_number'], packages=[package])
    operations = {old: row[new] for old, new in [('cancel', 'cancellation'), ('intake', 'pickup'),
      ('waybill', 'waybill'), ('barcode', 'barcode'), ('update:restored', 'editing')] if row[new]}
    connection.execute(table.update().where(table.c.id == row['id']).values(
      environment='test' if os.getenv('STAGE') == 'DEV' else 'production',
      request_payload=body, response_payload={}, operations=operations))
  with op.batch_alter_table('delivery_shipments') as batch:
    batch.alter_column('environment', existing_type=sa.String(16), nullable=False)
    for field in ('request_payload', 'response_payload', 'operations'):
      batch.alter_column(field, existing_type=sa.JSON(), nullable=False)
    for field in ('details', 'request_hash', *FIELDS):
      batch.drop_column(field)
  with op.batch_alter_table('purchases') as batch:
    batch.drop_column('delivery')
