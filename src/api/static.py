from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import APIRouter, Depends, Request

from src.core.database import get_db
from src.exceptions import JSRError
from src.models import StaticPage, StaticPagesTranslation
from src.models.static import PageStatus
from src.schemas import StaticPageResponse, StaticPageRequest, StaticPagesResponse


router = APIRouter(prefix="/api/static", tags=["static"])


@router.get('/', response_model=StaticPagesResponse)
async def fetch_pages(locale: str, request: Request, session: AsyncSession = Depends(get_db)) -> dict[str, list]:
  if locale not in {"ru", "en"}:
    raise JSRError("bad_request", message="Locale must be 'ru' or 'en'")

  query = (
    select(StaticPage, StaticPagesTranslation)
    .join(StaticPagesTranslation, StaticPagesTranslation.page_id == StaticPage.id)
    .where(StaticPagesTranslation.locale == locale)
    .where(StaticPage.status == PageStatus.PUBLISHED)
  )
  result = await session.execute(query)

  items = []
  for page, translation in result.all():
    items.append(
      {
        "id": page.id,
        "slug": page.slug,
        "status": page.status.value,
        **translation.json
      }
    )

  return {"items": items}


@router.post('/', status_code=200)
async def save_page(payload: StaticPageRequest, request: Request, session: AsyncSession = Depends(get_db)) -> dict[str, bool]:
  page = await StaticPage.first(session, slug=payload.slug)
  if not page:
    page = StaticPage(payload.slug, status=payload.status)
    await page.save(session)
    await session.flush()
  
  already_set_translation = await StaticPagesTranslation.first(session, page_id=page.id, locale=payload.locale)
  if already_set_translation:
      await already_set_translation.edit(session, **payload.model_dump())
  else:
    translation = StaticPagesTranslation(page.id, **payload.model_dump())
    await translation.save(session)
  return dict(processed=True)


@router.get('/{slug}/{locale}', response_model=StaticPageResponse)
async def get_page(slug: str, locale: str, session: AsyncSession = Depends(get_db)) -> dict:
  page = await StaticPage.first(session, slug=slug, status=PageStatus.PUBLISHED)
  if not page: raise JSRError('not_found')
  translated_page = await StaticPagesTranslation.first(session, page_id=page.id, locale=locale)
  if not translated_page: raise JSRError('not_found')
  return translated_page.json
