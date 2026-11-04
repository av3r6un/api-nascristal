from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.exceptions import JSRError
from src.models import User
from src.models.delivery import DeliveryShipment, IntegrationConfig
from src.models.user import Role
from src.schemas.delivery import IntakeRequest, ModuleUpdate, QuoteRequest, ShipmentRequest, PurchaseDelivery, WidgetSelection
from src.services import cdek
from src.services import cdek_webhooks, cdek_widget
from src.services.cdek_locations import search_cities
from src.services.cdek_client import CdekClient
from src.services.integrations import MODULES, configuration, definition, describe, save_configuration, delivery_selection

router = APIRouter(tags=['delivery'])


async def staff(request: Request, session: AsyncSession = Depends(get_db)):
  user = await session.get(User, getattr(request.state, 'user_uid', None))
  if not user or user.role not in (Role.OWNER, Role.DEVELOPER, Role.MANAGER):
    raise JSRError(status=403, message='Staff access required')
  return user


async def administrator(user=Depends(staff)):
  if user.role not in (Role.OWNER, Role.DEVELOPER):
    raise JSRError(status=403, message='Administrator access required')
  return user


@router.get('/api/delivery/modules')
async def delivery_modules(enabled: bool | None = True, session: AsyncSession = Depends(get_db)):
  items = []
  for code, module in MODULES.items():
    if module.type != 'delivery':
      continue
    row = await session.get(IntegrationConfig, code)
    active = bool(row and row.enabled)
    if enabled is not None and active != enabled:
      continue
    items.append(dict(code=code, name=module.name, type=module.type, enabled=active,
      configured=bool(row and row.config.get('account') and row.config.get('secure_password')), capabilities=module.capabilities))
  return {'items': items}


@router.get('/api/integrations/modules', dependencies=[Depends(administrator)])
async def integration_modules(enabled: bool | None = None, type: str | None = None, session: AsyncSession = Depends(get_db)):
  """Installed implementations, with their saved state and no connection data."""
  rows = (await session.execute(select(IntegrationConfig))).scalars()
  states = {row.code: row.enabled for row in rows}
  return {'items': [dict(code=code, name=module.name, type=module.type, enabled=states.get(code, False))
    for code, module in MODULES.items()
    if (enabled is None or states.get(code, False) == enabled) and (type is None or module.type == type)]}


@router.get('/api/integrations', dependencies=[Depends(administrator)])
async def integrations(session: AsyncSession = Depends(get_db)):
  items = []
  for code, module in MODULES.items():
    enabled, config, saved = await configuration(session, code)
    items.append(describe(module, enabled, config, saved))
  return {'items': items}


@router.get('/api/integrations/{code}', dependencies=[Depends(administrator)])
async def integration(code: str, session: AsyncSession = Depends(get_db)):
  module = definition(code)
  enabled, config, saved = await configuration(session, code)
  return describe(module, enabled, config, saved)


@router.put('/api/integrations/{code}', dependencies=[Depends(administrator)])
async def configure_integration(code: str, payload: ModuleUpdate, session: AsyncSession = Depends(get_db)):
  return await save_configuration(session, code, payload)


@router.post('/api/delivery/cdek/quote')
async def quote(payload: QuoteRequest, session: AsyncSession = Depends(get_db)):
  return await cdek.quote(session, payload)


@router.post('/api/integrations/cdek/webhooks', dependencies=[Depends(administrator)])
async def register_webhooks(session: AsyncSession = Depends(get_db)):
  return await cdek_webhooks.subscribe(session)


@router.post('/webhooks/cdek')
async def cdek_webhook(payload: cdek_webhooks.Notification, token: str | None = None,
  session: AsyncSession = Depends(get_db)):
  return await cdek_webhooks.receive(session, token, payload)


@router.get('/api/delivery/cdek/cities')
async def cities(name: str = Query(min_length=3, max_length=100), session: AsyncSession = Depends(get_db)):
  return {'items': await search_cities(session, name)}


@router.get('/api/delivery/cdek/points')
async def delivery_points(city_code: int = Query(gt=0), type: Literal['PVZ', 'POSTAMAT', 'ALL'] = 'ALL',
  session: AsyncSession = Depends(get_db)):
  _, config, _ = await configuration(session, require_enabled=True)
  async with CdekClient(config) as client:
    return await client.request('GET', '/v2/deliverypoints',
      params={'city_code': city_code, 'country_code': 'RU', 'type': type})


