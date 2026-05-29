from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.database import get_db
from src.exceptions import JSRError
from src.models import Product, ProductAttribute, PropertyOption, Purchase
from src.schemas.purchase import PurchaseCreateRequest, PurchasePatchRequest, PurchaseResponse, PurchasesResponse


router = APIRouter(prefix="/api/purchases", tags=["purchases"])


def _contact_info(payload: PurchaseCreateRequest) -> dict:
  return {
    "name": payload.name,
    "phone": payload.phone,
    "delivery": payload.delivery,
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


def _serialize_purchase(
  purchase: Purchase,
  products_by_id: dict[int, Product],
  options_by_eid: dict[str, PropertyOption],
) -> dict:
  return {
    "id": purchase.id,
    "uuid": purchase.uuid,
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
    "status": purchase.status.value,
    "created_ts": purchase.created_ts,
    "updated_ts": purchase.updated_ts,
  }


async def _serialize_purchase_with_refs(session: AsyncSession, purchase: Purchase) -> dict:
  products_by_id = await _load_product_map(session, purchase.product_ids)
  options_by_eid = await _load_property_option_map(session, _collect_property_eids(purchase.properties))
  return _serialize_purchase(purchase, products_by_id, options_by_eid)


async def _get_purchase_or_404(session: AsyncSession, purchase_id: int) -> Purchase:
  purchase = await Purchase.first(session, id=purchase_id)
  if not purchase:
    raise JSRError("not_found", message=f"Purchase not found: {purchase_id}")
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

  await session.commit()
  await session.refresh(purchase)
  return await _serialize_purchase_with_refs(session, purchase)


@router.get("/", response_model=PurchasesResponse, status_code=200)
async def get_purchases(session: AsyncSession = Depends(get_db)) -> dict[str, list[dict]]:
  result = await session.execute(
    select(Purchase)
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
  return {"items": [_serialize_purchase(purchase, products_by_id, options_by_eid) for purchase in purchases]}


@router.get("/{purchase_id}", response_model=PurchaseResponse, status_code=200)
async def get_purchase(purchase_id: int, session: AsyncSession = Depends(get_db)) -> dict:
  purchase = await _get_purchase_or_404(session, purchase_id)
  return await _serialize_purchase_with_refs(session, purchase)


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
