from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.change_logging import record_change
from src.core.database import get_db
from src.exceptions import JSRError
from src.models import Property, PropertyOption
from src.schemas import CatalogResponse, PropertyOptionsPatchRequest, PropertyOptionsResponse


router = APIRouter(prefix="/api/catalog", tags=["catalog"])


def _serialize_property(property_row: Property) -> dict:
  return {
    "id": property_row.id,
    "index": property_row.index,
    "name": property_row.name,
    "is_active": property_row.is_active,
  }


def _serialize_catalog_option(option: PropertyOption) -> dict:
  return {
    "id": option.id,
    "property_id": option.property_id,
    "value": option.value,
    "name": option.name,
    "icon": option.icon,
  }


def _serialize_option(option: PropertyOption) -> dict:
  return {
    "id": option.id,
    "eid": option.eid,
    "property_id": option.property_id,
    "value": option.value,
    "name": option.name,
    "icon": option.icon,
    "is_active": option.is_active,
    "property": {
      "id": option.property.id,
      "eid": option.property.eid,
      "index": option.property.index,
      "name": option.property.name,
      "is_active": option.property.is_active,
    },
  }


async def _fetch_properties(session: AsyncSession) -> list[Property]:
  query = select(Property).order_by(Property.index.asc(), Property.id.asc())
  result = await session.execute(query)
  return result.scalars().all()


async def _fetch_property_options(session: AsyncSession) -> list[PropertyOption]:
  query = (
    select(PropertyOption)
    .options(selectinload(PropertyOption.property))
    .order_by(PropertyOption.property_id.asc(), PropertyOption.value.asc(), PropertyOption.id.asc())
  )
  result = await session.execute(query)
  return result.scalars().all()


@router.get("/", response_model=CatalogResponse, status_code=200)
async def get_catalog(session: AsyncSession = Depends(get_db)) -> dict[str, list[dict]]:
  properties = await _fetch_properties(session)
  options = await _fetch_property_options(session)
  return {
    "properties": [_serialize_property(property_row) for property_row in properties],
    "options": [_serialize_catalog_option(option) for option in options],
  }


@router.get("/options/", response_model=PropertyOptionsResponse, status_code=200)
async def get_property_options(session: AsyncSession = Depends(get_db)) -> dict[str, list[dict]]:
  options = await _fetch_property_options(session)
  return {"items": [_serialize_option(option) for option in options]}


@router.patch("/options/", response_model=PropertyOptionsResponse, status_code=200)
async def patch_property_options(
  payload: PropertyOptionsPatchRequest,
  request: Request,
  session: AsyncSession = Depends(get_db),
) -> dict[str, list[dict]]:
  requested_ids = [item.id for item in payload.items]
  result = await session.execute(select(PropertyOption).where(PropertyOption.id.in_(requested_ids)))
  options_by_id = {option.id: option for option in result.scalars().all()}

  missing_ids = sorted(set(requested_ids) - set(options_by_id))
  if missing_ids:
    raise JSRError("not_found", message=f"Property options not found: {', '.join(str(item) for item in missing_ids)}")

  for item in payload.items:
    option = options_by_id[item.id]
    if "name" in item.model_fields_set:
      option.name = item.name
    if "icon" in item.model_fields_set:
      option.icon = item.icon

  await session.commit()

  actor_uid = getattr(request.state, "user_uid", None)
  await record_change(
    session,
    "property_options.updated",
    payload={"ids": requested_ids},
    actor_uid=actor_uid,
  )

  options = await _fetch_property_options(session)
  return {"items": [_serialize_option(option) for option in options]}
