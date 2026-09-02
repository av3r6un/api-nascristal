from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
  Attribute,
  AttributeOption,
  Category,
  Offer,
  Product,
  ProductAttribute,
  ProductImage,
  ProductVariant,
)


class MoySkladImportError(ValueError):
  pass


class MoySkladImportService:
  def __init__(self, session: AsyncSession) -> None:
    self.session = session

  @classmethod
  async def import_product(
    cls,
    session: AsyncSession,
    product_data: Mapping[str, Any],
    variants_data: Sequence[Mapping[str, Any]],
  ) -> Product:
    products, skipped = await cls(session)._import_assortment(
      [product_data, *variants_data],
      archive_missing=False,
    )
    if skipped or not products:
      raise MoySkladImportError("Product must contain at least one variant")
    return products[0]

  @classmethod
  async def import_assortment(
    cls,
    session: AsyncSession,
    rows: Sequence[Mapping[str, Any]],
  ) -> tuple[list[Product], list[Mapping[str, Any]]]:
    return await cls(session)._import_assortment(rows, archive_missing=True)

  async def _import_assortment(
    self,
    rows: Sequence[Mapping[str, Any]],
    archive_missing: bool,
  ) -> tuple[list[Product], list[Mapping[str, Any]]]:
    product_rows = [row for row in rows if self._entity_type(row) == "product"]
    variants_by_product: dict[uuid.UUID, list[Mapping[str, Any]]] = {}
    for row in rows:
      if self._entity_type(row) == "variant":
        product_uuid = self._relation_uuid(row.get("product"), "variant.product")
        variants_by_product.setdefault(product_uuid, []).append(row)

    importable: list[tuple[Mapping[str, Any], list[Mapping[str, Any]]]] = []
    skipped: list[Mapping[str, Any]] = []
    for product_data in product_rows:
      product_uuid = self._uuid(product_data.get("id"), "product.id")
      variants = variants_by_product.pop(product_uuid, [])
      if variants:
        importable.append((product_data, variants))
      else:
        skipped.append(product_data)

    if variants_by_product:
      raise MoySkladImportError("Variants contain products missing from assortment")
    if not importable:
      if archive_missing:
        await self._archive_missing(set(), set())
      return [], skipped

    categories = await self._load_categories(importable)
    products = await self._load_products(importable, categories)
    variants = await self._load_variants(products)
    attributes = await self._load_attributes(variants)
    options = await self._load_attribute_options(variants, attributes)
    await self._sync_attributes(variants, attributes, options)
    await self._sync_offers(variants)
    await self._sync_images(products)
    if archive_missing:
      await self._archive_missing(
        {product.uuid for product, _ in products},
        {variant.uuid for variant, _ in variants},
      )
    await self.session.flush()
    return [product for product, _ in products], skipped

  async def _archive_missing(
    self,
    product_uuids: set[uuid.UUID],
    variant_uuids: set[uuid.UUID],
  ) -> None:
    missing_variant_ids = select(ProductVariant.id).where(
      ProductVariant.uuid.not_in(variant_uuids),
    )
    await self.session.execute(
      update(Product).where(Product.uuid.not_in(product_uuids)).values(archived=True),
    )
    await self.session.execute(
      update(Offer).where(Offer.variant_id.in_(missing_variant_ids)).values(is_active=False),
    )
    await self.session.execute(
      update(ProductVariant)
      .where(ProductVariant.uuid.not_in(variant_uuids))
      .values(archived=True),
    )

  async def _load_categories(
    self,
    importable: Sequence[tuple[Mapping[str, Any], list[Mapping[str, Any]]]],
  ) -> dict[str, Category]:
    names = {self._category_name(product) for product, _ in importable}
    existing = (
      await self.session.execute(
        select(Category).where(Category.name.in_(names)).order_by(Category.id),
      )
    ).scalars().all()
    categories: dict[str, Category] = {}
    for category in existing:
      categories.setdefault(category.name, category)
    for name in names - categories.keys():
      categories[name] = Category(name=name)
      self.session.add(categories[name])
    await self.session.flush()
    return categories

  async def _load_products(
    self,
    importable: Sequence[tuple[Mapping[str, Any], list[Mapping[str, Any]]]],
    categories: Mapping[str, Category],
  ) -> list[tuple[Product, list[Mapping[str, Any]]]]:
    product_uuids = {self._uuid(data.get("id"), "product.id") for data, _ in importable}
    existing = (
      await self.session.execute(select(Product).where(Product.uuid.in_(product_uuids)))
    ).scalars().all()
    products_by_uuid = {product.uuid: product for product in existing}
    products = []

    for data, variants in importable:
      product_uuid = self._uuid(data.get("id"), "product.id")
      product = products_by_uuid.get(product_uuid)
      if product is None:
        product = Product(uuid=product_uuid)
        self.session.add(product)
      product.category_id = categories[self._category_name(data)].id
      product.sku = self._optional_text(data.get("article"))
      product.name = self._text(data, "name")
      product.description = self._optional_text(data.get("description"))
      product.code = self._text(data, "code")
      product.external_code = self._text(data, "externalCode")
      product.server_updated = self._datetime(data.get("updated"))
      product.archived = bool(data.get("archived", False))
      products.append((product, variants))

    await self.session.flush()
    return products

  async def _load_variants(
    self,
    products: Sequence[tuple[Product, list[Mapping[str, Any]]]],
  ) -> list[tuple[ProductVariant, Mapping[str, Any]]]:
    rows = [row for _, variants in products for row in variants]
    variant_uuids = {self._uuid(row.get("id"), "variant.id") for row in rows}
    existing = (
      await self.session.execute(
        select(ProductVariant).where(ProductVariant.uuid.in_(variant_uuids)),
      )
    ).scalars().all()
    variants_by_uuid = {variant.uuid: variant for variant in existing}
    result = []

    for product, variants in products:
      for data in variants:
        variant_uuid = self._uuid(data.get("id"), "variant.id")
        variant = variants_by_uuid.get(variant_uuid)
        if variant is None:
          variant = ProductVariant(uuid=variant_uuid)
          self.session.add(variant)
        variant.product_id = product.id
        variant.name = self._text(data, "name")
        variant.code = self._text(data, "code")
        variant.external_code = self._text(data, "externalCode")
        variant.sku = self._optional_text(data.get("article")) or variant.code
        variant.archived = bool(data.get("archived", False))
        result.append((variant, data))

    await self.session.flush()
    return result

  async def _load_attributes(
    self,
    variants: Sequence[tuple[ProductVariant, Mapping[str, Any]]],
  ) -> dict[uuid.UUID, Attribute]:
    definitions = {
      self._uuid(item.get("id"), "characteristic.id"): self._text(item, "name")
      for _, data in variants
      for item in self._characteristics(data)
    }
    if not definitions:
      return {}

    existing = (
      await self.session.execute(
        select(Attribute).where(Attribute.uuid.in_(definitions)),
      )
    ).scalars().all()
    attributes = {attribute.uuid: attribute for attribute in existing}
    for attribute_uuid, name in definitions.items():
      attribute = attributes.get(attribute_uuid)
      if attribute is None:
        attribute = Attribute(uuid=attribute_uuid, name=name)
        attributes[attribute_uuid] = attribute
        self.session.add(attribute)
      else:
        attribute.name = name
    await self.session.flush()
    return attributes

  async def _load_attribute_options(
    self,
    variants: Sequence[tuple[ProductVariant, Mapping[str, Any]]],
    attributes: Mapping[uuid.UUID, Attribute],
  ) -> dict[tuple[int, str], AttributeOption]:
    attribute_ids = [attribute.id for attribute in attributes.values()]
    if not attribute_ids:
      return {}

    existing = (
      await self.session.execute(
        select(AttributeOption).where(AttributeOption.attribute_id.in_(attribute_ids)),
      )
    ).scalars().all()
    options = {(option.attribute_id, option.value): option for option in existing}

    for _, data in variants:
      for item in self._characteristics(data):
        attribute = attributes[self._uuid(item.get("id"), "characteristic.id")]
        value = self._text(item, "value")
        key = (attribute.id, value)
        if key not in options:
          option = AttributeOption(attribute_id=attribute.id, value=value)
          options[key] = option
          self.session.add(option)

    await self.session.flush()
    return options

  async def _sync_attributes(
    self,
    variants: Sequence[tuple[ProductVariant, Mapping[str, Any]]],
    attributes: Mapping[uuid.UUID, Attribute],
    options: Mapping[tuple[int, str], AttributeOption],
  ) -> None:
    variant_ids = [variant.id for variant, _ in variants]
    existing = (
      await self.session.execute(
        select(ProductAttribute).where(ProductAttribute.variant_id.in_(variant_ids)),
      )
    ).scalars().all()
    links = {(link.variant_id, link.option_id): link for link in existing}
    wanted: set[tuple[int, int]] = set()

    for variant, data in variants:
      seen: set[uuid.UUID] = set()
      for item in self._characteristics(data):
        attribute_uuid = self._uuid(item.get("id"), "characteristic.id")
        if attribute_uuid in seen:
          raise MoySkladImportError("Variant contains a duplicate characteristic")
        seen.add(attribute_uuid)
        attribute = attributes[attribute_uuid]
        option = options[(attribute.id, self._text(item, "value"))]
        key = (variant.id, option.id)
        link = links.get(key)
        if link is None:
          link = ProductAttribute(variant_id=variant.id, option_id=option.id)
          self.session.add(link)
        wanted.add(key)

    for key, link in links.items():
      if key not in wanted:
        await self.session.delete(link)

  async def _sync_offers(
    self,
    variants: Sequence[tuple[ProductVariant, Mapping[str, Any]]],
  ) -> None:
    variant_ids = [variant.id for variant, _ in variants]
    existing = (
      await self.session.execute(select(Offer).where(Offer.variant_id.in_(variant_ids)))
    ).scalars().all()
    offers = {offer.variant_id: offer for offer in existing}
    for variant, data in variants:
      offer = offers.get(variant.id)
      if offer is None:
        offer = Offer(variant_id=variant.id)
        self.session.add(offer)
      offer.amount = self._sale_price(data)
      offer.quantity = self._quantity(data.get("quantity", 0))
      offer.is_active = not variant.archived

  async def _sync_images(
    self,
    products: Sequence[tuple[Product, list[Mapping[str, Any]]]],
  ) -> None:
    product_ids = [product.id for product, _ in products]
    existing = (
      await self.session.execute(
        select(ProductImage).where(ProductImage.product_id.in_(product_ids)),
      )
    ).scalars().all()
    images = {(image.product_id, image.object_key): image for image in existing}
    for image in existing:
      image.is_primary = False

    for product, variants in products:
      for sort_order, object_key in enumerate(self._image_keys(variants)):
        image = images.get((product.id, object_key))
        if image is None:
          image = ProductImage(uuid=uuid.uuid4(), product_id=product.id, object_key=object_key)
          self.session.add(image)
        image.sort_order = sort_order
        image.is_primary = sort_order == 0

  def _characteristics(self, data: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    items = data.get("characteristics", [])
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
      raise MoySkladImportError("Variant characteristics must be an array")
    if not all(isinstance(item, Mapping) for item in items):
      raise MoySkladImportError("Variant characteristic must be an object")
    return [item for item in items if item.get("name") != "ID изображения"]

  def _image_keys(self, variants: Sequence[Mapping[str, Any]]) -> list[str]:
    keys = []
    for variant in variants:
      items = variant.get("characteristics", [])
      if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        continue
      for item in items:
        if isinstance(item, Mapping) and item.get("name") == "ID изображения":
          key = self._optional_text(item.get("value"))
          if key and key not in keys:
            keys.append(key)
    return keys

  def _sale_price(self, data: Mapping[str, Any]) -> Decimal:
    prices = data.get("salePrices")
    if not isinstance(prices, Sequence) or isinstance(prices, (str, bytes)) or not prices:
      raise MoySkladImportError("Variant has no salePrice")
    price = prices[0]
    if not isinstance(price, Mapping) or price.get("value") is None:
      raise MoySkladImportError("Variant has no salePrice value")
    try:
      return (Decimal(str(price["value"])) / Decimal("100")).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as exc:
      raise MoySkladImportError("Invalid salePrice value") from exc

  def _quantity(self, value: Any) -> int:
    try:
      quantity = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
      raise MoySkladImportError("Invalid quantity") from exc
    if quantity != quantity.to_integral_value():
      raise MoySkladImportError("Quantity must be an integer")
    return max(0, int(quantity))

  def _category_name(self, data: Mapping[str, Any]) -> str:
    name = self._text(data, "pathName").rsplit("/", 1)[-1].strip()
    if not name:
      raise MoySkladImportError("Invalid pathName")
    return name

  def _uuid(self, value: Any, field: str) -> uuid.UUID:
    try:
      return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
      raise MoySkladImportError(f"Invalid {field}") from exc

  def _relation_uuid(self, value: Any, field: str) -> uuid.UUID:
    if isinstance(value, Mapping):
      if value.get("id"):
        return self._uuid(value["id"], field)
      meta = value.get("meta")
      if isinstance(meta, Mapping) and meta.get("href"):
        return self._uuid(str(meta["href"]).rstrip("/").rsplit("/", 1)[-1], field)
    raise MoySkladImportError(f"Invalid {field}")

  def _datetime(self, value: Any) -> datetime:
    try:
      parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
      raise MoySkladImportError("Invalid updated") from exc
    if parsed.tzinfo is not None:
      return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed

  def _text(self, data: Mapping[str, Any], field: str) -> str:
    value = self._optional_text(data.get(field))
    if value is None:
      raise MoySkladImportError(f"Missing {field}")
    return value

  def _optional_text(self, value: Any) -> str | None:
    if value is None:
      return None
    value = str(value).strip()
    return value or None

  def _entity_type(self, data: Mapping[str, Any]) -> str | None:
    meta = data.get("meta")
    return str(meta.get("type")) if isinstance(meta, Mapping) and meta.get("type") else None
