from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.database import get_db
from src.models import Product, ProductAttribute, Setting
from src.models.settings import SettingsKeys
from src.schemas import ProductsResponse


router = APIRouter(prefix="/api/products", tags=["products"])

DEFAULT_PRODUCTS_PAGE_LIMIT = 20
MAX_PRODUCTS_PAGE_LIMIT = 100


def _serialize_offer(offer) -> dict:
  return {
    "id": offer.id,
    "eid": offer.eid,
    "quantity": float(offer.quantity),
    "unit": offer.unit,
    "coefficient": float(offer.coefficient),
    "is_active": offer.is_active,
    "amount": float(offer.amount),
    "currency": offer.currency,
  }


def _serialize_attribute(attribute: ProductAttribute) -> dict:
  option = attribute.option
  return {
    "id": attribute.id,
    "eid": attribute.eid,
    "property_id": attribute.property_id,
    "option_id": attribute.option_id,
    "property": {
      "id": attribute.property.id,
      "eid": attribute.property.eid,
      "name": attribute.property.name,
      "is_active": attribute.property.is_active,
    },
    "option": None if option is None else {
      "id": option.id,
      "eid": option.eid,
      "property_id": option.property_id,
      "value": option.value,
      "name": option.name,
      "icon": option.icon,
      "is_active": option.is_active,
    },
  }


def _serialize_product(product: Product) -> dict:
  return {
    "id": product.id,
    "eid": product.eid,
    "sku": product.sku,
    "code": product.code,
    "name": product.name,
    "description": product.description,
    "primary_image": product.primary_image,
    "is_active": product.is_active,
    "category": None if product.category is None else {
      "id": product.category.id,
      "eid": product.category.eid,
      "parent_id": product.category.parent_id,
      "name": product.category.name,
      "index": product.category.index,
      "icon": product.category.icon,
    },
    "images": [
      {
        "id": image.id,
        "eid": image.eid,
        "path": image.path,
        "sort_order": image.sort_order,
        "is_primary": image.is_primary,
      }
      for image in sorted(product.images, key=lambda item: (item.sort_order, item.id))
    ],
    "attributes": [
      _serialize_attribute(attribute)
      for attribute in sorted(product.attributes, key=lambda item: (item.property.name, item.id))
    ],
    "offers": [
      _serialize_offer(offer)
      for offer in sorted(product.offers, key=lambda item: item.id)
    ],
  }
async def _get_products_page_limit(session: AsyncSession) -> int:
  setting = await Setting.first(session, key=SettingsKeys.PRODUCTS_PAGE_LIMIT)
  raw_limit = int(setting.value) if setting else DEFAULT_PRODUCTS_PAGE_LIMIT

  if not isinstance(raw_limit, int) or isinstance(raw_limit, bool):
    return DEFAULT_PRODUCTS_PAGE_LIMIT

  return max(1, min(raw_limit, MAX_PRODUCTS_PAGE_LIMIT))


async def _fetch_products_page(session: AsyncSession, page_index: int, page_limit: int) -> tuple[list[Product], bool]:
  query = (
    select(Product)
    .options(selectinload(Product.category))
    .options(selectinload(Product.images))
    .options(selectinload(Product.offers))
    .options(selectinload(Product.attributes).selectinload(ProductAttribute.property))
    .options(selectinload(Product.attributes).selectinload(ProductAttribute.option))
    .order_by(Product.name.asc(), Product.id.asc())
    .offset(page_index * page_limit)
    .limit(page_limit + 1)
  )
  result = await session.execute(query)
  products = result.scalars().all()
  has_next_page = len(products) > page_limit
  return products[:page_limit], has_next_page
@router.get("/", response_model=ProductsResponse, status_code=200)
async def get_products(
  page_index: int = Query(default=0, ge=0),
  session: AsyncSession = Depends(get_db),
) -> dict[str, list[dict] | int | bool]:
  page_limit = await _get_products_page_limit(session)
  products, has_next_page = await _fetch_products_page(session, page_index, page_limit)
  return {
    "items": [_serialize_product(product) for product in products],
    "page_index": page_index,
    "has_next_page": has_next_page,
  }
