"""Read an address from MoySklad and update the linked local Purchase."""
from sqlalchemy import select
from src.models import PurchaseSubmission
from src.schemas.contact import normalize_contact_info
from src.services.moysklad_client import MoySkladClient, MoySkladError
from src.services.purchase_sync import lock_purchase, verify_order

async def refresh_address(session, order_id):
  submission = (await session.execute(select(PurchaseSubmission)
    .where(PurchaseSubmission.order_id == order_id))).scalar_one_or_none()
  if submission:
    purchase = await lock_purchase(session, submission.purchase_id)
    async with MoySkladClient() as client:
      try:
        order = await client.get(f'/entity/customerorder/{order_id}')
      except MoySkladError as exc:
        if exc.status_code == 404:
          return
        raise
    verify_order(order, purchase, submission)
    address = order.get('shipmentAddress') or ''
    if not isinstance(address, str):
      raise ValueError('Invalid MoySklad shipmentAddress')
    contact = normalize_contact_info(purchase.contact_info)
    if contact['delivery']['address'] != address:
      contact['delivery']['address'] = address
      purchase.contact_info = contact
  await session.commit()
