from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends

from src.core.database import get_db
from src.exceptions import JSRError
from src.schemas import CatalogResponse

router = APIRouter(prefix='/api/catalog', tags=['catalog'])


@router.get('/', response_model=CatalogResponse)
async def get_catalog(session: AsyncSession = Depends(get_db)) -> list:
  return []
