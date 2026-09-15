import uuid
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from src.core.config import settings
from src.core.database import get_db
from src.exceptions import JSRError
from src.models import AttributeOption, Offer, Payment, ProductAttribute, ProductVariant, Purchase, PurchaseStatus

Product = ProductVariant
PropertyOption = AttributeOption
from src.models.payment import PaymentStatus as ProviderPaymentStatus
from src.schemas.contact import normalize_contact_info
from src.schemas.purchase import (
  PurchaseCreateRequest,
  PurchaseResponse,
  PurchasesResponse,
  PurchaseTrackingResponse,
  PurchaseUpdateRequest,
)
from src.services.purchase_sync import build_order_payload, lock_purchase, sync_purchase, sync_purchase_status
from src.services.payment_sync import apply_successful_payment, refresh_payment_state
from src.services.yookassa import (
  build_purchase_return_url,
  build_yookassa_payment_payload,
  cancel_yookassa_payment,
  create_yookassa_payment,
)


router = APIRouter(prefix="/api/purchases", tags=["purchases"])

FINAL_PAYMENT_STATUSES = {
  ProviderPaymentStatus.SUCCEEDED.value,
  ProviderPaymentStatus.CANCELED.value,
  ProviderPaymentStatus.FAILED.value,
}


def _contact_info(payload: PurchaseCreateRequest) -> dict:
  return {
    "name": payload.customer.name,
    "phone": payload.customer.phone,
    "username": payload.customer.username,
    "email": payload.customer.email,
  }


async def _get_products_or_404(session: AsyncSession, product_ids: list[int]) -> list[Product]:
  unique_product_ids = list(dict.fromkeys(product_ids))
  query = (
    select(Product)
    .options(
      selectinload(Product.attributes)
      .selectinload(ProductAttribute.option)
      .selectinload(AttributeOption.attribute)
    )
    .options(selectinload(Product.offer))
    .where(Product.id.in_(unique_product_ids))
  )
  products = (await session.execute(query)).scalars().all()
  products_by_id = {product.id: product for product in products}
  missing = [product_id for product_id in unique_product_ids if product_id not in products_by_id]
  if missing:
    raise JSRError("not_found", message=f"Products not found: {', '.join(map(str, missing))}")
  return [products_by_id[product_id] for product_id in unique_product_ids]


async def _get_products_by_offer_ids_or_404(session: AsyncSession, offer_ids: list[int]) -> dict[int, Product]:
  unique_offer_ids = list(dict.fromkeys(offer_ids))
  query = (
    select(Product)
    .join(Offer, Offer.variant_id == Product.id)
    .options(
      selectinload(Product.attributes)
      .selectinload(ProductAttribute.option)
      .selectinload(AttributeOption.attribute)
    )
    .options(selectinload(Product.offer))
    .where(Offer.id.in_(unique_offer_ids))
  )
  products = (await session.execute(query)).scalars().all()
  products_by_offer_id = {
    product.offer.id: product
    for product in products
    if product.offer is not None
  }
  missing = [offer_id for offer_id in unique_offer_ids if offer_id not in products_by_offer_id]
  if missing:
    raise JSRError("not_found", message=f"Offers not found: {', '.join(map(str, missing))}")
  return products_by_offer_id


def _resolve_property_option_eids(product: Product, properties: list[str]) -> list[str]:
  options_by_value = {}
  options_by_eid = {}
  for attribute in product.attributes:
    if attribute.option is None:
      continue
    option_id = str(attribute.option.id)
    options_by_value[attribute.option.value] = option_id
    options_by_eid[option_id] = option_id

  resolved = []
  missing = []
  for property_value in properties:
    option_eid = options_by_eid.get(property_value) or options_by_value.get(property_value)
    if option_eid is None:
      missing.append(property_value)
    else:
      resolved.append(option_eid)

  if missing:
    raise JSRError("bad_request", message=f"Properties not found for product {product.id}: {', '.join(missing)}")

  return resolved


