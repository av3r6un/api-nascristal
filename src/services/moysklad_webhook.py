from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.sync import SyncTask
from src.models import Purchase, PurchaseSubmission
from src.schemas.moysklad_webhook import WebhookEvent


async def save_webhook_events(session: AsyncSession, events: list[WebhookEvent], request_id: UUID):
  dialect = session.get_bind().dialect.name
  if dialect not in ('sqlite', 'mysql'):
    raise RuntimeError(f'Unsupported database: {dialect}')
  insert = sqlite_insert if dialect == 'sqlite' else mysql_insert

  order_ids = {str(event.meta.entity_uuid) for event in events if event.meta.type == 'customerorder'}
  if order_ids:
    linked_orders = set(await session.scalars(
      select(PurchaseSubmission.order_id).join(Purchase, Purchase.id == PurchaseSubmission.purchase_id)
      .where(PurchaseSubmission.order_id.in_(order_ids)),
    ))
    events = [event for event in events if event.meta.type != 'customerorder' or str(event.meta.entity_uuid) in linked_orders]

  # Stable order avoids opposite lock ordering for overlapping batches.
  for event in sorted(events, key=lambda item: (item.meta.type, str(item.meta.entity_uuid))):
    values = dict(
      entity_type=event.meta.type,
      entity_uuid=event.meta.entity_uuid,
      action=event.action,
      request_id=request_id,
      payload=event.model_dump(mode='json', exclude_none=True),
    )
    statement = insert(SyncTask).values(
      **values, status='pending',
    )
    changes = dict(
      action=values['action'],
      request_id=request_id,
      payload=values['payload'],
      status='pending',
      updated=func.now(),
    )
    if dialect == 'sqlite':
      statement = statement.on_conflict_do_update(
        index_elements=['entity_type', 'entity_uuid'], set_=changes,
      )
    else:
      statement = statement.on_duplicate_key_update(**changes)
    await session.execute(statement)