@router.get('/api/delivery/shipments', dependencies=[Depends(staff)])
async def shipments(offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100),
  session: AsyncSession = Depends(get_db)):
  rows = (await session.execute(select(DeliveryShipment).order_by(DeliveryShipment.id.desc())
    .offset(offset).limit(limit))).scalars()
  return {'items': [row.json for row in rows]}


@router.get('/api/purchases/{purchase_id}/delivery', dependencies=[Depends(staff)])
async def shipment(purchase_id: int, session: AsyncSession = Depends(get_db)):
  return (await cdek.shipment_for_purchase(session, purchase_id)).json


@router.put('/api/purchases/{purchase_id}/delivery', dependencies=[Depends(staff)])
async def save_delivery(purchase_id: int, payload: PurchaseDelivery, session: AsyncSession = Depends(get_db)):
  purchase = await cdek.save_purchase_delivery(session, purchase_id, payload)
  return purchase.delivery


@router.post('/api/purchases/{purchase_id}/delivery/cdek', dependencies=[Depends(staff)])
async def create(purchase_id: int, payload: ShipmentRequest, retry_rejected: bool = False,
  session: AsyncSession = Depends(get_db)):
  return (await cdek.create_shipment(session, purchase_id, payload, retry_rejected=retry_rejected)).json


@router.post('/api/purchases/{purchase_id}/delivery/refresh', dependencies=[Depends(staff)])
async def refresh(purchase_id: int, session: AsyncSession = Depends(get_db)):
  return (await cdek.refresh_shipment(session, purchase_id)).json


@router.patch('/api/purchases/{purchase_id}/delivery', dependencies=[Depends(staff)])
async def update(purchase_id: int, payload: ShipmentRequest, session: AsyncSession = Depends(get_db)):
  return (await cdek.update_shipment(session, purchase_id, payload)).json


@router.delete('/api/purchases/{purchase_id}/delivery', dependencies=[Depends(staff)])
async def cancel(purchase_id: int, session: AsyncSession = Depends(get_db)):
  return await cdek.shipment_operation(session, purchase_id, 'cancel')


@router.post('/api/purchases/{purchase_id}/delivery/intake', dependencies=[Depends(staff)])
async def intake(purchase_id: int, payload: IntakeRequest, session: AsyncSession = Depends(get_db)):
  return await cdek.shipment_operation(session, purchase_id, 'intake', payload=payload.model_dump(mode='json'))


@router.post('/api/purchases/{purchase_id}/delivery/documents/{kind}', dependencies=[Depends(staff)])
async def create_document(purchase_id: int, kind: Literal['waybill', 'barcode'], session: AsyncSession = Depends(get_db)):
  return await cdek.shipment_operation(session, purchase_id, kind)


@router.get('/api/purchases/{purchase_id}/delivery/documents/{kind}', dependencies=[Depends(staff)])
async def document_status(purchase_id: int, kind: Literal['waybill', 'barcode'],
  pdf: bool = False, session: AsyncSession = Depends(get_db)):
  result = await cdek.document(session, purchase_id, kind, pdf=pdf)
  return Response(result, media_type='application/pdf') if pdf else result


@router.get('/api/delivery/cdek/widget/config')
async def widget_config(quantity: int = Query(gt=0, le=999), session: AsyncSession = Depends(get_db)):
  _, config, _ = await configuration(session, require_enabled=True)
  if not config.from_location:
    raise JSRError(status=409, message='Sender city is not configured')
  return {'package': cdek.estimated_package(config, quantity)}


@router.api_route('/api/delivery/cdek/widget', methods=['GET', 'POST'])
async def widget_service(request: Request, response: Response, session: AsyncSession = Depends(get_db)):
  data = dict(request.query_params)
  if request.method == 'POST':
    try:
      body = await request.json()
    except ValueError as exc:
      raise JSRError('bad_request', message='Invalid widget body') from exc
    if not isinstance(body, dict):
      raise JSRError('bad_request', message='Invalid widget body')
    data.update(body)
  result = await cdek_widget.service(session, data)
  response.headers['X-Service-Version'] = cdek_widget.VERSION
  return result


@router.post('/api/delivery/cdek/widget/selection')
async def widget_selection(payload: WidgetSelection, session: AsyncSession = Depends(get_db)):
  return await cdek_widget.selection(session, payload)
