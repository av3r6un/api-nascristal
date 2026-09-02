from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.schemas import ProductsResponse,ProductsAttributesResponse
from src.services import ProductService


router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("/", response_model=ProductsResponse)
async def get_products(page_index: int = Query(default=0, ge=0), all_products: bool = Query(default=False, alias="all"), session: AsyncSession = Depends(get_db)) -> ProductsResponse:
  return await ProductService.get_products(session, page_index, fetch_all=all_products)


@router.get('/attributes', response_model=ProductsAttributesResponse)
async def get_attributes(session: AsyncSession = Depends(get_db)):
  return await ProductService.get_attributes(session)
