from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends

from src.core.database import get_db
from src.exceptions import JSRError
from src.models import Category, CategoryTranslation, Color, Size
from src.schemas import (
  BatchUpdateResponse,
  CategoriesResponse,
  CategoryBatchUpdateRequest,
  CategoryRequest,
  CategoryResponse,
  CategorySaveResponse,
  ColorBatchUpdateRequest,
  ColorsResponse,
  ColorRequest,
  ColorResponse,
  ProcessResponse,
  SizeBatchUpdateRequest,
  SizesResponse,
  SizeRequest,
  SizeResponse,
  WarehouseSpecsResponse,
)

router = APIRouter(tags=["catalog"], prefix='/api')


def _validate_locale(locale: str) -> None:
  if locale not in {"ru", "en"}:
    raise JSRError("bad_request", message="Locale must be 'ru' or 'en'")


def _serialize_category(category: Category, translation: CategoryTranslation) -> dict:
  return {
    "uid": category.uid,
    "index": category.index,
    "icon": category.icon,
    "locale": translation.locale,
    "name": translation.name,
    "description": translation.description,
  }


def _ensure_unique_entries(values: list, entity_name: str) -> None:
  if len(values) != len(set(values)):
    raise JSRError("conflict", message=f"Duplicate {entity_name} entries in request")


async def _fetch_localized_categories(session: AsyncSession, locale: str) -> list[dict]:
  query = (
    select(Category, CategoryTranslation)
    .join(CategoryTranslation, CategoryTranslation.category_uid == Category.uid)
    .where(CategoryTranslation.locale == locale)
    .order_by(Category.index.asc(), Category.uid.asc())
  )
  result = await session.execute(query)
  return [_serialize_category(category, translation) for category, translation in result.all()]


@router.get("/categories/{locale}", response_model=CategoriesResponse)
async def get_categories(locale: str, session: AsyncSession = Depends(get_db)) -> dict[str, list[dict]]:
  _validate_locale(locale)
  return {"items": await _fetch_localized_categories(session, locale)}


@router.get("/category/{uid}/{locale}", response_model=CategoryResponse)
async def get_category(uid: str, locale: str, session: AsyncSession = Depends(get_db)) -> dict:
  _validate_locale(locale)

  query = (
    select(Category, CategoryTranslation)
    .join(CategoryTranslation, CategoryTranslation.category_uid == Category.uid)
    .where(Category.uid == uid)
    .where(CategoryTranslation.locale == locale)
  )
  result = await session.execute(query)
  row = result.first()
  if not row:
    raise JSRError("not_found")

  category, translation = row
  return _serialize_category(category, translation)


@router.post("/category", response_model=CategorySaveResponse, status_code=200)
async def save_category(payload: CategoryRequest, session: AsyncSession = Depends(get_db)) -> dict[str, bool | str]:
  _validate_locale(payload.locale)

  category = await Category.first(session, uid=payload.uid) if payload.uid else None
  if payload.uid and not category:
    raise JSRError("not_found")

  if not category:
    uid = await Category.create_uid(session)
    index = payload.index if payload.index is not None else await Category.next_index(session)
    category = Category(uid=uid, index=index, icon=payload.icon)
    await category.save(session)
  else:
    await category.edit(
      session,
      index=payload.index if payload.index is not None else category.index,
      icon=payload.icon,
    )

  translation = await CategoryTranslation.first(session, category_uid=category.uid, locale=payload.locale)
  if not translation:
    translation = CategoryTranslation(
      category_uid=category.uid,
      locale=payload.locale,
      name=payload.name,
      description=payload.description,
    )
    await translation.save(session)
  else:
    await translation.edit(session, name=payload.name, description=payload.description)

  return {"processed": True, "uid": category.uid}


@router.put("/categories", response_model=BatchUpdateResponse, status_code=200)
async def update_categories(payload: CategoryBatchUpdateRequest, session: AsyncSession = Depends(get_db)) -> dict[str, bool | int]:
  _ensure_unique_entries([(item.uid, item.locale) for item in payload.items], "category")

  category_base_updates: dict[str, tuple[int, str]] = {}
  for item in payload.items:
    _validate_locale(item.locale)

    if item.uid in category_base_updates and category_base_updates[item.uid] != (item.index, item.icon):
      raise JSRError("bad_request", message=f'Category "{item.uid}" has conflicting base fields in request')

    category = await Category.first(session, uid=item.uid)
    if not category:
      raise JSRError("not_found")

    translation = await CategoryTranslation.first(session, category_uid=item.uid, locale=item.locale)
    if not translation:
      raise JSRError("not_found")

    category_base_updates[item.uid] = (item.index, item.icon)

  for item in payload.items:
    category = await Category.first(session, uid=item.uid)
    translation = await CategoryTranslation.first(session, category_uid=item.uid, locale=item.locale)
    await category.edit(session, index=item.index, icon=item.icon)
    await translation.edit(session, name=item.name, description=item.description)

  return {"processed": True, "updated": len(payload.items)}


@router.delete("/category/{uid}", response_model=ProcessResponse, status_code=200)
async def delete_category(uid: str, session: AsyncSession = Depends(get_db)) -> dict[str, bool]:
  category = await Category.first(session, uid=uid)
  if not category:
    raise JSRError("not_found")

  await category.delete(session)
  return {"processed": True}


@router.get("/colors", response_model=ColorsResponse)
async def get_colors(session: AsyncSession = Depends(get_db)) -> dict[str, list[dict]]:
  colors = await Color.all(session)
  items = sorted((color.json for color in colors), key=lambda item: item["id"])
  return {"items": items}


