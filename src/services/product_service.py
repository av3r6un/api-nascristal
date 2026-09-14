from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.change_logging import record_change
from src.models import Product, Attribute, AttributeOption, Category
from src.models.settings import SettingsKeys
from src.exceptions import JSRError

from .server_settings import ServerSettings


DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100


class ProductService:
  server_settings = ServerSettings

  def __init__(self, session: AsyncSession) -> None:
    self.session = session

  @classmethod
  async def get_stock(
    cls,
    session: AsyncSession,
    page: int,
    fetch_all: bool = False,
    **filters,
  ) -> dict[str, Any]:
    return await cls(session)._get_stock(page, fetch_all=fetch_all, **filters)

  @classmethod
  async def get_products(
    cls,
    session: AsyncSession,
    page: int,
    fetch_all: bool = False,
    **filters,
  ) -> dict[str, Any]:
    return await cls(session)._get_products(page, fetch_all=fetch_all, **filters)
  
  @classmethod
  async def get_product(cls, session: AsyncSession, id) -> dict[str, Any]:
    return await cls(session)._get_product(id)
  
  @classmethod
  async def get_attributes(cls, session: AsyncSession, **kwargs) -> dict[str, Any]:
    return await cls(session)._get_attrs(**kwargs)

  @classmethod
  async def patch_attribute_options(cls, session: AsyncSession, items, actor_uid: str | None = None) -> dict[str, Any]:
    service = cls(session)
    ids = [item.id for item in items]
    options = (await session.execute(select(AttributeOption).where(AttributeOption.id.in_(ids)))).scalars().all()
    options_by_id = {option.id: option for option in options}
    missing_ids = sorted(set(ids) - options_by_id.keys())
    if missing_ids:
      raise JSRError("not_found", message=f"Attribute options not found: {', '.join(map(str, missing_ids))}")
    for item in items:
      options_by_id[item.id].label = item.label
    await session.commit()
    await record_change(session, "attribute_options.updated", payload={"ids": ids}, actor_uid=actor_uid)
    return await service._get_attrs()

  async def _get_products(self, page: int, fetch_all: bool = False, **filters) -> dict[str, Any]:
    page_size = self._pagination(page)
    limit = None if fetch_all else page_size
    filters.pop("order_by", None)
    pagination = {} if limit is None else {
      "limit": limit + 1,
      "offset": page * limit,
    }
    products = await Product.all(
      self.session,
      relationships=["category", "variants.attributes.option.attribute", "variants.offer"],
      order_by=["archived", "name", "id"],
      **pagination,
      **filters,
    )
    return self._response(products, page, limit, public=False, page_size=page_size)
  
  async def _get_product(self, id: int) -> dict:
    product = await Product.first(
      self.session,
      id=id,
      relationships=["category", "variants.attributes.option.attribute", "variants.offer"],
    )
    if not product: raise JSRError('not_found', message=f'Product[{id}] is not found!')
    item = self._serialize(product, public=True)
    if item is None:
      raise JSRError('not_found', message=f'Product[{id}] is not available!')
    return item

  async def _get_stock(self, page: int, fetch_all: bool = False, **filters) -> dict[str, Any]:
    page_size = self._pagination(page)
    limit = None if fetch_all else page_size
    filters.pop("order_by", None)
    filters["archived"] = False
    pagination = {} if limit is None else {
      "limit": limit + 1,
      "offset": page * limit,
    }
    products = await Product.all(
      self.session,
      relationships=["category", "variants.attributes.option.attribute", "variants.offer"],
      order_by=["name", "id"],
      **pagination,
      **filters,
    )
    return self._response(products, page, limit, public=True, page_size=page_size)
  
  async def _get_attrs(self, **filters) -> dict[str, Any]:
    attributes = await Attribute.get_json(self.session, **filters)
    categories = await Category.get_json(self.session, **filters)
    return dict(attributes=attributes, categories=categories)

  def _response(
    self,
    products: list[Product],
    page: int,
    limit: int | None,
    public: bool,
    page_size: int | None = None,
  ) -> dict[str, Any]:
    page_products = products if limit is None else products[:limit]
    items = [item for product in page_products if (item := self._serialize(product, public)) is not None]
    return {
      "items": items,
      "page_index": page,
      "page_size": page_size or limit or self._page_limit(),
      "has_next_page": limit is not None and len(products) > limit,
    }

  def _serialize(self, product: Product, public: bool) -> dict[str, Any] | None:
    variants = sorted(
      product.variants,
      key=lambda variant: (variant.archived, variant.name.lower(), variant.id),
    )
    if public:
      variants = [
        variant
        for variant in variants
        if not variant.archived and variant.offer is not None and variant.offer.is_active
      ]
      if not variants:
        return None

    item = product.json
    item["variants"] = [
      variant.json | {
        "image_url": (
          f"{settings.S3_DOMAIN.rstrip('/')}/{variant.image_key.lstrip('/')}"
          if variant.image_key else None
        ),
      }
      for variant in variants
    ]
    item["variants_count"] = sum(v.offer.quantity for v in variants)
    first_variant_key = next(
      (variant.image_key for variant in variants if variant.image_key),
      None,
    )
    item["images"] = ([{
      "object_key": first_variant_key,
      "url": f"{settings.S3_DOMAIN.rstrip('/')}/{first_variant_key.lstrip('/')}",
      "primary": True,
    }] if first_variant_key else [])
    if public:
      item["min_price"] = min(variant.offer.amount for variant in variants)
    return item

  def _page_limit(self) -> int:
    value = self.server_settings.get(SettingsKeys.PRODUCTS_PAGE_LIMIT, DEFAULT_PAGE_LIMIT)
    if isinstance(value, bool):
      return DEFAULT_PAGE_LIMIT
    try:
      return max(1, min(int(value), MAX_PAGE_LIMIT))
    except (TypeError, ValueError):
      return DEFAULT_PAGE_LIMIT

  def _pagination(self, page: int) -> int:
    if page < 0:
      raise ValueError("Page must be greater than or equal to zero")
    return self._page_limit()