def _resolve_properties_by_product(products_by_id: dict[int, Product], properties_by_product: dict[int, list[str]]) -> dict[str, list[str]]:
  resolved = {}
  for product_id, properties in properties_by_product.items():
    product = products_by_id.get(product_id)
    if product is None:
      raise JSRError("not_found", message=f"Product not found: {product_id}")
    resolved[str(product_id)] = _resolve_property_option_eids(product, properties)
  return resolved


def _normalize_quantities_by_product(product_quantities: dict[int, int]) -> dict[str, int]:
  return {str(product_id): quantity for product_id, quantity in product_quantities.items()}


def _money(value) -> Decimal:
  return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _format_money(value: Decimal) -> str:
  return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def _primary_offer(product: Product):
  offer = product.offer
  if offer is None or not offer.is_active:
    raise JSRError("bad_request", message=f"Active offer not found for product {product.id}")
  return offer


def _price_int(value: Decimal) -> int:
  integer_value = value.to_integral_value(rounding=ROUND_HALF_UP)
  if value != integer_value:
    raise JSRError("bad_request", message=f"Purchase total {value} must be a whole number")
  return int(integer_value)


def _build_receipt_for_purchase(
  *,
  customer_email: str | None,
  price: int,
  products_by_id: dict[int, Product],
  quantities_by_product: dict[int, int],
) -> dict:
  if not customer_email:
    raise JSRError("bad_request", message="Customer email is required for card payment receipt")

  items = []
  total = Decimal("0.00")
  for product_id, quantity in quantities_by_product.items():
    product = products_by_id.get(product_id)
    if product is None:
      raise JSRError("not_found", message=f"Product not found: {product_id}")

    offer = _primary_offer(product)
    unit_amount = _money(offer.amount)
    total += unit_amount * quantity
    items.append({
      "description": product.name[:128],
      "quantity": quantity,
      "amount": {
        "value": _format_money(unit_amount),
        "currency": "RUB",
      },
      "vat_code": settings.YOOKASSA_RECEIPT_VAT_CODE,
      "payment_mode": settings.YOOKASSA_RECEIPT_PAYMENT_MODE,
      "payment_subject": settings.YOOKASSA_RECEIPT_PAYMENT_SUBJECT,
    })

  expected_total = _money(price)
  if total != expected_total:
    raise JSRError(
      "bad_request",
      message=f"Receipt items total {total} does not match payment price {expected_total}",
    )

  return {
    "customer": {
      "email": customer_email,
    },
    "items": items,
  }


def _calculate_purchase_total(products_by_id: dict[int, Product], quantities_by_product: dict[int, int]) -> Decimal:
  total = Decimal("0.00")
  for product_id, quantity in quantities_by_product.items():
    product = products_by_id.get(product_id)
    if product is None:
      raise JSRError("not_found", message=f"Product not found: {product_id}")
    total += _money(_primary_offer(product).amount) * quantity
  return total


def _purchase_quantities_as_ints(purchase: Purchase) -> dict[int, int]:
  return {int(product_id): int(quantity) for product_id, quantity in purchase.product_quantities.items()}


def _payment_fingerprint(
  *,
  contact_info: dict,
  products_by_id: dict[int, Product],
  quantities_by_product: dict[int, int],
) -> dict:
  return {
    "email": contact_info.get("email") or "",
    "items": tuple(
      sorted(
        (
          product_id,
          quantity,
          _price_int(_money(_primary_offer(products_by_id[product_id]).amount)),
        )
        for product_id, quantity in quantities_by_product.items()
      )
    ),
  }


def _collect_property_eids(properties: dict[str, list[str]]) -> list[str]:
  return [
    option_eid
    for option_eids in properties.values()
    for option_eid in option_eids
  ]


def _serialize_payment(payment: Payment | None) -> dict | None:
  if payment is None:
    return None

  return {
    "id": payment.id,
    "uuid": payment.uuid,
    "provider": payment.provider,
    "idempotency_key": payment.idempotency_key,
    "external_payment_id": payment.external_payment_id,
    "status": payment.status,
    "amount_value": payment.amount_value,
    "currency": payment.currency,
    "paid": payment.paid,
    "confirmation_url": payment.confirmation_url,
    "return_url": payment.return_url,
    "created_ts": payment.created_ts,
    "updated_ts": payment.updated_ts,
  }


