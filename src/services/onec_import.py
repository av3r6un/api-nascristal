from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime as dt
import hashlib
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.onec_catalog import Category, Offer, OneCImportRuns, Product, ProductAttribute, ProductImage, Property, PropertyOption, uuid1_str
from src.services.commerce_ml_parser import CommerceMLParser


@dataclass(slots=True)
class OneCImportSummary:
  import_run_id: int
  categories: int
  properties: int
  property_options: int
  products: int
  product_images: int
  product_attributes: int
  offers: int


def _local_now_naive() -> dt:
  return dt.now().astimezone().replace(tzinfo=None)


def compute_catalog_md5(import_path: str | Path, offers_path: str | Path) -> str:
  digest = hashlib.md5()
  for path in sorted((Path(import_path), Path(offers_path)), key=lambda item: item.name.lower()):
    with path.open("rb") as file_handle:
      for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
        digest.update(chunk)
  return digest.hexdigest()


def parse_catalog(import_path: str | Path, offers_path: str | Path) -> dict:
  parser = CommerceMLParser(import_path, offers_path)
  parsed = parser.parse()
  if not isinstance(parsed, dict):
    raise RuntimeError("CommerceMLParser returned unexpected payload")
  return parsed


def _stringify_value(value) -> str:
  if value is None:
    return ""
  return str(value).strip()


def _as_float(value) -> float:
  if value is None:
    return 0.0
  return float(value)


async def _next_category_index(session: AsyncSession) -> int:
  return await Category.next_index(session)


async def create_import_run(
  session: AsyncSession,
  *,
  exchange_type: str,
  classifier_id: str | None,
  source_md5: str,
  status: str,
  started_at: dt | None = None,
  finished_at: dt | None = None,
) -> OneCImportRuns:
  run = OneCImportRuns(
    exchange_type=exchange_type,
    classifier_id=classifier_id,
    source_md5=source_md5,
    status=status,
    started_at=started_at or _local_now_naive(),
    finished_at=finished_at,
  )
  session.add(run)
  await session.commit()
  return run


