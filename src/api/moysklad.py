from fastapi import APIRouter, Depends, HTTPException, Request
import httpx
from typing import Literal
from src.models.user import User, Role
from src.services.moysklad_client import MoySkladError
from src.services.moysklad_webhook_registration import manage_webhooks, registration_lock
from src.core.change_logging import record_change
from src.core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from src.schemas import MoySkladImportResponse
from src.services import MoySkladImportService, MoySkladClient
import json

router = APIRouter(prefix="/api/moysklad", tags=["moysklad"])


async def webhook_admin(request: Request, session: AsyncSession = Depends(get_db)):
  user = await User.first(session, uid=getattr(request.state, 'user_uid', None))
  if not user or user.role not in (Role.OWNER, Role.DEVELOPER):
    raise HTTPException(403, 'Webhook management requires owner or developer role')


async def webhook_operation(operation: str):
  try:
    async with registration_lock, MoySkladClient(timeout=5.0) as client:
      return await manage_webhooks(client, operation)
  except ValueError:
    raise HTTPException(503, 'Check MOYSKLAD_TOKEN, MOYSKLAD_WEBHOOK_URL, MOYSKLAD_WEBHOOK_SECRET and MOYSKLAD_ACCOUNT_ID')
  except MoySkladError as exc:
    raise HTTPException(502, f'MoySklad webhook request failed (HTTP {exc.status_code})')
  except httpx.HTTPError:
    raise HTTPException(502, 'MoySklad webhook request failed: network error')


@router.get('/webhooks/status', dependencies=[Depends(webhook_admin)])
async def webhook_status():
  return await webhook_operation('status')


@router.post('/webhooks/{operation}', dependencies=[Depends(webhook_admin)])
async def set_webhooks(operation: Literal['connect', 'disconnect']):
  return await webhook_operation(operation)


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
  variants_count = sum(1 for row in rows if row.get("meta", {}).get("type") == "variant")
  await record_change(
    session,
    "products.moysklad.imported",
    payload={
      "products": len(products),
      "variants": variants_count,
      "skipped_products": len(skipped_products),
    },
  )

  return MoySkladImportResponse(
    products=len(products),
    variants=variants_count,
    skipped_products=[
      {"id": product["id"], "name": product["name"]}
      for product in skipped_products
    ],
  )