def _serialize_purchase_tracking(payment: Payment | None, purchase: Purchase) -> dict:
  contact_info = normalize_contact_info(purchase.contact_info)
  return {
    "purchase": {
      "id": purchase.id,
      "created_ts": purchase.created_ts,
      "price": purchase.final_price,
      "status": purchase.status.value,
      "contact_info": contact_info,
    },
    "payment": (
      {
        "status": payment.status,
        "amount_value": payment.amount_value,
        "currency": payment.currency,
        "paid": payment.paid,
        "confirmation_url": payment.confirmation_url,
      }
      if payment is not None else None
    ),
  }


async def _load_product_map(session: AsyncSession, product_ids: list[int]) -> dict[int, Product]:
  if not product_ids:
    return {}

  result = await session.execute(
    select(Product)
    .options(selectinload(Product.offer))
    .where(Product.id.in_(product_ids))
  )
  return {product.id: product for product in result.scalars().all()}


async def _load_property_option_map(session: AsyncSession, property_eids: list[str]) -> dict[str, PropertyOption]:
  if not property_eids:
    return {}

  option_ids = [int(option_id) for option_id in property_eids if option_id.isdigit()]
  if not option_ids:
    return {}

  result = await session.execute(
    select(PropertyOption)
    .options(selectinload(PropertyOption.attribute))
    .where(PropertyOption.id.in_(option_ids))
  )
  return {str(option.id): option for option in result.scalars().all()}


async def _load_payment_map(session: AsyncSession, payment_ids: list[int | None]) -> dict[int, Payment]:
  normalized_payment_ids = [payment_id for payment_id in payment_ids if payment_id is not None]
  if not normalized_payment_ids:
    return {}

  result = await session.execute(select(Payment).where(Payment.id.in_(normalized_payment_ids)))
  return {payment.id: payment for payment in result.scalars().all()}


def _serialize_purchase(
  purchase: Purchase,
  products_by_id: dict[int, Product],
  options_by_eid: dict[str, PropertyOption],
  payments_by_id: dict[int, Payment],
) -> dict:
  payment = payments_by_id.get(purchase.payment_id) if purchase.payment_id is not None else None

  def serialize_product(product_id: int, product: Product) -> dict:
    offer = _primary_offer(product)
    return {
      "id": offer.id,
      "sku": product.sku,
      "name": product.name,
      "price": _price_int(_money(offer.amount)),
      "quantity": {
        "value": purchase.product_quantities.get(str(product_id), 0),
        "max": int(offer.quantity),
      },
      "properties": [
        {
          "value": option.value,
          "name": option.label,
          "property": {
            "id": option.attribute.id,
            "name": option.attribute.name,
          },
        }
        for option_eid in purchase.properties.get(str(product_id), [])
        if (option := options_by_eid.get(option_eid)) is not None and option.attribute is not None
      ],
    }

  contact_info = normalize_contact_info(purchase.contact_info)
  return {
    "id": purchase.id,
    "uuid": purchase.uuid,
    "payment_id": purchase.payment_id,
    "products": [
      serialize_product(product_id, product)
      for product_id in purchase.product_ids
      if (product := products_by_id.get(product_id)) is not None
    ],
    "contact_info": contact_info,
    "payment": _serialize_payment(payment),
    "status": purchase.status.value,
    "created_ts": purchase.created_ts,
    "updated_ts": purchase.updated_ts,
  }


async def _serialize_purchase_with_refs(session: AsyncSession, purchase: Purchase) -> dict:
  products_by_id = await _load_product_map(session, purchase.product_ids)
  options_by_eid = await _load_property_option_map(session, _collect_property_eids(purchase.properties))
  payments_by_id = await _load_payment_map(session, [purchase.payment_id])
  return _serialize_purchase(purchase, products_by_id, options_by_eid, payments_by_id)


async def _get_purchase_or_404(session: AsyncSession, purchase_id: int) -> Purchase:
  purchase = await Purchase.first(session, id=purchase_id)
  if not purchase:
    raise JSRError("not_found", message=f"Purchase not found: {purchase_id}")
  return purchase


