import re
from collections import defaultdict
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.database import get_db
from src.exceptions import JSRError
from src.models import Product, ProductAttribute
from src.schemas.stock import StockItem, StockOptionsResponse, StockResponse


router = APIRouter(prefix="/api/stock", tags=["stock"])

SIZE_PROPERTY_ID = 2
STOCK_PAGE_LIMIT = 9
_NATURAL_SORT_PATTERN = re.compile(r"(\d+)")
_PAGINATION_QUERY_KEYS = {"page", "page_index"}


def _natural_sort_key(value: str | None) -> tuple:
  text = (value or "").strip().lower()
  parts = _NATURAL_SORT_PATTERN.split(text)
  return tuple(int(part) if part.isdigit() else part for part in parts)


def _serialize_category(product: Product) -> dict | None:
  category = product.category
  if category is None:
    return None
  return {
    "id": category.id,
    "name": category.name,
    "index": category.index,
  }


def _serialize_image(image) -> dict:
  return {
    "id": image.id,
    "eid": image.eid,
    "path": image.path,
    "sort_order": image.sort_order,
    "is_primary": image.is_primary,
  }


def _serialize_product_images(product: Product) -> list[dict]:
  return [
    _serialize_image(image)
    for image in sorted(product.images, key=lambda item: (item.sort_order, item.id))
  ]


def _add_stock_item_images(item: dict, product: Product) -> None:
  existing_image_ids = {image["id"] for image in item["images"]}
  for image in _serialize_product_images(product):
    if image["id"] in existing_image_ids:
      continue
    item["images"].append(image)
    existing_image_ids.add(image["id"])


def _serialize_non_size_options(product: Product) -> list[dict]:
  options: list[dict] = []
  for attribute in sorted(product.attributes, key=lambda item: (item.property.index, item.id)):
    option = attribute.option
    if attribute.property_id == SIZE_PROPERTY_ID or option is None:
      continue
    options.append(
      {
        "id": option.id,
        "value": option.value,
        "name": option.name,
      }
    )
  return options


def _size_variant(product: Product) -> dict | None:
  for attribute in sorted(product.attributes, key=lambda item: (item.property_id, item.id)):
    if attribute.property_id != SIZE_PROPERTY_ID or attribute.option is None:
      continue
    return {
      attribute.option.id: {
        "value": attribute.option.value,
        "name": attribute.option.name,
      },
    }
  return None


def _variant_sort_id(variant: dict | None) -> int | None:
  if variant is None:
    return None
  return next(iter(variant))


def _stock_group_key(product: Product) -> tuple:
  category = product.category
  option_key = tuple(
    (option["id"], option["value"], option["name"] or "")
    for option in _serialize_non_size_options(product)
  )
  return (
    category.id if category else None,
    product.name,
    product.primary_image or "",
    option_key,
  )


def _stock_item_sort_key(item: dict) -> tuple:
  category = item["category"]
  option_key = tuple(
    _natural_sort_key(option["name"] or option["value"])
    for option in item["options"]
  )
  return (
    1 if category is None else 0,
    0 if category is None else category["index"],
    _natural_sort_key(item["name"]),
    option_key,
  )


def _serialize_stock_offer(product: Product, variant: dict | None, offer) -> dict:
  return {
    "id": offer.id,
    "eid": offer.eid,
    "product_id": product.id,
    "product_eid": product.eid,
    "sku": product.sku,
    "code": product.code,
    "name": product.name,
    "description": product.description,
    "primary_image": product.primary_image,
    "product_is_active": product.is_active,
    "quantity": float(offer.quantity),
    "unit": offer.unit,
    "coefficient": float(offer.coefficient),
    "is_active": offer.is_active,
    "amount": float(offer.amount),
    "currency": offer.currency,
    "variant": variant,
  }


def _group_products(products: list[Product]) -> dict[tuple, dict]:
  grouped_items: dict[tuple, dict] = {}

  for product in products:
    active_offers = [offer for offer in product.offers if offer.is_active]
    if not active_offers:
      continue

    group_key = _stock_group_key(product)
    item = grouped_items.get(group_key)
    if item is None:
      item = {
        "name": product.name,
        "primary_image": product.primary_image,
        "images": [],
        "category": _serialize_category(product),
        "options": _serialize_non_size_options(product),
        "offers": [],
      }
      grouped_items[group_key] = item

    _add_stock_item_images(item, product)
    variant = _size_variant(product)
    for offer in active_offers:
      item["offers"].append(_serialize_stock_offer(product, variant, offer))

  for item in grouped_items.values():
    item["offers"].sort(
      key=lambda offer: (
        (offer["variant"] is None),
        _variant_sort_id(offer["variant"]) or 0,
        offer["product_id"],
      )
    )

  return grouped_items


def _serialize_stock_items(products: list[Product]) -> list[dict]:
  items = list(_group_products(products).values())
  items.sort(key=_stock_item_sort_key)
  return items


def _paginate_stock_items(items: list[dict], page_index: int) -> tuple[list[dict], bool]:
  start = page_index * STOCK_PAGE_LIMIT
  end = start + STOCK_PAGE_LIMIT + 1
  page_items = items[start:end]
  has_next_page = len(page_items) > STOCK_PAGE_LIMIT
  return page_items[:STOCK_PAGE_LIMIT], has_next_page


