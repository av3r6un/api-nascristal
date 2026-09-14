from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.schemas import AttributeOptionsPatchRequest, ProductsAttributesResponse
from src.services import ProductService


router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("/", response_model=ProductsAttributesResponse)
async def get_catalog(session: AsyncSession = Depends(get_db)):
  return await ProductService.get_attributes(session)


@router.patch("/options", response_model=ProductsAttributesResponse)
async def patch_attribute_options(
  payload: AttributeOptionsPatchRequest,
  request: Request,
  session: AsyncSession = Depends(get_db),
):
  return await ProductService.patch_attribute_options(
    session,
    payload.items,
    actor_uid=getattr(request.state, "user_uid", None),
  )
