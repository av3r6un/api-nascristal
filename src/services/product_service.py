from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.config import settings
from src.core.change_logging import record_change
from src.models import (
  Attribute,
  AttributeOption,
  Category,
  Offer,
  Product,
  ProductAttribute,
  ProductVariant,
)
from src.models.settings import SettingsKeys
from src.exceptions import JSRError

from .server_settings import ServerSettings


DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100
STOCK_ATTRIBUTE_NAMES = {
  "fixation": "Фиксация",
  "cuts": "Грани",
  "size": "Размер",
  "color": "Цвет",
  "form": "Форма",
}


class ProductService:
  server_settings = ServerSettings

  def __init__(self, session: AsyncSession) -> None:
    self.session = session

  @classmethod
  async def get_stock(
    cls,
    session: AsyncSession,
    page: int,
    page_size: int | None = None,
    **filters,
  ) -> dict[str, Any]:
    return await cls(session)._get_stock(page, page_size=page_size, **filters)

  @classmethod
  async def get_stock_availability(
    cls,
    session: AsyncSession,
    **filters,
  ) -> dict[str, Any]:
    return await cls(session)._get_stock_availability(**filters)

  @classmethod
  async def get_products(
    cls,
    session: AsyncSession,
    page: int,
    fetch_all: bool = False,
    page_size: int | None = None,
    search: str | None = None,
    sort_by: str | None = None,
    sort_direction: str = "asc",
    **filters,
  ) -> dict[str, Any]:
    return await cls(session)._get_products(
      page,
      fetch_all=fetch_all,
      page_size=page_size,
      search=search,
      sort_by=sort_by,
      sort_direction=sort_direction,
      **filters,
    )

  @classmethod
  async def get_product_stats(cls, session: AsyncSession) -> dict[str, int | float]:
    return await cls(session)._get_product_stats()
  
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

  async def _get_products(
    self,
    page: int,
    fetch_all: bool = False,
    page_size: int | None = None,
    search: str | None = None,
    sort_by: str | None = None,
    sort_direction: str = "asc",
    **filters,
  ) -> dict[str, Any]:
    resolved_page_size = self._pagination(page, page_size)
    limit = None if fetch_all else resolved_page_size
    conditions = []
    if "archived" in filters:
      conditions.append(Product.archived.is_(bool(filters["archived"])))
    conditions.extend(self._product_search_conditions(search))

    count_query = select(func.count(Product.id)).where(*conditions)
    total_items = int(await self.session.scalar(count_query) or 0)
    total_pages = max(1, (total_items + resolved_page_size - 1) // resolved_page_size)

    query = (
      select(Product)
      .where(*conditions)
      .options(
        selectinload(Product.category),
        selectinload(Product.variants)
          .selectinload(ProductVariant.attributes)
          .selectinload(ProductAttribute.option)
          .selectinload(AttributeOption.attribute),
        selectinload(Product.variants).selectinload(ProductVariant.offer),
      )
    )
    query = self._apply_product_sort(query, sort_by, sort_direction)
    if limit is not None:
      query = query.offset(page * limit).limit(limit + 1)
    products = (await self.session.execute(query)).scalars().all()
    return self._response(
      products,
      page,
      limit,
      public=False,
      page_size=resolved_page_size,
      total_items=total_items,
      total_pages=total_pages,
    )

  async def _get_product_stats(self) -> dict[str, int | float]:
    products_count = int(await self.session.scalar(select(func.count(Product.id))) or 0)
    variants_count = float(await self.session.scalar(select(func.coalesce(func.sum(Offer.quantity), 0.0))) or 0)
    return {"products_count": products_count, "variants_count": variants_count}

  @staticmethod
  def _product_search_conditions(search: str | None) -> list[Any]:
    terms = [term for term in (search or "").lower().split() if term]
    conditions = []
    for term in terms:
      pattern = f"%{term}%"
      option_match = or_(
        func.lower(AttributeOption.value).like(pattern),
        func.lower(AttributeOption.label).like(pattern),
      )
      variant_match = or_(
        func.lower(ProductVariant.name).like(pattern),
        func.lower(ProductVariant.sku).like(pattern),
        func.lower(ProductVariant.code).like(pattern),
        func.lower(ProductVariant.external_code).like(pattern),
        ProductVariant.attributes.any(ProductAttribute.option.has(option_match)),
      )
      conditions.append(or_(
        func.lower(Product.name).like(pattern),
        func.lower(Product.sku).like(pattern),
        func.lower(Product.code).like(pattern),
        func.lower(Product.external_code).like(pattern),
        func.lower(Product.description).like(pattern),
        Product.variants.any(variant_match),
      ))
    return conditions

  @staticmethod
  def _apply_product_sort(query, sort_by: str | None, sort_direction: str):
    direction = "desc" if sort_direction == "desc" else "asc"
    if sort_by == "category":
      query = query.join(Product.category)
      expression = func.lower(Category.name)
    elif sort_by == "price":
      expression = (
        select(func.min(Offer.amount))
        .join(ProductVariant, ProductVariant.id == Offer.variant_id)
        .where(ProductVariant.product_id == Product.id)
        .correlate(Product)
        .scalar_subquery()
      )
    elif sort_by == "amount":
      expression = (
        select(func.coalesce(func.sum(Offer.quantity), 0.0))
        .join(ProductVariant, ProductVariant.id == Offer.variant_id)
        .where(ProductVariant.product_id == Product.id)
        .correlate(Product)
        .scalar_subquery()
      )
    elif sort_by == "status":
      expression = Product.archived
    elif sort_by == "name":
      expression = func.lower(Product.name)
    else:
      return query.order_by(Product.archived, Product.name, Product.id)
    ordered_expression = expression.desc() if direction == "desc" else expression.asc()
    return query.order_by(ordered_expression, Product.id)
  
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

  async def _get_stock(self, page: int, page_size: int | None = None, **filters) -> dict[str, Any]:
    limit = self._pagination(page, page_size)
    normalized_filters = self._normalize_stock_filters(filters)
    variant_condition = self._stock_variant_condition(normalized_filters)

    query = (
      select(Product)
      .where(
        Product.archived.is_(False),
        Product.variants.any(variant_condition),
      )
      .order_by(Product.name, Product.id)
      .offset(page * limit)
      .limit(limit + 1)
      .options(
        selectinload(Product.category),
        selectinload(Product.variants.and_(variant_condition))
          .selectinload(ProductVariant.attributes)
          .selectinload(ProductAttribute.option)
          .selectinload(AttributeOption.attribute),
        selectinload(Product.variants.and_(variant_condition))
          .selectinload(ProductVariant.offer),
      )
      .execution_options(populate_existing=True)
    )
    categories = normalized_filters.get("category", [])
    if categories:
      query = query.where(Product.category_id.in_(categories))

    products = (await self.session.execute(query)).scalars().all()
    return self._response(products, page, limit, public=True, page_size=limit)

  async def _get_stock_availability(self, **filters) -> dict[str, Any]:
    normalized_filters = self._normalize_stock_filters(filters)
    available: dict[str, list[str]] = {}

    for filter_name in ("category", *STOCK_ATTRIBUTE_NAMES):
      excluded = {filter_name}
      if filter_name == "category":
        excluded.update({"cuts", "form"})
      variant_condition = self._stock_variant_condition(normalized_filters, excluded)
      product_conditions = [
        Product.archived.is_(False),
        ProductVariant.archived.is_(False),
        variant_condition,
      ]
      categories = normalized_filters.get("category", [])
      if categories and "category" not in excluded:
        product_conditions.append(Product.category_id.in_(categories))

      if filter_name == "category":
        query = (
          select(Product.category_id)
          .join(ProductVariant, ProductVariant.product_id == Product.id)
          .where(*product_conditions)
          .distinct()
          .order_by(Product.category_id)
        )
        available[filter_name] = [str(value) for value in (await self.session.scalars(query)).all()]
        continue

      attribute_name = STOCK_ATTRIBUTE_NAMES[filter_name]
      query = (
        select(AttributeOption.value)
        .join(ProductAttribute, ProductAttribute.option_id == AttributeOption.id)
        .join(ProductVariant, ProductVariant.id == ProductAttribute.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .join(Attribute, Attribute.id == AttributeOption.attribute_id)
        .where(Attribute.name == attribute_name, *product_conditions)
        .distinct()
        .order_by(AttributeOption.value)
      )
      available[filter_name] = list((await self.session.scalars(query)).all())

    k9_condition = self._attribute_condition("fixation", ["k9"])
    k9_categories_query = (
      select(Product.category_id)
      .join(ProductVariant, ProductVariant.product_id == Product.id)
      .where(
        Product.archived.is_(False),
        ProductVariant.archived.is_(False),
        ProductVariant.offer.has(Offer.is_active.is_(True)),
        k9_condition,
      )
      .distinct()
      .order_by(Product.category_id)
    )
    k9_category_ids = [str(value) for value in (await self.session.scalars(k9_categories_query)).all()]
    return {"available": available, "k9_category_ids": k9_category_ids}

  @staticmethod
  def _normalize_filter_values(value: Any) -> list[str]:
    values = value if isinstance(value, (list, tuple, set)) else [value]
    normalized: list[str] = []
    for item in values:
      if item is None:
        continue
      normalized.extend(part.strip() for part in str(item).split(",") if part.strip())
    return list(dict.fromkeys(normalized))

  def _normalize_stock_filters(self, filters: dict[str, Any]) -> dict[str, list[Any]]:
    normalized: dict[str, list[Any]] = {}
    for name in ("category", *STOCK_ATTRIBUTE_NAMES):
      values = self._normalize_filter_values(filters.get(name))
      if name == "category":
        parsed_values = [int(value) for value in values if value.isdigit() and int(value) > 0]
        values = parsed_values or ([-1] if values else [])
      elif name == "fixation":
        values = [value.lower() for value in values]
      if values:
        normalized[name] = values
    return normalized

  @staticmethod
  def _attribute_condition(filter_name: str, values: list[Any]):
    attribute_name = STOCK_ATTRIBUTE_NAMES[filter_name]
    value_condition = (
      func.lower(AttributeOption.value).in_(values)
      if filter_name == "fixation"
      else AttributeOption.value.in_(values)
    )
    return ProductVariant.attributes.any(
      ProductAttribute.option.has(
        and_(
          AttributeOption.attribute.has(Attribute.name == attribute_name),
          value_condition,
        )
      )
    )

  def _stock_variant_condition(
    self,
    filters: dict[str, list[Any]],
    excluded: set[str] | None = None,
  ):
    excluded = excluded or set()
    conditions = [
      ProductVariant.archived.is_(False),
      ProductVariant.offer.has(Offer.is_active.is_(True)),
    ]
    for filter_name in STOCK_ATTRIBUTE_NAMES:
      if filter_name in excluded or not filters.get(filter_name):
        continue
      conditions.append(self._attribute_condition(filter_name, filters[filter_name]))
    return and_(*conditions)
  
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
    total_items: int | None = None,
    total_pages: int | None = None,
  ) -> dict[str, Any]:
    page_products = products if limit is None else products[:limit]
    items = [item for product in page_products if (item := self._serialize(product, public)) is not None]
    response = {
      "items": items,
      "page_index": page,
      "page_size": page_size or limit or self._page_limit(),
      "has_next_page": limit is not None and len(products) > limit,
    }
    if total_items is not None:
      response["total_items"] = total_items
    if total_pages is not None:
      response["total_pages"] = total_pages
    return response

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

  def _pagination(self, page: int, page_size: int | None = None) -> int:
    if page < 0:
      raise ValueError("Page must be greater than or equal to zero")
    if page_size is None:
      return self._page_limit()
    return max(1, min(page_size, MAX_PAGE_LIMIT))
