from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.change_logging import record_change
from src.core.database import get_db
from src.exceptions import JSRError
from src.models import Category
from src.schemas import CategoriesPatchRequest, CategoriesResponse


router = APIRouter(prefix="/api/categories", tags=["categories"])


async def _fetch_categories(session: AsyncSession) -> list[Category]:
  query = select(Category).order_by(Category.index.asc(), Category.id.asc())
  result = await session.execute(query)
  return result.scalars().all()


@router.get("/", response_model=CategoriesResponse, status_code=200)
async def get_categories(session: AsyncSession = Depends(get_db)) -> dict[str, list[dict]]:
  categories = await _fetch_categories(session)
  return {"items": [category.json for category in categories]}


@router.patch("/", response_model=CategoriesResponse, status_code=200)
async def patch_categories(
  payload: CategoriesPatchRequest,
  request: Request,
  session: AsyncSession = Depends(get_db),
) -> dict[str, list[dict]]:
  requested_ids = [item.id for item in payload.items]
  result = await session.execute(select(Category).where(Category.id.in_(requested_ids)))
  categories_by_id = {category.id: category for category in result.scalars().all()}

  missing_ids = sorted(set(requested_ids) - set(categories_by_id))
  if missing_ids:
    raise JSRError("not_found", message=f"Categories not found: {', '.join(str(item) for item in missing_ids)}")

  for item in payload.items:
    category = categories_by_id[item.id]
    if item.name is not None:
      category.name = item.name
    if item.index is not None:
      category.index = item.index
    if item.icon is not None:
      category.icon = item.icon

  await session.commit()

  actor_uid = getattr(request.state, "user_uid", None)
  await record_change(
    session,
    "categories.updated",
    payload={"ids": requested_ids},
    actor_uid=actor_uid,
  )

  categories = await _fetch_categories(session)
  return {"items": [category.json for category in categories]}
