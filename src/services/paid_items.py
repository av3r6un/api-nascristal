"""Use paid receipt amounts, never current catalog prices."""
from decimal import Decimal, InvalidOperation

from src.exceptions import JSRError
from src.models import Payment, ProductVariant
from src.services.yookassa import get_yookassa_receipt


async def paid_items(session, purchase):
  payment = await session.get(Payment, purchase.payment_id) if purchase.payment_id else None
  if not payment or payment.status != 'succeeded' or not payment.paid:
    raise JSRError(status=409, message='A successful paid payment is required')
  saved = payment.request_payload or {}
  receipt = saved.get('receipt')
  if not receipt:
    if not payment.external_payment_id:
      raise JSRError(status=409, message='Paid receipt is missing')
    receipt = await get_yookassa_receipt(payment.external_payment_id)
  rows = receipt.get('items', [])
  ids = saved.get('receipt_item_variant_ids')
  if ids is None:
    # Older receipts have no IDs. Match only unique, unchanged descriptions.
    names = {}
    for product_id in purchase.product_quantities:
      product = await session.get(ProductVariant, int(product_id))
      name = product.name[:128] if product else None
      if not name or name in names:
        raise JSRError(status=409, message='Cannot unambiguously match paid receipt items')
      names[name] = str(product_id)
    ids = [names.get(row.get('description')) for row in rows]
  error = 'Paid receipt does not match order items, quantities or total'
  try:
    ids = [str(value) for value in ids]
    quantities = {str(key): Decimal(str(value)) for key, value in purchase.product_quantities.items()}
    if not rows or len(ids) != len(rows) or len(set(ids)) != len(ids) or set(ids) != set(quantities):
      raise ValueError()
    items = []
    total = Decimal(0)
    for product_id, row in zip(ids, rows):
      quantity = Decimal(str(row['quantity']))
      cost = Decimal(str(row['amount']['value']))
      if (not quantity.is_finite() or quantity != quantities[product_id] or quantity < 1
        or quantity > 999 or quantity != quantity.to_integral_value()
        or not cost.is_finite() or cost < 0 or cost.as_tuple().exponent < -2
        or row['amount']['currency'] != 'RUB' or not row['description']):
        raise ValueError()
      total += quantity * cost
      items.append(dict(name=row['description'][:255], ware_key=product_id,
        amount=int(quantity), cost=float(cost), payment={'value': 0}))
    if payment.currency != 'RUB' or total != Decimal(payment.amount_value) or total != Decimal(purchase.final_price):
      raise ValueError()
  except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
    raise JSRError(status=409, message=error) from exc
  # Cache recovered data and legacy associations only after validating them.
  if not saved.get('receipt') or saved.get('receipt_item_variant_ids') is None:
    payment.request_payload = {**saved, 'receipt': receipt, 'receipt_item_variant_ids': ids}
  return items