def _serialize_filters(products: list[Product]) -> dict[str, list[dict[str, str | None]]] | None:
  grouped_filters: dict[str, dict[int, tuple[str, str | None]]] = {}

  for product in products:
    if not any(offer.is_active for offer in product.offers):
      continue

    for attribute in sorted(product.attributes, key=lambda item: (item.property.index, item.id)):
      option = attribute.option
      if option is None:
        continue

      property_index = str(attribute.property.index)
      property_filters = grouped_filters.setdefault(property_index, {})
      property_filters[option.id] = (option.value, option.name)

  if not grouped_filters:
    return None

  return {
    property_id: [
      {value: name}
      for _, value, name in sorted(
        ((option_id, option_value, option_name) for option_id, (option_value, option_name) in options.items()),
        key=lambda item: (_natural_sort_key(item[2] or item[1]), item[0]),
      )
    ]
    for property_id, options in sorted(grouped_filters.items(), key=lambda item: int(item[0]))
  }


def _parse_stock_filters(request: Request) -> dict[int, set[str]]:
  filters: dict[int, set[str]] = defaultdict(set)
  raw_query_string = request.scope.get("query_string", b"").decode("utf-8")

  for query_part in raw_query_string.split("&"):
    if not query_part:
      continue

    raw_key, _, raw_value = query_part.partition("=")
    key = unquote(raw_key)
    if key in _PAGINATION_QUERY_KEYS:
      continue
    try:
      property_index = int(key)
    except ValueError as exc:
      raise JSRError("bad_request", message=f"Invalid stock filter key: {key}") from exc

    for raw_item in raw_value.split(","):
      normalized_value = unquote(raw_item).strip()
      if normalized_value:
        filters[property_index].add(normalized_value)

  return dict(filters)


def _product_matches_filters(product: Product, filters: dict[int, set[str]]) -> bool:
  if not filters:
    return True

  for filter_id, allowed_values in filters.items():
    if not any(
      attribute.option is not None
      and (attribute.property.index == filter_id or attribute.option.id == filter_id)
      and attribute.option.value in allowed_values
      for attribute in product.attributes
    ):
      return False

  return True


def _stock_product_query():
  return (
    select(Product)
    .options(selectinload(Product.category))
    .options(selectinload(Product.images))
    .options(selectinload(Product.offers))
    .options(selectinload(Product.attributes).selectinload(ProductAttribute.property))
    .options(selectinload(Product.attributes).selectinload(ProductAttribute.option))
  )


async def _fetch_products(session: AsyncSession) -> list[Product]:
  query = (
    _stock_product_query()
    .where(Product.is_active.is_(True))
    .order_by(Product.name.asc(), Product.id.asc())
  )
  result = await session.execute(query)
  return result.scalars().all()


async def _fetch_product(session: AsyncSession, product_id: int) -> Product | None:
  query = (
    _stock_product_query()
    .where(Product.id == product_id)
    .order_by(Product.id.asc())
  )
  result = await session.execute(query)
  return result.scalar_one_or_none()


async def _fetch_stock_group_products(session: AsyncSession, product: Product) -> list[Product]:
  query = (
    _stock_product_query()
    .where(Product.is_active.is_(True))
    .where(Product.name == product.name)
    .order_by(Product.name.asc(), Product.id.asc())
  )

  if product.category_id is None:
    query = query.where(Product.category_id.is_(None))
  else:
    query = query.where(Product.category_id == product.category_id)

  if product.primary_image is None:
    query = query.where(Product.primary_image.is_(None))
  else:
    query = query.where(Product.primary_image == product.primary_image)

  result = await session.execute(query)
  return result.scalars().all()


@router.get("/", response_model=StockResponse, status_code=200)
async def get_stock(
  request: Request,
  page_index: int = Query(default=0, ge=0),
  session: AsyncSession = Depends(get_db),
) -> dict[str, list[dict] | int | bool]:
  products = await _fetch_products(session)
  filters = _parse_stock_filters(request)
  products = [product for product in products if _product_matches_filters(product, filters)]
  items, has_next_page = _paginate_stock_items(_serialize_stock_items(products), page_index)
  return {
    "items": items,
    "page_index": page_index,
    "has_next_page": has_next_page,
  }


@router.options("/", response_model=StockOptionsResponse, response_model_exclude_none=True, status_code=200)
async def get_stock_options(session: AsyncSession = Depends(get_db)) -> dict:
  products = await _fetch_products(session)
  filters = _serialize_filters(products)
  if filters is None:
    return {}
  return {"filters": filters}


@router.get("/{product_id}", response_model=StockItem, status_code=200)
async def get_stock_product(product_id: int, session: AsyncSession = Depends(get_db)) -> dict:
  product = await _fetch_product(session, product_id)
  if product is None or not product.is_active:
    raise JSRError("not_found", message=f"Stock product not found: {product_id}")

  grouped_items = _group_products(await _fetch_stock_group_products(session, product))
  item = grouped_items.get(_stock_group_key(product))
  if item is None:
    raise JSRError("not_found", message=f"Stock product not found: {product_id}")

  return item
