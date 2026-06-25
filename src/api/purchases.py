import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.config import settings
from src.core.database import get_db
from src.exceptions import JSRError
from src.models import Payment, Product, ProductAttribute, PropertyOption, Purchase
from src.models.payment import PaymentStatus as ProviderPaymentStatus
from src.models.purchase import PaymentStatus as PurchasePaymentStatus
from src.schemas.purchase import PurchaseCreateRequest, PurchasePatchRequest, PurchaseResponse, PurchasesResponse, PurchaseTrackingResponse
from src.services.payment_sync import refresh_payment_state
from src.services.yookassa import build_purchase_return_url, build_yookassa_payment_payload, create_yookassa_payment


router = APIRouter(prefix="/api/purchases", tags=["purchases"])


def _contact_info(payload: PurchaseCreateRequest) -> dict:
  return {
    "name": payload.name,
    "phone": payload.phone,
    "delivery": payload.delivery,
    "username": payload.username,
  }


async def _get_products_or_404(session: AsyncSession, product_ids: list[int]) -> list[Product]:
  unique_product_ids = list(dict.fromkeys(product_ids))
  query = (
    select(Product)
    .options(selectinload(Product.attributes).selectinload(ProductAttribute.option))
    .where(Product.id.in_(unique_product_ids))
  )
  products = (await session.execute(query)).scalars().all()
  products_by_id = {product.id: product for product in products}
  missing = [product_id for product_id in unique_product_ids if product_id not in products_by_id]
  if missing:
    raise JSRError("not_found", message=f"Products not found: {', '.join(map(str, missing))}")
  return [products_by_id[product_id] for product_id in unique_product_ids]


