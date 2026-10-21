from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import ChangeEvent, Product, ProductVariant
from src.models.sync import SyncTask


async def get_last_updates(session: AsyncSession) -> dict:
  last_sync = await session.scalar(select(func.max(SyncTask.updated)).where(SyncTask.status == 'synced'))
  last_import = await session.scalar(select(func.max(ChangeEvent.created)).where(
    ChangeEvent.event_type == 'products.moysklad.imported',
  ))
  query = (select(
    SyncTask.id, SyncTask.entity_type, SyncTask.entity_uuid, SyncTask.action, SyncTask.status,
    func.coalesce(Product.name, ProductVariant.name).label('entity_name'), SyncTask.updated,
  ).outerjoin(Product, and_(SyncTask.entity_type == 'product', Product.uuid == SyncTask.entity_uuid))
    .outerjoin(ProductVariant, and_(SyncTask.entity_type == 'variant', ProductVariant.uuid == SyncTask.entity_uuid))
    .order_by(SyncTask.updated.desc(), SyncTask.id.desc()))
  rows = (await session.execute(query.limit(5))).all()
  if not any(row.status == 'pending' for row in rows):
    pending = (await session.execute(query.where(SyncTask.status == 'pending').limit(1))).first()
    if pending:
      rows = [*rows[:4], pending]
  return {
    'last_update': max((int(value.timestamp()) for value in (last_sync, last_import) if value), default=0),
    'updates': [dict(
      id=row.id, entity_type=row.entity_type, entity_uuid=row.entity_uuid,
      action=row.action, status=row.status, entity_name=row.entity_name or str(row.entity_uuid),
      updated_at=int(row.updated.timestamp()),
    ) for row in rows],
  }
