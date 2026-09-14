from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.schemas import ProductsResponse, ProductsAttributesResponse, ProductResponse
from src.services import ProductService
from src.services.moysklad_client import MoySkladClient
from src.services.product_image_upload import ProductImageUploadError, ProductImageUploadService
from src.models import ProductVariant
from src.exceptions import JSRError


router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("/", response_model=ProductsResponse)
async def get_products(page_index: int = Query(default=0, ge=0), all_products: bool = Query(default=False, alias="all"), session: AsyncSession = Depends(get_db)) -> ProductsResponse:
  return await ProductService.get_products(session, page_index, fetch_all=all_products)


@router.get('/attributes', response_model=ProductsAttributesResponse)
async def get_attributes(session: AsyncSession = Depends(get_db)):
  return await ProductService.get_attributes(session)


@router.get('/{id}', response_model=ProductResponse)
async def get_product(id: int, session: AsyncSession = Depends(get_db)) -> ProductResponse:
  return await ProductService.get_product(session, id)


@router.post('/variants/{variant_id}/image')
async def upload_variant_image(
  variant_id: int,
  request: Request,
  file: UploadFile = File(...),
  session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
  if not getattr(request.state, "user_uid", None):
    raise JSRError('unauthorized')
  variant = await session.scalar(select(ProductVariant).where(ProductVariant.id == variant_id))
  if variant is None:
    raise JSRError('not_found', message=f'ProductVariant[{variant_id}] is not found')
  if not file.content_type:
    raise JSRError('bad_request', message='Image content type is required')
  content = await file.read()
  try:
    async with MoySkladClient() as client:
      result = await ProductImageUploadService().upload_for_variant(
        client=client, variant_id=variant.uuid, category_name=variant.product.category.name,
        content=content, content_type=file.content_type,
      )
    variant.image_key = result["object_key"]
    await session.commit()
    return result
  except ProductImageUploadError as exc:
    raise JSRError('bad_request', message=str(exc)) from exc