async def _get_purchase_by_uuid_or_404(session: AsyncSession, purchase_uuid: str) -> Purchase:
  purchase = await Purchase.first(session, uuid=purchase_uuid)
  if not purchase:
    raise JSRError("not_found", message=f"Purchase not found: {purchase_uuid}")
  return purchase


async def _cancel_payment_for_purchase(payment: Payment | None) -> None:
  if payment is None or payment.status in FINAL_PAYMENT_STATUSES:
    return

  if payment.external_payment_id:
    provider_payment = await cancel_yookassa_payment(
      idempotency_key=f"cancel-{payment.uuid}"[:64],
      external_payment_id=payment.external_payment_id,
    )
    payment.status = provider_payment.get("status", ProviderPaymentStatus.CANCELED.value)
    payment.paid = bool(provider_payment.get("paid", False))
    payment.confirmation_url = (provider_payment.get("confirmation") or {}).get("confirmation_url")
    payment.response_payload = provider_payment
  else:
    payment.status = ProviderPaymentStatus.CANCELED.value
    payment.paid = False
    payment.confirmation_url = None
    payment.response_payload = {"status": ProviderPaymentStatus.CANCELED.value}


async def _create_card_payment_for_purchase(
  *,
  session: AsyncSession,
  purchase: Purchase,
  products_by_id: dict[int, Product],
  quantities_by_product: dict[int, int],
) -> Payment:
  base_return_url = settings.YOOKASSA_RETURN_URL
  if not base_return_url:
    raise JSRError(status=500, message="YooKassa return URL is not configured")

  return_url = build_purchase_return_url(base_return_url, purchase.uuid)
  amount_value = _format_money(_money(purchase.final_price))
  payment = await Payment.first(session, id=purchase.payment_id) if purchase.payment_id is not None else None
  if payment is not None and payment.status == ProviderPaymentStatus.SUCCEEDED.value:
    return payment
  if (
    payment is not None
    and payment.status not in FINAL_PAYMENT_STATUSES
    and payment.amount_value == amount_value
    and payment.confirmation_url
  ):
    return payment

  contact_info = normalize_contact_info(purchase.contact_info)
  customer_name = contact_info.get("name") or purchase.uuid

  should_reuse_payment = (
    payment is not None
    and payment.status not in FINAL_PAYMENT_STATUSES
    and payment.amount_value == amount_value
  )
  if not should_reuse_payment:
    idempotency_key = f"purchase-{purchase.uuid}"[:64] if payment is None else f"purchase-{purchase.uuid[:8]}-{uuid.uuid4()}"[:64]
    payment = Payment(
      idempotency_key=idempotency_key,
      amount_value=amount_value,
      return_url=return_url,
      description=f"Purchase {customer_name}",
    )
    session.add(payment)
    await session.flush()
    purchase.payment_id = payment.id
  else:
    idempotency_key = payment.idempotency_key
    payment.return_url = return_url
    payment.description = f"Purchase {customer_name}"

  payment_payload = build_yookassa_payment_payload(
    price=purchase.final_price,
    description=f"Purchase #{purchase.id}",
    return_url=return_url,
    metadata={
      "purchase_id": str(purchase.id),
      "purchase_uuid": purchase.uuid,
      "payment_id": str(payment.id),
    },
    receipt=_build_receipt_for_purchase(
      customer_email=contact_info.get("email"),
      price=purchase.final_price,
      products_by_id=products_by_id,
      quantities_by_product=quantities_by_product,
    ),
  )
  payment.description = payment_payload["description"]
  payment.payment_metadata = payment_payload["metadata"]
  payment.request_payload = payment_payload

  try:
    provider_payment = await create_yookassa_payment(
      idempotency_key=idempotency_key,
      payload=payment_payload,
    )
  except JSRError:
    payment.status = ProviderPaymentStatus.FAILED.value
    payment.response_payload = {"error": "payment_creation_failed"}
    await session.commit()
    raise

  payment.external_payment_id = provider_payment.get("id")
  payment.status = provider_payment.get("status", ProviderPaymentStatus.PENDING.value)
  payment.paid = bool(provider_payment.get("paid", False))
  payment.confirmation_url = (provider_payment.get("confirmation") or {}).get("confirmation_url")
  payment.response_payload = provider_payment
  return payment


