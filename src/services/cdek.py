"""Site-owned shipments only; durable write reservations prevent duplicate waybills."""
import asyncio
import hashlib
import json
import logging
from decimal import Decimal, InvalidOperation
from uuid import UUID, NAMESPACE_URL, uuid5

from sqlalchemy import select

from src.core.config import settings
from src.core.database import session_maker
from src.exceptions import JSRError
from src.models import Payment, Purchase, PurchaseStatus
from src.models.delivery import DeliveryShipment
from src.schemas.delivery import Recipient
from src.services.cdek_client import CdekClient, CdekError, errors_from
from src.services.integrations import configuration
from src.services.cdek_routing import calculate
from src.services.paid_items import paid_items
from src.services.purchase_sync import lock_purchase


def fingerprint(config):
  return hashlib.sha256((config.account or '').encode()).hexdigest()


def order_number(purchase, config):
  return 'WEB-' + uuid5(NAMESPACE_URL,
    f'nascrystal:{settings.STAGE}:{config.environment}:{config.account}:{purchase.uuid}').hex


def estimated_package(config, quantity):
  return dict(weight=config.estimated_unit_weight * quantity, length=config.estimated_length,
    width=config.estimated_width, height=config.estimated_height)


async def quote(session, payload):
  _, config, _ = await configuration(session, require_enabled=True)
  package = estimated_package(config, payload.quantity)
  calculation = await calculate(config, package, to_location=payload.to_location,
    delivery_point=payload.delivery_point, tariff_code=payload.tariff_code)
  return dict(estimated=True, package=package, tariff_code=calculation['tariff_code'],
    delivery_mode=calculation['delivery_mode'], result=calculation['result'], tariffs=calculation['tariffs'],
    service_fee_enabled=config.service_fee_enabled,
    service_fee=str(config.service_fee if config.service_fee_enabled else Decimal(0)),
    delivery_payment_mode='recipient_collection_under_sender_contract')


async def shipment_for_purchase(session, purchase_id):
  row = (await session.execute(select(DeliveryShipment).where(DeliveryShipment.purchase_id == purchase_id))).scalar_one_or_none()
  if row is None:
    raise JSRError('not_found', message='Shipment not found')
  return row


def check_identity(row, config):
  if row.account_fingerprint != fingerprint(config):
    raise JSRError(status=409, message='Shipment belongs to a different CDEK account')


def can_edit(row):
  if row is None:
    return True
  if row.status == 'rejected' and not row.remote_uuid:
    return True
  editing = row.editing or {}
  return bool(row.remote_uuid and row.status in ('ACCEPTED', 'CREATED')
    and (row.cancellation or {}).get('state') in (None, 'rejected')
    and editing.get('state') not in ('pending', 'unknown')
    and not (editing.get('changes') and editing.get('state') != 'rejected'))


def has_delivery_draft(purchase):
  return (purchase.delivery or {}).get('data', {}).get('cdek_package_draft') is True


class PackageRegistrationPending(JSRError):
  pass


def can_dispatch(purchase, row):
  return bool(purchase.status in (PurchaseStatus.ASSEMBLING, PurchaseStatus.PROCESSING)
    and not has_delivery_draft(purchase)
    and row and row.remote_uuid and row.tracking_number
    and row.status in ('ACCEPTED', 'CREATED')
    and row.details.get('reviewed_and_packed') is True
    and row.registration.get('state') == 'success'
    and row.editing.get('state') in (None, 'success')
    and row.cancellation.get('state') in (None, 'rejected'))


def uuid_from(data):
  try:
    return str(UUID(data['entity']['uuid']))
  except (KeyError, ValueError, TypeError) as exc:
    raise CdekError('CDEK response has no entity UUID', ambiguous=True) from exc


