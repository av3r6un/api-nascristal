import asyncio
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from uuid import UUID

from src.core.config import settings
from src.services.moysklad_client import MoySkladClient


SUBSCRIPTIONS = tuple(
  (entity, action)
  for entity in ('product', 'variant', 'customerorder')
  for action in ('CREATE', 'UPDATE', 'DELETE')
)
registration_lock = asyncio.Lock()


def callback_url() -> str:
  if not settings.MOYSKLAD_WEBHOOK_URL or not settings.MOYSKLAD_WEBHOOK_SECRET or not settings.MOYSKLAD_ACCOUNT_ID:
    raise ValueError('Webhook URL, secret and account ID must be configured')
  UUID(settings.MOYSKLAD_ACCOUNT_ID)
  parsed = urlsplit(settings.MOYSKLAD_WEBHOOK_URL)
  if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
      or parsed.query or parsed.fragment or parsed.path != '/webhooks/moysklad'):
    raise ValueError('Webhook URL must be an HTTPS URL ending in /webhooks/moysklad without query parameters')
  result = urlunsplit(parsed._replace(query=urlencode({'secret': settings.MOYSKLAD_WEBHOOK_SECRET})))
  if len(result) > 255:
    raise ValueError('Webhook URL exceeds 255 characters')
  return result


def belongs_to_app(hook: dict, expected_url: str, *, stock: bool = False) -> bool:
  actual, expected = urlsplit(hook.get('url', '')), urlsplit(expected_url)
  query = parse_qs(actual.query)
  # Same endpoint also recognises an old token parameter or a rotated secret.
  # A moved endpoint is recognised only with this installation's secret.
  same_endpoint = actual.netloc == expected.netloc and actual.path.rstrip('/') == expected.path
  same_secret = settings.MOYSKLAD_WEBHOOK_SECRET in query.get('secret', []) + query.get('token', [])
  matches_type = (hook.get('stockType') == 'stock' and hook.get('reportType') == 'all') if stock else (
    hook.get('entityType'), hook.get('action')
  ) in SUBSCRIPTIONS
  return (same_endpoint or (actual.path.rstrip('/') == expected.path and same_secret)) and matches_type


async def manage_stock_webhook(client: MoySkladClient, expected_url: str, operation: str) -> dict:
  hooks = [hook async for hook in client.iter_entities('webhookstock')
    if belongs_to_app(hook, expected_url, stock=True)]
  created = updated = 0
  if not hooks and operation in ('startup', 'connect'):
    await client.create('webhookstock', dict(
      url=expected_url, stockType='stock', reportType='all', enabled=True,
    ))
    created = 1
  for hook in hooks:
    changes = {}
    if operation in ('startup', 'connect'):
      changes['url'] = expected_url
    if operation in ('connect', 'disconnect'):
      changes['enabled'] = operation == 'connect'
    changes = {key: value for key, value in changes.items() if hook.get(key) != value}
    if changes:
      await client.update('webhookstock', hook['id'], changes)
      updated += 1
  if operation != 'status':
    hooks = [hook async for hook in client.iter_entities('webhookstock')
      if belongs_to_app(hook, expected_url, stock=True)]
  return dict(
    entity_type='stock', action='UPDATE', registered=bool(hooks),
    enabled=any(hook.get('enabled') is True for hook in hooks),
    configured=any(hook.get('url') == expected_url for hook in hooks),
    count=len(hooks), created=created, updated=updated,
  )


async def manage_webhooks(client: MoySkladClient, operation: str = 'status') -> dict:
  """Reconcile only this installation's subscriptions; preserve manual disabling on startup."""
  expected_url = callback_url()
  hooks = [hook async for hook in client.iter_entities('webhook')]
  owned = [hook for hook in hooks if belongs_to_app(hook, expected_url)]
  created = updated = 0
  if operation != 'status':
    for entity, action in SUBSCRIPTIONS:
      matches = [hook for hook in owned if hook.get('entityType') == entity and hook.get('action') == action]
      if not matches and operation in ('startup', 'connect'):
        payload = dict(url=expected_url, entityType=entity, action=action, method='POST', enabled=True)
        if action == 'UPDATE':
          payload['diffType'] = 'FIELDS'
        await client.create('webhook', payload)
        created += 1
      for hook in matches:
        changes = {}
        if operation != 'disconnect':
          changes = dict(url=expected_url, method='POST')
          if action == 'UPDATE':
            changes['diffType'] = 'FIELDS'
        if operation in ('connect', 'disconnect'):
          changes['enabled'] = operation == 'connect'
        changes = {key: value for key, value in changes.items() if hook.get(key) != value}
        if changes:
          await client.update('webhook', hook['id'], changes)
          updated += 1
    hooks = [hook async for hook in client.iter_entities('webhook')]
    owned = [hook for hook in hooks if belongs_to_app(hook, expected_url)]
  subscriptions = []
  for entity, action in SUBSCRIPTIONS:
    matches = [hook for hook in owned if hook.get('entityType') == entity and hook.get('action') == action]
    subscriptions.append(dict(
      entity_type=entity, action=action, registered=bool(matches),
      enabled=any(hook.get('enabled') is True for hook in matches),
      configured=any(hook.get('url') == expected_url and hook.get('method') == 'POST'
        and (action != 'UPDATE' or hook.get('diffType') == 'FIELDS') for hook in matches),
      count=len(matches),
    ))
  stock = await manage_stock_webhook(client, expected_url, operation)
  created += stock.pop('created')
  updated += stock.pop('updated')
  subscriptions.append(stock)
  return dict(
    expected=len(subscriptions), registered=sum(item['registered'] for item in subscriptions),
    enabled=sum(item['enabled'] for item in subscriptions), created=created, updated=updated,
    subscriptions=subscriptions,
  )
