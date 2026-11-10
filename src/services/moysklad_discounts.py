from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from src.core.database import session_maker
from src.models import Discount, DiscountProduct
from src.services.moysklad_client import MoySkladClient


async def reconcile_discounts(sessions=session_maker):
  snapshot = {}
  async with MoySkladClient() as client:
    async for row in client.iter_entities('discount'):
      # This table represents percentage rules that can be shown to every visitor.
      if (row['meta']['type'] != 'specialpricediscount'
          or row['allAgents'] is not True or row['usePriceType'] is not False):
        continue
      amount = Decimal(str(row['discount']))
      if not amount.is_finite() or not 0 <= amount <= 100 or amount != round(amount, 6):
        raise ValueError('Invalid MoySklad discount percentage')
      if type(row['active']) is not bool or type(row['allProducts']) is not bool:
        raise ValueError('Invalid MoySklad discount flags')
      scope = set()
      if not row['allProducts']:
        for item in row['assortment']:
          meta = item['meta']
          entity_type, entity_id = meta['href'].rsplit('/', 2)[-2:]
          if entity_type != meta['type']:
            raise ValueError('Invalid MoySklad discount assortment reference')
          scope.add((entity_type, UUID(entity_id)))
      uuid = UUID(row['id'])
      if uuid in snapshot:
        raise ValueError('Duplicate MoySklad discount')
      snapshot[uuid] = (dict(name=row['name'], active=row['active'],
        all_products=row['allProducts'], amount=amount), scope)

  async with sessions() as session, session.begin():
    discounts = {row.uuid: row for row in (await session.scalars(select(Discount))).all()}
    links = {}
    for row in (await session.scalars(select(DiscountProduct))).all():
      links.setdefault(row.discount_id, {})[row.entity_type, row.entity_uuid] = row

    for uuid, (values, scope) in snapshot.items():
      discount = discounts.pop(uuid, None)
      if discount is None:
        discount = Discount(uuid=uuid, **values)
        session.add(discount)
        await session.flush()
      else:
        for field, value in values.items():
          setattr(discount, field, value)
      existing = links.get(discount.id, {})
      for key in existing.keys() - scope:
        await session.delete(existing[key])
      for entity_type, entity_uuid in scope - existing.keys():
        session.add(DiscountProduct(discount_id=discount.id, entity_type=entity_type, entity_uuid=entity_uuid))

    for discount in discounts.values():
      for row in links.get(discount.id, {}).values():
        await session.delete(row)
      await session.flush()
      await session.delete(discount)