def _resolve_property_option_eids(product: Product, properties: list[str]) -> list[str]:
  options_by_value = {}
  options_by_eid = {}
  for attribute in product.attributes:
    if attribute.option is None:
      continue
    options_by_value[attribute.option.value] = attribute.option.eid
    options_by_eid[attribute.option.eid] = attribute.option.eid

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
    "purchase": None,
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
  return {
    "purchase": {
      "id": purchase.id,
      "created_ts": purchase.created_ts,
      "payment_method": purchase.payment_method,
      "contact_info": purchase.contact_info,
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

  result = await session.execute(select(Product).where(Product.id.in_(product_ids)))
  return {product.id: product for product in result.scalars().all()}


async def _load_property_option_map(session: AsyncSession, property_eids: list[str]) -> dict[str, PropertyOption]:
  if not property_eids:
    return {}

  result = await session.execute(
    select(PropertyOption)
    .options(selectinload(PropertyOption.property))
    .where(PropertyOption.eid.in_(property_eids))
  )
  return {option.eid: option for option in result.scalars().all()}


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
  return {
    "id": purchase.id,
    "uuid": purchase.uuid,
    "payment_id": purchase.payment_id,
    "products": [
      {
        "id": product.id,
        "sku": product.sku,
        "name": product.name,
        "quantity": purchase.product_quantities.get(str(product_id), 0),
        "properties": [
          {
            "value": option.value,
            "name": option.name,
            "property": {
              "id": option.property.id,
              "name": option.property.name,
            },
          }
          for option_eid in purchase.properties.get(str(product_id), [])
          if (option := options_by_eid.get(option_eid)) is not None and option.property is not None
        ],
      }
      for product_id in purchase.product_ids
      if (product := products_by_id.get(product_id)) is not None
    ],
    "quantity": purchase.quantity,
    "contact_info": purchase.contact_info,
    "final_price": purchase.final_price,
    "payment_method": purchase.payment_method,
    "payment_status": purchase.payment_status.value,
    "payment": _serialize_payment(payments_by_id.get(purchase.payment_id) if purchase.payment_id is not None else None),
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


@router.post("/", response_model=PurchaseResponse, status_code=200)
async def create_purchase(payload: PurchaseCreateRequest, session: AsyncSession = Depends(get_db)) -> dict:
  product_ids = [item.id for item in payload.items]
  products = await _get_products_or_404(session, product_ids)
  products_by_id = {product.id: product for product in products}
  properties_by_product: dict[int, list[str]] = {}
  quantities_by_product: dict[int, int] = {}
  for item in payload.items:
    properties_by_product.setdefault(item.id, []).extend(item.properties)
    quantities_by_product[item.id] = quantities_by_product.get(item.id, 0) + item.quantity.value

  contact_info = _contact_info(payload)
  purchase = Purchase(
    product_ids=product_ids,
    properties=_resolve_properties_by_product(products_by_id, properties_by_product),
    product_quantities=_normalize_quantities_by_product(quantities_by_product),
    quantity=sum(item.quantity.value for item in payload.items),
    contact_info=contact_info,
    final_price=payload.price,
    payment_method=payload.payment,
  )
  session.add(purchase)
  await session.flush()

  if payload.payment == "card":
    idempotency_key = str(uuid.uuid4())
    base_return_url = settings.YOOKASSA_RETURN_URL
    if not base_return_url:
      raise JSRError(status=500, message="YooKassa return URL is not configured")

    return_url = build_purchase_return_url(base_return_url, purchase.uuid)
    payment = Payment(
      idempotency_key=idempotency_key,
      amount_value=f"{payload.price:.2f}",
      return_url=return_url,
      description=f"Purchase {payload.name}",
    )
    session.add(payment)
    await session.flush()
    purchase.payment_id = payment.id

    payment_payload = build_yookassa_payment_payload(
      price=payload.price,
      description=f"Purchase #{purchase.id}",
      return_url=return_url,
      metadata={
        "purchase_id": str(purchase.id),
        "purchase_uuid": purchase.uuid,
        "payment_id": str(payment.id),
      },
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
      purchase.payment_status = PurchasePaymentStatus.FAILED
      await session.commit()
      raise

    payment.external_payment_id = provider_payment.get("id")
    payment.status = provider_payment.get("status", ProviderPaymentStatus.PENDING.value)
    payment.paid = bool(provider_payment.get("paid", False))
    payment.confirmation_url = (provider_payment.get("confirmation") or {}).get("confirmation_url")
    payment.response_payload = provider_payment
    purchase.payment_status = (
      PurchasePaymentStatus.PAID
      if payment.status == ProviderPaymentStatus.SUCCEEDED.value
      else PurchasePaymentStatus.FAILED if payment.status in {ProviderPaymentStatus.CANCELED.value, ProviderPaymentStatus.FAILED.value}
      else PurchasePaymentStatus.PENDING
    )

  await session.commit()
  await session.refresh(purchase)
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


@router.get("/{purchase_id}", response_model=PurchaseResponse, status_code=200)
async def get_purchase(purchase_id: int, session: AsyncSession = Depends(get_db)) -> dict:
  purchase = await _get_purchase_or_404(session, purchase_id)
  return await _serialize_purchase_with_refs(session, purchase)


@router.get("/by-uuid/{purchase_uuid}", response_model=PurchaseTrackingResponse, status_code=200)
async def get_purchase_by_uuid(purchase_uuid: str, session: AsyncSession = Depends(get_db)) -> dict:
  purchase = await _get_purchase_by_uuid_or_404(session, purchase_uuid)
  payment = await Payment.first(session, id=purchase.payment_id) if purchase.payment_id is not None else None
  if payment is not None:
    payment = await refresh_payment_state(session, payment, purchase)
  return _serialize_purchase_tracking(payment, purchase)


@router.patch("/{purchase_id}", response_model=PurchaseResponse, status_code=200)
async def update_purchase(
  purchase_id: int,
  payload: PurchasePatchRequest,
  session: AsyncSession = Depends(get_db),
) -> dict:
  purchase = await _get_purchase_or_404(session, purchase_id)
  updates = payload.model_dump(exclude_unset=True)

  product_ids = updates.get("product_ids", purchase.product_ids)
  products = await _get_products_or_404(session, product_ids)
  products_by_id = {product.id: product for product in products}

  if "product_ids" in updates and updates["product_ids"] is not None:
    purchase.product_ids = product_ids
  if "properties" in updates and updates["properties"] is not None:
    purchase.properties = _resolve_properties_by_product(products_by_id, updates["properties"])
  if "product_quantities" in updates and updates["product_quantities"] is not None:
    purchase.product_quantities = _normalize_quantities_by_product(updates["product_quantities"])
  if "quantity" in updates and updates["quantity"] is not None:
    purchase.quantity = updates["quantity"]
  if "contact_info" in updates and updates["contact_info"] is not None:
    purchase.contact_info = updates["contact_info"]
  if "final_price" in updates:
    purchase.final_price = updates["final_price"]
  if "payment_method" in updates and updates["payment_method"] is not None:
    purchase.payment_method = updates["payment_method"]
  if "payment_status" in updates and updates["payment_status"] is not None:
    purchase.payment_status = updates["payment_status"]
  if "status" in updates and updates["status"] is not None:
    purchase.status = updates["status"]

  await session.commit()
  await session.refresh(purchase)
  return await _serialize_purchase_with_refs(session, purchase)


@router.delete("/{purchase_id}", status_code=200)
async def delete_purchase(purchase_id: int, session: AsyncSession = Depends(get_db)) -> dict[str, bool]:
  purchase = await _get_purchase_or_404(session, purchase_id)
  await purchase.delete(session)
  return {"processed": True}