async def build_payload(session, purchase, config, payload):
  if not config.from_location or not config.sender:
    raise JSRError(status=409, message='Sender contact and location must be configured')
  if not config.shipment_point and not config.from_location.address:
    raise JSRError(status=409, message='Sender address or shipment point is required')
  items = await paid_items(session, purchase)
  total_weight = sum(i['amount'] for i in items)
  if payload.package.weight < total_weight:
    raise JSRError('bad_request', message='Packed weight is too small to describe all items in grams')
  # Distribute the actual gross weight rather than sending the calculator's estimates.
  for item in items:
    item['weight'] = max(1, payload.package.weight // total_weight)
  calculation = await calculate(config, payload.package.model_dump(), to_location=payload.to_location,
    delivery_point=payload.delivery_point, tariff_code=payload.tariff_code)
  delivery_cost = calculation['price']
  result = dict(type=1, number=order_number(purchase, config), tariff_code=calculation['tariff_code'],
    sender=config.sender.model_dump(exclude_none=True), recipient=payload.recipient.model_dump(exclude_none=True),
    packages=[dict(number='1', **payload.package.model_dump(), items=items)],
    delivery_recipient_cost={'value': float(delivery_cost + (config.service_fee if config.service_fee_enabled else 0))})
  if config.shipment_point:
    result['shipment_point'] = config.shipment_point
  else:
    result['from_location'] = config.from_location.model_dump(exclude_none=True)
  if payload.delivery_point:
    result['delivery_point'] = payload.delivery_point
  else:
    result['to_location'] = payload.to_location.model_dump(exclude_none=True)
  return result


def request_hash(body):
  data = {key: value for key, value in body.items() if key not in ('number', 'type', 'uuid')}
  return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def summary(data, request_type=None):
  requests = data.get('requests') or []
  if request_type:
    requests = [r for r in requests if r.get('type') in request_type]
  latest = max(requests, key=lambda r: r.get('date_time', ''), default={})
  errors = errors_from({'errors': data.get('errors') or [], 'requests': [latest] if latest else []})
  state = latest.get('state', 'ACCEPTED')
  statuses = data.get('entity', {}).get('statuses') or []
  if not request_type and statuses:
    state = max(statuses, key=lambda s: s.get('date_time', ''))['code']
  if state == 'INVALID':
    errors.extend(errors_from({'errors': latest.get('warnings') or []}))
  state = {'INVALID': 'rejected', 'SUCCESSFUL': 'success', 'READY': 'ready',
    'ACCEPTED': 'accepted', 'WAITING': 'pending', 'PROCESSING': 'pending'}.get(state, state.lower())
  result = {'state': 'rejected' if errors else state, 'errors': errors}
  if data.get('entity', {}).get('uuid'):
    result['uuid'] = data['entity']['uuid']
  if latest.get('request_uuid'):
    result['request_uuid'] = latest['request_uuid']
  return result


def failure(exc):
  return {'state': 'unknown' if exc.ambiguous else 'rejected',
    'errors': exc.errors or [{'code': 'request_failed', 'message': str(exc)}]}


def shipment_details(payload, body, config):
  details = payload.model_dump(mode='json')
  details['selected_tariff_code'] = body['tariff_code']
  details['delivery_cost'] = str(Decimal(str(body['delivery_recipient_cost']['value'])) -
    (config.service_fee if config.service_fee_enabled else 0))
  return details


def save_details(row, purchase, payload, body, config):
  row.details = shipment_details(payload, body, config)
  row.request_hash = request_hash(body)
  purchase.delivery = {'module': 'cdek', 'data': {**(purchase.delivery or {}).get('data', {}), **row.details}}


async def create_shipment(session, purchase_id, payload, *, retry_rejected=False):
  _, config, _ = await configuration(session, require_enabled=True)
  purchase = await lock_purchase(session, purchase_id)
  existing = (await session.execute(select(DeliveryShipment).where(DeliveryShipment.purchase_id == purchase_id))).scalar_one_or_none()
  if existing:
    check_identity(existing, config)
    if not (retry_rejected and existing.status == 'rejected' and not existing.remote_uuid):
      return existing
  payment = await session.get(Payment, purchase.payment_id) if purchase.payment_id else None
  if payment is None or payment.status != 'succeeded' or not payment.paid:
    raise JSRError(status=409, message='Purchase must be paid before shipping')
  # Repair the old payment transition only when no CDEK shipment has ever been registered.
  if (purchase.status == PurchaseStatus.DELIVERING and (purchase.delivery or {}).get('module') == 'cdek'
    and (existing is None or (existing.status == 'rejected' and not existing.remote_uuid))):
    purchase.status = PurchaseStatus.ASSEMBLING
  if purchase.status not in (PurchaseStatus.ASSEMBLING, PurchaseStatus.PROCESSING, PurchaseStatus.CREATED):
    raise JSRError(status=409, message='Создание отправления доступно только для заказа в сборке')
  body = await build_payload(session, purchase, config, payload)
  row = existing or DeliveryShipment(purchase_id=purchase_id, provider='cdek',
    account_fingerprint=fingerprint(config), external_number=body['number'])
  row.status, row.registration = 'submitting', {'state': 'pending', 'errors': []}
  save_details(row, purchase, payload, body, config)
  session.add(row)
  await session.commit()
  try:
    async with CdekClient(config) as client:
      result = await client.request('POST', '/v2/orders', json=body)
    row.remote_uuid = uuid_from(result)
    row.status, row.registration = 'accepted', summary(result, ('CREATE',))
  except CdekError as exc:
    row.registration = failure(exc)
    row.status = row.registration['state']
    await session.commit()
    raise
  await session.commit()
  await session.refresh(row)
  return row


async def refresh_shipment(session, purchase_id, *, commit=True):
  row, _ = await _refresh_shipment(session, purchase_id, commit=commit)
  return row


async def _refresh_shipment(session, purchase_id, *, commit=True):
  _, config, _ = await configuration(session)
  purchase = await lock_purchase(session, purchase_id)
  row = await shipment_for_purchase(session, purchase_id)
  check_identity(row, config)
  async with CdekClient(config) as client:
    result = await client.request('GET', f'/v2/orders/{row.remote_uuid}' if row.remote_uuid else '/v2/orders',
      params=None if row.remote_uuid else {'im_number': row.external_number})
    entity = result.get('entity', {})
    if entity.get('number') != row.external_number:
      raise JSRError(status=409, message='CDEK order does not belong to this site purchase')
    remote_uuid = uuid_from(result)
    if row.remote_uuid and row.remote_uuid != remote_uuid:
      raise JSRError(status=409, message='CDEK order identity mismatch')
    row.remote_uuid = remote_uuid
    if entity.get('cdek_number'):
      row.tracking_number = str(entity['cdek_number'])
    for field, types in [('registration', ('CREATE',)), ('editing', ('UPDATE', 'EDIT')),
      ('cancellation', ('DELETE',))]:
      if any(r.get('type') in types for r in result.get('requests') or []):
        previous = getattr(row, field) or {}
        if field == 'editing' and previous.get('state') in ('pending', 'unknown') and not previous.get('changes'):
          continue
        request_uuid = previous.get('request_uuid') if field == 'editing' and previous.get('changes') else None
        if request_uuid:
          requests = [request for request in result['requests'] if request.get('request_uuid') == request_uuid]
          if not requests:
            continue
          state = summary({**result, 'requests': requests}, types)
        else:
          state = summary(result, types)
        if field == 'editing' and previous.get('changes'):
          if state['state'] == 'success':
            row.waybill, row.barcode = {}, {}
            row.details = previous['changes']
            row.request_hash = previous['request_hash']
            purchase.delivery = previous.get('selection') or {'module': 'cdek', 'data': row.details}
          else:
            state.update({key: previous[key] for key in ('changes', 'request_hash', 'selection') if key in previous})
        setattr(row, field, state)
    editing = row.editing or {}
    if (row.registration or {}).get('state') == 'success' and not (
      editing.get('state') in ('pending', 'unknown') or (editing.get('changes') and editing.get('state') != 'rejected')):
      confirmed = {}
      recipient = entity.get('recipient')
      if isinstance(recipient, dict):
        local_recipient = row.details.get('recipient', {})
        confirmed['recipient'] = {**local_recipient,
          **{key: value for key, value in recipient.items() if key in Recipient.model_fields},
          'contragent_type': local_recipient.get('contragent_type', recipient.get('contragent_type', 'INDIVIDUAL'))}
        if confirmed['recipient']['contragent_type'] == 'INDIVIDUAL':
          confirmed['recipient'].update(company=None, tin=None)
          confirmed['recipient'].pop('company_name', None)
      delivery_sum = (entity.get('delivery_detail') or {}).get('delivery_sum')
      charge = (entity.get('delivery_recipient_cost') or {}).get('value')
      try:
        if delivery_sum is not None:
          cost = Decimal(str(delivery_sum))
        elif charge is not None:
          cost = Decimal(str(charge)) - (config.service_fee if config.service_fee_enabled else 0)
        else:
          cost = None
        if cost is not None and cost.is_finite() and cost >= 0:
          confirmed['delivery_cost'] = str(cost)
      except InvalidOperation:
        pass
      if confirmed:
        if any(row.details.get(key) != value for key, value in confirmed.items()):
          row.details = {**row.details, **confirmed}
          row.request_hash = None
        if (purchase.delivery or {}).get('module') == 'cdek' and not has_delivery_draft(purchase):
          purchase.delivery = {'module': 'cdek', 'data': {**purchase.delivery['data'], **confirmed}}
    statuses = entity.get('statuses') or []
    if row.registration.get('state') == 'rejected':
      row.status = 'rejected'
    elif statuses:
      row.status = max(statuses, key=lambda s: s.get('date_time', ''))['code']
    if row.status == 'DELIVERED':
      purchase.status = PurchaseStatus.FINISHED
    elif row.status in ('RECEIVED_AT_SHIPMENT_WAREHOUSE', 'TAKEN_BY_COURIER',
      'READY_FOR_SHIPMENT_IN_SENDER_CITY', 'TAKEN_BY_TRANSPORTER_FROM_SENDER_CITY',
      'SENT_TO_TRANSIT_CITY', 'ACCEPTED_IN_TRANSIT_CITY', 'ACCEPTED_IN_TRANSIT_WAREHOUSE',
      'READY_FOR_SHIPMENT_IN_TRANSIT_CITY', 'TAKEN_BY_TRANSPORTER_FROM_TRANSIT_CITY',
      'SENT_TO_SENDER_CITY', 'SENT_TO_RECIPIENT_CITY', 'ACCEPTED_IN_RECIPIENT_CITY',
      'ACCEPTED_AT_RECIPIENT_CITY_WAREHOUSE', 'ACCEPTED_AT_PICK_UP_POINT',
      'TAKEN_BY_COURIER_FROM_PICK_UP_POINT', 'READY_FOR_DELIVERY', 'DELIVERY_DELAYED') and purchase.status in (
        PurchaseStatus.ASSEMBLING, PurchaseStatus.PROCESSING):
      purchase.status = PurchaseStatus.DELIVERING
    for field, path in [('waybill', '/v2/print/orders/'), ('barcode', '/v2/print/barcodes/'), ('pickup', '/v2/intakes/')]:
      operation = getattr(row, field) or {}
      if operation.get('uuid') and operation.get('state') in ('accepted', 'pending', 'unknown'):
        try:
          remote = await client.request('GET', path + operation['uuid'])
          setattr(row, field, summary(remote))
        except CdekError as exc:
          setattr(row, field, {**operation, 'errors': failure(exc)['errors']})
  if commit:
    await session.commit()
    await session.refresh(row)
  return row, entity


async def update_shipment(session, purchase_id, payload, *, selection=None):
  _, config, _ = await configuration(session, require_enabled=True)
  purchase = await lock_purchase(session, purchase_id)
  row, entity = await _refresh_shipment(session, purchase_id, commit=False)
  check_identity(row, config)
  if (not row.remote_uuid or row.status not in ('ACCEPTED', 'CREATED')
    or (row.cancellation or {}).get('state') not in (None, 'rejected')):
    raise JSRError(status=409, message='Shipment cannot be edited in this state')
  if (row.editing or {}).get('state') in ('pending', 'unknown') or ((row.editing or {}).get('changes') and row.editing.get('state') != 'rejected'):
    raise JSRError(status=409, message='Previous update must be reconciled first')
  body = await build_payload(session, purchase, config, payload)
  if row.request_hash == request_hash(body):
    if selection is not None:
      purchase.delivery = {**selection, 'data': {**selection['data'], **row.details}}
    await session.commit()
    return row
  remote_packages = {package.get('number'): package for package in entity.get('packages') or []}
  patch = {key: value for key, value in body.items() if key not in ('number', 'packages')}
  patch['uuid'] = row.remote_uuid
  packages = []
  for package in body['packages']:
    remote_package = remote_packages.get(package['number'], {})
    package_id = remote_package.get('package_id')
    if package_id:
      packages.append({**package, 'package_id': package_id})
    elif any(remote_package.get(key) != value for key, value in package.items()):
      error = PackageRegistrationPending if row.registration.get('state') in ('accepted', 'pending') else JSRError
      raise error(status=409, message='СДЭК ещё не выдал идентификатор грузового места. Вес, габариты и состав можно изменить после подтверждения регистрации.')
  if packages:
    patch['packages'] = packages
  row.editing = {'state': 'pending', 'errors': []}
  await session.commit()
  try:
    async with CdekClient(config) as client:
      result = await client.request('PATCH', '/v2/orders', json=patch)
    row.editing = summary(result, ('UPDATE', 'EDIT'))
  except CdekError as exc:
    row.editing = failure(exc)
    await session.commit()
    raise
  if row.editing['state'] == 'success':
    row.waybill, row.barcode = {}, {}
    save_details(row, purchase, payload, body, config)
  elif row.editing['state'] != 'rejected':
    row.editing = {**row.editing, 'changes': shipment_details(payload, body, config),
      'request_hash': request_hash(body)}
    if selection is not None:
      row.editing = {**row.editing, 'selection': {**selection, 'data': {**selection['data'], **row.editing['changes']}}}
  if row.editing['state'] == 'success' and selection is not None:
    purchase.delivery = {**selection, 'data': {**selection['data'], **row.details}}
  await session.commit()
  await session.refresh(row)
  return row


async def save_purchase_delivery(session, purchase_id, value):
  from pydantic import ValidationError
  from src.schemas.delivery import ShipmentRequest
  from src.schemas.contact import normalize_contact_info
  from src.services.integrations import delivery_selection
  purchase = await lock_purchase(session, purchase_id)
  row = await session.scalar(select(DeliveryShipment).where(DeliveryShipment.purchase_id == purchase_id))
  selection = await delivery_selection(session, value)
  retry = bool(row and row.status == 'rejected' and not row.remote_uuid)
  if row and (not selection or selection['module'] != row.provider):
    raise JSRError(status=409, message='Нельзя сменить службу доставки созданного отправления')
  if selection and selection['module'] == 'cdek':
    previous = purchase.delivery or {}
    selection['data'] = {**(row.details if row else {}),
      **(previous.get('data', {}) if previous.get('module') == 'cdek' else {}), **selection['data']}
    data = selection['data']
    data.pop('cdek_package_draft', None)
    ready = data.get('reviewed_and_packed') is True and data.get('recipient_collection_confirmed') is True
    if (row and not retry) or ready:
      contact = normalize_contact_info(purchase.contact_info)
      data.setdefault('recipient', {key: value for key, value in {
        'name': contact.get('name'), 'email': contact.get('email'),
        'phones': [{'number': contact.get('phone')}],
      }.items() if value is not None})
      try:
        payload = ShipmentRequest.model_validate({key: val for key, val in data.items() if key in ShipmentRequest.model_fields})
      except ValidationError as exc:
        raise JSRError('bad_request', message='Проверьте данные получателя, адрес, упаковку и подтверждения') from exc
      if row and not retry:
        try:
          await update_shipment(session, purchase_id, payload, selection=selection)
        except PackageRegistrationPending:
          data['cdek_package_draft'] = True
          purchase.delivery = selection
          await session.commit()
          await session.refresh(purchase)
          return purchase
        return purchase
      else:
        purchase.delivery = selection
        await create_shipment(session, purchase_id, payload, retry_rejected=retry)
        return purchase
  purchase.delivery = selection
  await session.commit()
  await session.refresh(purchase)
  return purchase


async def shipment_operation(session, purchase_id, operation, *, payload=None):
  _, config, _ = await configuration(session, require_enabled=True)
  purchase = await lock_purchase(session, purchase_id)
  row = await shipment_for_purchase(session, purchase_id)
  check_identity(row, config)
  field = {'cancel': 'cancellation', 'intake': 'pickup', 'waybill': 'waybill', 'barcode': 'barcode'}.get(operation)
  if not field:
    raise ValueError('Unsupported shipment operation')
  if not row.remote_uuid:
    raise JSRError(status=409, message='Shipment must be reconciled first')
  is_document = operation in ('waybill', 'barcode')
  editing = row.editing or {}
  if (is_document or operation == 'cancel') and (editing.get('state') in ('pending', 'unknown')
    or (editing.get('changes') and editing.get('state') != 'rejected')):
    raise JSRError(status=409, message='Дождитесь подтверждения изменения отправления в СДЭК')
  if is_document:
    if has_delivery_draft(purchase):
      raise JSRError(status=409, message='Сначала отправьте сохранённые изменения в СДЭК')
    if (row.cancellation or {}).get('state') not in (None, 'rejected') or row.status == 'REMOVED':
      raise JSRError(status=409, message='Печать недоступна после запроса на отмену отправления')
    if not row.tracking_number:
      raise JSRError(status=409, message='CDEK waybill number is not assigned yet; refresh shipment before printing')
    if (row.registration or {}).get('state') != 'success':
      raise JSRError(status=409, message='СДЭК ещё не подтвердил регистрацию отправления. Обновите статус перед печатью.')
  previous = getattr(row, field) or {}
  retryable_states = ('rejected', 'removed') if is_document else ('rejected',)
  if previous and previous.get('state') not in retryable_states:
    return previous
  if operation == 'cancel':
    method, path, body = 'DELETE', f'/v2/orders/{row.remote_uuid}', None
  elif operation in ('waybill', 'barcode'):
    method, path = 'POST', '/v2/print/' + ('orders' if operation == 'waybill' else 'barcodes')
    body = {'orders': [{'order_uuid': row.remote_uuid}], 'copy_count': 1}
  else:
    if not config.from_location or not config.from_location.address or not config.sender:
      raise JSRError(status=409, message='Pickup requires sender address and contact')
    method, path = 'POST', '/v2/intakes'
    body = dict(payload, order_uuid=row.remote_uuid,
      sender={'name': config.sender.name, 'phones': [p.model_dump() for p in config.sender.phones]},
      from_location=config.from_location.model_dump(exclude_none=True))
  setattr(row, field, {'state': 'pending', 'errors': []})
  await session.commit()
  try:
    async with CdekClient(config) as client:
      result = await client.request(method, path, json=body)
    value = summary(result)
    if operation != 'cancel':
      value['uuid'] = uuid_from(result)
  except CdekError as exc:
    setattr(row, field, failure(exc))
    await session.commit()
    raise
  setattr(row, field, value)
  await session.commit()
  return value


async def document(session, purchase_id, kind, *, pdf=False):
  _, config, _ = await configuration(session)
  await lock_purchase(session, purchase_id)
  row = await shipment_for_purchase(session, purchase_id)
  check_identity(row, config)
  operation = getattr(row, kind) or {}
  if not operation.get('uuid'):
    raise JSRError(status=409, message='Document is not registered')
  path = '/v2/print/' + ('orders' if kind == 'waybill' else 'barcodes') + '/' + operation['uuid']
  async with CdekClient(config) as client:
    result = await client.request('GET', path)
    state = summary(result)
    setattr(row, kind, state)
    await session.commit()
    if not pdf:
      return state
    if state['state'] != 'ready':
      raise JSRError(status=409, message='CDEK document is not ready; see document state and errors')
    return await client.request('GET', path + '.pdf', pdf=True)


async def run_cdek_sync():
  logger = logging.getLogger('uvicorn.error')
  while True:
    await asyncio.sleep(settings.CDEK_SYNC_INTERVAL)
    try:
      async with session_maker() as session:
        ids = list((await session.execute(select(DeliveryShipment.purchase_id).where(
          DeliveryShipment.provider == 'cdek', DeliveryShipment.status.not_in(
            ('DELIVERED', 'NOT_DELIVERED', 'REMOVED', 'rejected'))))).scalars())
      for purchase_id in ids:
        try:
          async with session_maker() as session:
            await refresh_shipment(session, purchase_id)
        except Exception as exc:
          logger.warning('CDEK shipment %s sync failed (%s)', purchase_id, type(exc).__name__)
    except Exception as exc:
      logger.warning('CDEK sync failed (%s)', type(exc).__name__)


