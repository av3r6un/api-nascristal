from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.schemas import ProductsResponse, StockAvailabilityResponse
from src.services import ProductService


router = APIRouter(prefix="/api/stock", tags=["stock"])

FILTER_KEYS = ("category", "fixation", "cuts", "size", "color", "form")
LEGACY_FILTER_KEYS = {"0": "category", "1": "cuts", "2": "size", "3": "color", "4": "form"}


def _split_values(values: list[str]) -> list[str]:
  return list(dict.fromkeys(
    part.strip()
    for value in values
    for part in value.split(",")
    if part.strip()
  ))


def _stock_filters(request: Request) -> dict[str, list[str]]:
  filters: dict[str, list[str]] = {}
  for key in FILTER_KEYS:
    values = _split_values(request.query_params.getlist(key))
    if values:
      filters[key] = values

  for legacy_key, filter_key in LEGACY_FILTER_KEYS.items():
    values = _split_values(request.query_params.getlist(legacy_key))
    if not values:
      continue
    if legacy_key == "0" and all(value.lower() in {"hot", "non", "k9"} for value in values):
      filter_key = "fixation"
    filters.setdefault(filter_key, values)
  return filters


StockQuery = Annotated[list[str] | None, Query()]

@router.get('/', response_model=ProductsResponse)
async def get_stock(
  request: Request,
  page_index: int = Query(default=0, ge=0),
  page_size: int | None = Query(default=None, ge=1, le=100),
  category: StockQuery = None,
  fixation: StockQuery = None,
  cuts: StockQuery = None,
  size: StockQuery = None,
  color: StockQuery = None,
  form: StockQuery = None,
  session: AsyncSession = Depends(get_db),
) -> ProductsResponse:
  return await ProductService.get_stock(
    session,
    page_index,
    page_size=page_size,
    **_stock_filters(request),
  )


@router.get('/availability', response_model=StockAvailabilityResponse)
async def get_stock_availability(
  request: Request,
  category: StockQuery = None,
  fixation: StockQuery = None,
  cuts: StockQuery = None,
  size: StockQuery = None,
  color: StockQuery = None,
  form: StockQuery = None,
  session: AsyncSession = Depends(get_db),
) -> StockAvailabilityResponse:
  return await ProductService.get_stock_availability(session, **_stock_filters(request))