@router.get("/color/{color_id}", response_model=ColorResponse)
async def get_color(color_id: int, session: AsyncSession = Depends(get_db)) -> dict:
  color = await Color.first(session, id=color_id)
  if not color:
    raise JSRError("not_found")
  return color.json


@router.post("/color", response_model=ColorResponse, status_code=200)
async def save_color(payload: ColorRequest, session: AsyncSession = Depends(get_db)) -> dict:
  if payload.id is None:
    existing = await Color.first(session, sku=payload.sku)
    if existing:
      raise JSRError("conflict", message=f'Color with sku "{payload.sku}" already exists')
    color = Color(**payload.model_dump(exclude={"id"}))
    await color.save(session)
    return color.json

  color = await Color.first(session, id=payload.id)
  if not color:
    raise JSRError("not_found")

  sku_owner = await Color.first(session, sku=payload.sku)
  if sku_owner and sku_owner.id != color.id:
    raise JSRError("conflict", message=f'Color with sku "{payload.sku}" already exists')

  await color.edit(session, sku=payload.sku, name=payload.name)
  return color.json


@router.put("/colors", response_model=BatchUpdateResponse, status_code=200)
async def update_colors(payload: ColorBatchUpdateRequest, session: AsyncSession = Depends(get_db)) -> dict[str, bool | int]:
  _ensure_unique_entries([item.id for item in payload.items], "color")
  _ensure_unique_entries([item.sku for item in payload.items], "color sku")

  for item in payload.items:
    color = await Color.first(session, id=item.id)
    if not color:
      raise JSRError("not_found")

    sku_owner = await Color.first(session, sku=item.sku)
    if sku_owner and sku_owner.id != item.id:
      raise JSRError("conflict", message=f'Color with sku "{item.sku}" already exists')

  for item in payload.items:
    color = await Color.first(session, id=item.id)
    await color.edit(session, sku=item.sku, name=item.name)

  return {"processed": True, "updated": len(payload.items)}


@router.delete("/color/{color_id}", response_model=ProcessResponse, status_code=200)
async def delete_color(color_id: int, session: AsyncSession = Depends(get_db)) -> dict[str, bool]:
  color = await Color.first(session, id=color_id)
  if not color:
    raise JSRError("not_found")

  await color.delete(session)
  return {"processed": True}


@router.get("/sizes", response_model=SizesResponse)
async def get_sizes(session: AsyncSession = Depends(get_db)) -> dict[str, list[dict]]:
  sizes = await Size.all(session)
  items = sorted((size.json for size in sizes), key=lambda item: item["id"])
  return {"items": items}


@router.get("/size/{size_id}", response_model=SizeResponse)
async def get_size(size_id: int, session: AsyncSession = Depends(get_db)) -> dict:
  size = await Size.first(session, id=size_id)
  if not size:
    raise JSRError("not_found")
  return size.json


@router.post("/size", response_model=SizeResponse, status_code=200)
async def save_size(payload: SizeRequest, session: AsyncSession = Depends(get_db)) -> dict:
  if payload.size_min > payload.size_max:
    raise JSRError("bad_request", message="size_min must be less than or equal to size_max")

  if payload.id is None:
    existing = await Size.first(session, sku=payload.sku)
    if existing:
      raise JSRError("conflict", message=f'Size with sku "{payload.sku}" already exists')
    size = Size(**payload.model_dump(exclude={"id"}))
    await size.save(session)
    return size.json

  size = await Size.first(session, id=payload.id)
  if not size:
    raise JSRError("not_found")

  sku_owner = await Size.first(session, sku=payload.sku)
  if sku_owner and sku_owner.id != size.id:
    raise JSRError("conflict", message=f'Size with sku "{payload.sku}" already exists')

  await size.edit(session, sku=payload.sku, size_min=payload.size_min, size_max=payload.size_max)
  return size.json


@router.put("/sizes", response_model=BatchUpdateResponse, status_code=200)
async def update_sizes(payload: SizeBatchUpdateRequest, session: AsyncSession = Depends(get_db)) -> dict[str, bool | int]:
  _ensure_unique_entries([item.id for item in payload.items], "size")
  _ensure_unique_entries([item.sku for item in payload.items], "size sku")

  for item in payload.items:
    if item.size_min > item.size_max:
      raise JSRError("bad_request", message="size_min must be less than or equal to size_max")

    size = await Size.first(session, id=item.id)
    if not size:
      raise JSRError("not_found")

    sku_owner = await Size.first(session, sku=item.sku)
    if sku_owner and sku_owner.id != item.id:
      raise JSRError("conflict", message=f'Size with sku "{item.sku}" already exists')

  for item in payload.items:
    size = await Size.first(session, id=item.id)
    await size.edit(session, sku=item.sku, size_min=item.size_min, size_max=item.size_max)

  return {"processed": True, "updated": len(payload.items)}


@router.delete("/size/{size_id}", response_model=ProcessResponse, status_code=200)
async def delete_size(size_id: int, session: AsyncSession = Depends(get_db)) -> dict[str, bool]:
  size = await Size.first(session, id=size_id)
  if not size:
    raise JSRError("not_found")

  await size.delete(session)
  return {"processed": True}


@router.get("/warehouse/specs", response_model=WarehouseSpecsResponse)
async def get_warehouse_specs(locale: str, session: AsyncSession = Depends(get_db)) -> dict[str, list[dict]]:
  _validate_locale(locale)
  colors = await Color.all(session)
  sizes = await Size.all(session)
  return {
    "categories": await _fetch_localized_categories(session, locale),
    "colors": sorted((color.json for color in colors), key=lambda item: item["id"]),
    "sizes": sorted((size.json for size in sizes), key=lambda item: item["id"]),
  }
