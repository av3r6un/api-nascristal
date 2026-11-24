from fastapi import APIRouter, Depends, Request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.change_logging import record_change
from src.core.database import get_db
from src.exceptions import JSRError
from src.models import Category
from src.schemas import CategoriesPatchRequest, CategoriesResponse

from .delivery import staff


router = APIRouter(prefix="/api", tags=["categories"])


async def _fetch_categories(session: AsyncSession) -> list[Category]:
  query = select(Category).order_by(Category.sort_order.asc(), Category.id.asc())
  result = await session.execute(query)
  return result.scalars().all()


@router.get("/categories/", response_model=CategoriesResponse, status_code=200)
async def get_categories(session: AsyncSession = Depends(get_db)) -> dict[str, list[dict]]:
  categories = await _fetch_categories(session)
  return {"items": [category.json for category in categories]}


@router.patch("/categories/", response_model=CategoriesResponse, status_code=200)
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
    if item.sort_order is not None:
      category.sort_order = item.sort_order

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


@router.delete("/category/{id}", status_code=204, dependencies=[Depends(staff)])
async def delete_category(id: int, request: Request, session: AsyncSession = Depends(get_db)) -> None:
  query = (
    delete(Category)
    .where(Category.id == id, ~Category.products.any())
    .execution_options(synchronize_session=False)
  )
  try:
    result = await session.execute(query)
  except IntegrityError as exc:
    await session.rollback()
    raise JSRError("conflict", message=f"Category {id} is in use") from exc

  if result.rowcount == 0:
    category_id = await session.scalar(select(Category.id).where(Category.id == id))
    if category_id is None:
      raise JSRError("not_found", message=f"Category {id} not found")
    raise JSRError("conflict", message=f"Category {id} has products")

  await record_change(session, "categories.deleted", payload={"ids": [id]}, actor_uid=request.state.user_uid)