async def import_catalog(
  session: AsyncSession,
  *,
  import_path: str | Path,
  offers_path: str | Path,
  exchange_type: str = "catalog",
  source_md5: str | None = None,
) -> OneCImportSummary:
  import_file = Path(import_path)
  offers_file = Path(offers_path)
  started_at = _local_now_naive()
  run = OneCImportRuns(
    exchange_type=exchange_type,
    classifier_id=None,
    source_md5=source_md5 or compute_catalog_md5(import_file, offers_file),
    status="processing",
    started_at=started_at,
  )
  session.add(run)
  await session.commit()
  run_id = run.id

  try:
    parsed = parse_catalog(import_file, offers_file)
    run = await session.get(OneCImportRuns, run_id)
    if run is None:
      raise RuntimeError("Import run was not persisted")
    run.classifier_id = parsed.get("classifier_id") or None

    categories = {
      item.eid: item
      for item in (await session.execute(select(Category))).scalars().all()
    }
    properties = {
      item.eid: item
      for item in (await session.execute(select(Property))).scalars().all()
    }
    options = {
      item.eid: item
      for item in (await session.execute(select(PropertyOption))).scalars().all()
    }
    products = {
      item.eid: item
      for item in (await session.execute(select(Product))).scalars().all()
    }
    offers = {
      item.eid: item
      for item in (await session.execute(select(Offer))).scalars().all()
    }

    property_id_to_eid = {item.id: item.eid for item in properties.values()}
    option_by_property_and_value = {
      (property_id_to_eid[item.property_id], item.value): item
      for item in options.values()
      if item.property_id in property_id_to_eid
    }

    next_category_index = await _next_category_index(session)
    seen_property_ids: set[str] = set()
    seen_option_ids: set[str] = set()
    seen_product_ids: set[str] = set()
    seen_offer_ids: set[str] = set()
    image_count = 0
    attribute_count = 0

    for item in parsed.get("categories", []):
      category = categories.get(item["id"])
      if category is None:
        category = Category(
          eid=item["id"],
          parent_id=None,
          name=item["name"],
          icon="diamond",
          index=next_category_index,
        )
        next_category_index += 1
        session.add(category)
        categories[category.eid] = category
      else:
        category.parent_id = None
        category.name = item["name"]
    await session.flush()

    property_parent_category_ids: dict[str, int] = {}
    for item in parsed.get("categories", []):
      category = categories.get(item["id"])
      if category is None:
        continue
      for property_id in item.get("property_ids", []):
        # `parent_category` is singular, so keep the first category seen for a property.
        if property_id and property_id not in property_parent_category_ids:
          property_parent_category_ids[property_id] = category.id

    for property_index, item in enumerate(parsed.get("properties", []), start=1):
      property_row = properties.get(item["id"])
      parent_category_id = property_parent_category_ids.get(item["id"])
      if property_row is None:
        property_row = Property(
          eid=item["id"],
          parent_category_id=parent_category_id,
          index=property_index,
          name=item["name"],
          is_active=True,
        )
        session.add(property_row)
        await session.flush()
        properties[property_row.eid] = property_row
        property_id_to_eid[property_row.id] = property_row.eid
      else:
        property_row.parent_category_id = parent_category_id
        property_row.index = property_index
        property_row.name = item["name"]
        property_row.is_active = True
      seen_property_ids.add(property_row.eid)

      for option in item.get("options", []):
        option_value = _stringify_value(option.get("value"))
        option_row = options.get(option["id"])
        if option_row is None:
          option_row = PropertyOption(
            eid=option["id"],
            property_id=property_row.id,
            value=option_value,
            is_active=True,
          )
          session.add(option_row)
          options[option_row.eid] = option_row
        else:
          option_row.property_id = property_row.id
          option_row.value = option_value
          option_row.is_active = True
        option_by_property_and_value[(property_row.eid, option_value)] = option_row
        seen_option_ids.add(option_row.eid)
    await session.flush()

    for item in parsed.get("products", []):
      product_eid = item["id"]
      product = products.get(product_eid)
      category = categories.get(item.get("category_id") or "")
      if product is None:
        product = Product(
          eid=product_eid,
          sku=item["sku"],
          code=item["code"],
          name=item["name"],
          description=item.get("description") or None,
          category_id=category.id if category else None,
          primary_image=item.get("image") or None,
          is_active=True,
          last_seen_import_run_id=run.id,
        )
        session.add(product)
        await session.flush()
        products[product.eid] = product
      else:
        product.sku = item["sku"]
        product.code = item["code"]
        product.name = item["name"]
        product.description = item.get("description") or None
        product.category_id = category.id if category else None
        product.primary_image = item.get("image") or None
        product.is_active = True
        product.last_seen_import_run_id = run.id
      seen_product_ids.add(product.eid)

      await session.execute(delete(ProductImage).where(ProductImage.product_id == product.id))
      await session.execute(delete(ProductAttribute).where(ProductAttribute.product_id == product.id))

      if product.primary_image:
        session.add(
          ProductImage(
            product_id=product.id,
            path=product.primary_image,
            sort_order=0,
            is_primary=True,
          )
        )
        image_count += 1

      product_attribute_option_ids: dict[str, int] = {}
      for attribute in item.get("attributes", []):
        property_id = attribute["property_id"]
        value = _stringify_value(attribute.get("value"))
        if not value:
          continue

        property_row = properties.get(property_id)
        if property_row is None:
          property_row = Property(
            eid=property_id,
            parent_category_id=property_parent_category_ids.get(property_id),
            index=0,
            name=property_id,
            is_active=True,
          )
          session.add(property_row)
          await session.flush()
          properties[property_id] = property_row
          property_id_to_eid[property_row.id] = property_row.eid
        else:
          property_row.parent_category_id = property_parent_category_ids.get(property_id)
        property_row.is_active = True
        seen_property_ids.add(property_row.eid)

        option_row = option_by_property_and_value.get((property_row.eid, value))
        if option_row is None:
          option_row = PropertyOption(
            eid=uuid1_str(),
            property_id=property_row.id,
            value=value,
            is_active=True,
          )
          session.add(option_row)
          await session.flush()
          options[option_row.eid] = option_row
          option_by_property_and_value[(property_row.eid, value)] = option_row
        else:
          option_row.is_active = True
        seen_option_ids.add(option_row.eid)
        product_attribute_option_ids[property_row.eid] = option_row.id

      for property_eid, option_id in product_attribute_option_ids.items():
        property_row = properties[property_eid]
        session.add(
          ProductAttribute(
            eid=uuid1_str(),
            product_id=product.id,
            property_id=property_row.id,
            option_id=option_id,
          )
        )
        attribute_count += 1

      offer_eid = product.eid
      product_price = item.get("price", {})
      offer = offers.get(offer_eid)
      if offer is None:
        offer = Offer(
          eid=offer_eid,
          product_id=product.id,
          quantity=_as_float(item.get("quantity")),
          unit=_stringify_value(product_price.get("unit")) or None,
          coefficient=_as_float(product_price.get("coefficient") or 1),
          is_active=True,
          amount=_as_float(product_price.get("amount")),
          currency=_stringify_value(product_price.get("currency")) or None,
        )
        session.add(offer)
        offers[offer.eid] = offer
      else:
        offer.product_id = product.id
        offer.quantity = _as_float(item.get("quantity"))
        offer.unit = _stringify_value(product_price.get("unit")) or None
        offer.coefficient = _as_float(product_price.get("coefficient") or 1)
        offer.is_active = True
        offer.amount = _as_float(product_price.get("amount"))
        offer.currency = _stringify_value(product_price.get("currency")) or None
      seen_offer_ids.add(offer.eid)

    for property_row in properties.values():
      if property_row.eid not in seen_property_ids:
        property_row.is_active = False

    for option_row in options.values():
      if option_row.eid not in seen_option_ids:
        option_row.is_active = False

    for product in products.values():
      if product.eid not in seen_product_ids:
        product.is_active = False

    for offer in offers.values():
      if offer.eid not in seen_offer_ids:
        offer.is_active = False

    run.status = "success"
    run.finished_at = _local_now_naive()
    await session.commit()

    return OneCImportSummary(
      import_run_id=run.id,
      categories=len(parsed.get("categories", [])),
      properties=len(seen_property_ids),
      property_options=len(seen_option_ids),
      products=len(seen_product_ids),
      product_images=image_count,
      product_attributes=attribute_count,
      offers=len(seen_offer_ids),
    )
  except Exception:
    await session.rollback()
    run = await session.get(OneCImportRuns, run_id)
    if run is not None:
      run.status = "failed"
      run.finished_at = _local_now_naive()
      await session.commit()
    raise