async def _start_purchase_payment(
  *,
  session: AsyncSession,
  purchase: Purchase,
  products_by_id: dict[int, Product],
  patch_moysklad_order: bool = False,
) -> Payment:
  purchase.status = PurchaseStatus.AWAITING_PAYMENT
  if settings.MOYSKLAD_CHECKOUT_SYNC_ENABLED:
    await sync_purchase(session, purchase, products_by_id, patch=patch_moysklad_order)

  payment = await _create_card_payment_for_purchase(
    session=session,
    purchase=purchase,
    products_by_id=products_by_id,
    quantities_by_product=_purchase_quantities_as_ints(purchase),
  )
  await session.commit()
  await session.refresh(purchase)
  await session.refresh(payment)
  await apply_successful_payment(session, payment, purchase)
  return payment


@router.post("/", response_model=PurchaseResponse, status_code=200)
async def create_purchase(
  payload: PurchaseCreateRequest,
  session: AsyncSession = Depends(get_db),
  idempotency_key: uuid.UUID | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
  if idempotency_key is not None:
    existing = await Purchase.first(session, uuid=str(idempotency_key))
    if existing is not None:
      purchase = await lock_purchase(session, existing.id)
      if purchase.status not in {PurchaseStatus.CREATED, PurchaseStatus.AWAITING_PAYMENT}:
        return await _serialize_purchase_with_refs(session, purchase)
      products_by_id = await _load_product_map(session, purchase.product_ids)
      await _start_purchase_payment(
        session=session,
        purchase=purchase,
        products_by_id=products_by_id,
        patch_moysklad_order=True,
      )
      return await _serialize_purchase_with_refs(session, purchase)
  offer_ids = [item.id for item in payload.items]
  products_by_offer_id = await _get_products_by_offer_ids_or_404(session, offer_ids)
  product_ids = [products_by_offer_id[offer_id].id for offer_id in offer_ids]
  products = list(products_by_offer_id.values())
  products_by_id = {product.id: product for product in products}
  properties_by_product: dict[int, list[str]] = {}
  quantities_by_product: dict[int, int] = {}
  for item in payload.items:
    product_id = products_by_offer_id[item.id].id
    properties_by_product.setdefault(product_id, []).extend(item.properties)
    quantities_by_product[product_id] = quantities_by_product.get(product_id, 0) + item.quantity.value

  contact_info = _contact_info(payload)
  purchase = Purchase(
    product_ids=product_ids,
    properties=_resolve_properties_by_product(products_by_id, properties_by_product),
    product_quantities=_normalize_quantities_by_product(quantities_by_product),
    quantity=sum(item.quantity.value for item in payload.items),
    contact_info=contact_info,
    final_price=payload.price,
    purchase_uuid=str(idempotency_key) if idempotency_key else None,
  )
  # Validate before persisting. The Purchase itself is the durable retry payload.
  if settings.MOYSKLAD_CHECKOUT_SYNC_ENABLED:
    build_order_payload(purchase, products_by_id)
  elif _calculate_purchase_total(products_by_id, quantities_by_product) != _money(payload.price):
    raise JSRError('bad_request', message='Order total does not match items')
  session.add(purchase)
  try:
    await session.commit()
  except IntegrityError:
    await session.rollback()
    if idempotency_key is None:
      raise
    existing = await Purchase.first(session, uuid=str(idempotency_key))
    if existing is None:
      raise
    purchase = existing
  purchase = await lock_purchase(session, purchase.id)
  products_by_id = await _load_product_map(session, purchase.product_ids)
  await _start_purchase_payment(
    session=session,
    purchase=purchase,
    products_by_id=products_by_id,
  )
  return await _serialize_purchase_with_refs(session, purchase)


@router.get("/", response_model=PurchasesResponse, status_code=200)
async def get_purchases(session: AsyncSession = Depends(get_db)) -> dict[str, list[dict]]:
  result = await session.execute(
    select(Purchase)
    .options(selectinload(Purchase.payment))
    .order_by(Purchase.created.desc(), Purchase.id.desc())
  )
  purchases = result.scalars().all()
  product_ids = [
    product_id
    for purchase in purchases
    for product_id in purchase.product_ids
  ]
  property_eids = [
    option_eid
    for purchase in purchases
    for option_eid in _collect_property_eids(purchase.properties)
  ]
  products_by_id = await _load_product_map(session, product_ids)
  options_by_eid = await _load_property_option_map(session, property_eids)
  payments_by_id = await _load_payment_map(session, [purchase.payment_id for purchase in purchases])
  return {"items": [_serialize_purchase(purchase, products_by_id, options_by_eid, payments_by_id) for purchase in purchases]}


@router.get("/by-uuid/{purchase_uuid}", response_model=PurchaseTrackingResponse, response_model_exclude_none=True, status_code=200)
async def get_purchase_by_uuid(purchase_uuid: str, session: AsyncSession = Depends(get_db)) -> dict:
  purchase = await _get_purchase_by_uuid_or_404(session, purchase_uuid)
  payment = await Payment.first(session, id=purchase.payment_id) if purchase.payment_id is not None else None
  if payment is not None:
    payment = await refresh_payment_state(session, payment, purchase)
  return _serialize_purchase_tracking(payment, purchase)


@router.post("/by-uuid/{purchase_uuid}/payment", response_model=PurchaseTrackingResponse, response_model_exclude_none=True, status_code=200)
async def create_purchase_payment_by_uuid(purchase_uuid: str, session: AsyncSession = Depends(get_db)) -> dict:
  purchase = await _get_purchase_by_uuid_or_404(session, purchase_uuid)
  payment = await Payment.first(session, id=purchase.payment_id) if purchase.payment_id is not None else None
  if payment is not None:
    payment = await refresh_payment_state(session, payment, purchase)

  if payment is not None and payment.status == ProviderPaymentStatus.SUCCEEDED.value:
    return _serialize_purchase_tracking(payment, purchase)
  if purchase.status != PurchaseStatus.AWAITING_PAYMENT:
    raise JSRError("bad_request", message="Purchase is not awaiting payment")

  quantities_by_product = _purchase_quantities_as_ints(purchase)
  products = await _get_products_or_404(session, purchase.product_ids)
  products_by_id = {product.id: product for product in products}
  payment = await _create_card_payment_for_purchase(
    session=session,
    purchase=purchase,
    products_by_id=products_by_id,
    quantities_by_product=quantities_by_product,
  )

  await session.commit()
  await session.refresh(purchase)
  await session.refresh(payment)
  await apply_successful_payment(session, payment, purchase)
  return _serialize_purchase_tracking(payment, purchase)


@router.get("/{purchase_id}", response_model=PurchaseResponse, status_code=200)
async def get_purchase(purchase_id: int, session: AsyncSession = Depends(get_db)) -> dict:
  purchase = await _get_purchase_or_404(session, purchase_id)
  return await _serialize_purchase_with_refs(session, purchase)


@router.patch("/{purchase_id}", response_model=PurchaseResponse, status_code=200)
async def update_purchase(
  purchase_id: int,
  payload: PurchaseUpdateRequest,
  session: AsyncSession = Depends(get_db),
) -> dict:
  purchase = await lock_purchase(session, purchase_id)
  if payload.products is not None:
    offer_ids = [item.id for item in payload.products]
    products_by_offer_id = await _get_products_by_offer_ids_or_404(session, offer_ids)
    product_ids = [products_by_offer_id[offer_id].id for offer_id in offer_ids]
    quantities_by_product: dict[int, int] = {}
    properties_by_product: dict[int, list[str]] = {}
    for item in payload.products:
      product_id = products_by_offer_id[item.id].id
      quantities_by_product[product_id] = quantities_by_product.get(product_id, 0) + item.quantity.value
      properties_by_product.setdefault(product_id, []).extend(property_item.value for property_item in item.properties)
  else:
    product_ids = purchase.product_ids
    quantities_by_product = _purchase_quantities_as_ints(purchase)
    properties_by_product = {
      int(product_id): option_eids
      for product_id, option_eids in purchase.properties.items()
    }

  old_quantities_by_product = _purchase_quantities_as_ints(purchase)
  products = await _get_products_or_404(session, list(dict.fromkeys([*purchase.product_ids, *product_ids])))
  products_by_id = {product.id: product for product in products}
  old_contact_info = normalize_contact_info(purchase.contact_info)
  old_fingerprint = _payment_fingerprint(
    contact_info=old_contact_info,
    products_by_id=products_by_id,
    quantities_by_product=old_quantities_by_product,
  )
  contact_info = (
    normalize_contact_info(payload.contact_info.model_dump())
    if payload.contact_info is not None
    else normalize_contact_info(purchase.contact_info)
  )
  new_fingerprint = _payment_fingerprint(
    contact_info=contact_info,
    products_by_id=products_by_id,
    quantities_by_product=quantities_by_product,
  )
  payment_inputs_changed = old_fingerprint != new_fingerprint

  calculated_total = _calculate_purchase_total(products_by_id, quantities_by_product)
  calculated_final_price = _price_int(calculated_total)
  if payload.final_price is not None and payload.final_price != calculated_final_price:
    raise JSRError(
      "bad_request",
      message=f"Final price {payload.final_price} does not match items total {calculated_final_price}",
    )

  if payload.products is not None:
    purchase.product_ids = product_ids
    purchase.properties = _resolve_properties_by_product(products_by_id, properties_by_product)
    purchase.product_quantities = _normalize_quantities_by_product(quantities_by_product)
    purchase.quantity = sum(quantities_by_product.values())

  purchase.contact_info = contact_info
  purchase.final_price = payload.final_price if payload.final_price is not None else calculated_final_price
  existing_payment = await Payment.first(session, id=purchase.payment_id) if purchase.payment_id is not None else None
  if (
    purchase.status == PurchaseStatus.AWAITING_PAYMENT
    and existing_payment is not None
    and existing_payment.amount_value != _format_money(_money(calculated_final_price))
  ):
    payment_inputs_changed = True
  if (
    purchase.status == PurchaseStatus.AWAITING_PAYMENT
    and payment_inputs_changed
    and existing_payment is not None
    and existing_payment.status == ProviderPaymentStatus.SUCCEEDED.value
  ):
    raise JSRError("bad_request", message="Cannot change payment details for an already paid purchase")
  if purchase.status == PurchaseStatus.AWAITING_PAYMENT and payment_inputs_changed:
    await _cancel_payment_for_purchase(existing_payment)
  await _start_purchase_payment(
    session=session,
    purchase=purchase,
    products_by_id=products_by_id,
    patch_moysklad_order=True,
  )
  return await _serialize_purchase_with_refs(session, purchase)


@router.put("/{purchase_id}", response_model=PurchaseResponse, status_code=200)
async def mark_purchase_delivering(purchase_id: int, session: AsyncSession = Depends(get_db)) -> dict:
  purchase = await lock_purchase(session, purchase_id)
  purchase.status = PurchaseStatus.DELIVERING
  # mailing here
  await sync_purchase_status(session, purchase)
  await session.commit()
  await session.refresh(purchase)
  return await _serialize_purchase_with_refs(session, purchase)


@router.post("/{purchase_id}", response_model=PurchaseResponse, status_code=200)
async def finish_purchase(purchase_id: int, session: AsyncSession = Depends(get_db)) -> dict:
  purchase = await lock_purchase(session, purchase_id)
  purchase.status = PurchaseStatus.FINISHED
  # mailing here
  await sync_purchase_status(session, purchase)
  await session.commit()
  await session.refresh(purchase)
  return await _serialize_purchase_with_refs(session, purchase)


@router.post("/{purchase_id}/sync", response_model=PurchaseResponse, status_code=200)
async def retry_purchase_sync(purchase_id: int, session: AsyncSession = Depends(get_db)) -> dict:
  purchase = await lock_purchase(session, purchase_id)
  products_by_id = await _load_product_map(session, purchase.product_ids)
  await sync_purchase(session, purchase, products_by_id)
  await session.commit()
  await session.refresh(purchase)
  return await _serialize_purchase_with_refs(session, purchase)
