from fastapi import APIRouter, Depends
from src.core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from src.schemas import MoySkladImportResponse
from src.services import MoySkladImportService, MoySkladClient
import json

router = APIRouter(prefix="/api/moysklad", tags=["moysklad"])


@router.get("/import", response_model=MoySkladImportResponse, status_code=200)
async def manual_import(
  session: AsyncSession = Depends(get_db),
) -> MoySkladImportResponse:
  async with MoySkladClient() as client:
    rows = [
      row
      async for row in client.iter_entities("assortment", filter="archived=false")
    ]

  products, skipped_products = await MoySkladImportService.import_assortment(session, rows)
  await session.commit()

  return MoySkladImportResponse(
    products=len(products),
    variants=sum(1 for row in rows if row.get("meta", {}).get("type") == "variant"),
    skipped_products=[
      {"id": product["id"], "name": product["name"]}
      for product in skipped_products
    ],
  )
