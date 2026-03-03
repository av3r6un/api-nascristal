import base64
import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from threading import Lock
from xml.etree import ElementTree as ET

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse as PTR


router = APIRouter(prefix='/1c', tags=['1c'])

LOG_DIR = os.getenv('ONEC_LOG_DIR', '/app/logs/1c')
UPLOAD_DIR = os.getenv('ONEC_UPLOAD_DIR', '/app/data/1c_exchange')
AUTH_ENABLED = os.getenv('ONEC_AUTH_ENABLED', '1').strip() not in {'0', 'false', 'False'}
AUTH_USER = os.getenv('ONEC_AUTH_USER', '1c')
AUTH_PASSWORD = os.getenv('ONEC_AUTH_PASSWORD', '1c')
SESSION_COOKIE_NAME = os.getenv('ONEC_SESSION_COOKIE_NAME', 'sessid')
SESSION_TTL_SECONDS = int(os.getenv('ONEC_SESSION_TTL_SECONDS', '3600'))
FILE_LIMIT = int(os.getenv('ONEC_FILE_LIMIT', '104857600'))
ZIP_ENABLED = os.getenv('ONEC_ZIP_ENABLED', 'no').strip().lower() in {'yes', '1', 'true'}

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

_sessions: dict[str, dict] = {}
_sessions_lock = Lock()


def _utc_now() -> datetime:
  return datetime.now(timezone.utc)


def _request_id() -> str:
  return secrets.token_hex(8)


def _log_file_path() -> str:
  return os.path.join(LOG_DIR, f'{_utc_now().strftime("%Y-%m-%d")}.jsonl')


def log_event(event: str, request_id: str, **data) -> None:
  payload = {
    'ts_utc': _utc_now().isoformat(),
    'event': event,
    'request_id': request_id,
    **data,
  }
  line = json.dumps(payload, ensure_ascii=False)
  with open(_log_file_path(), 'a', encoding='utf-8') as f:
    f.write(line + '\n')
  print(line, flush=True)


def _decode_basic_auth(header_value: str | None) -> tuple[str, str] | None:
  if not header_value:
    return None
  if not header_value.lower().startswith('basic '):
    return None
  token = header_value[6:].strip()
  try:
    decoded = base64.b64decode(token, validate=True).decode('utf-8')
  except Exception:
    return None
  if ':' not in decoded:
    return None
  username, password = decoded.split(':', 1)
  return username, password


def _create_session(remote_ip: str) -> str:
  sid = secrets.token_hex(16)
  expires_at = _utc_now() + timedelta(seconds=SESSION_TTL_SECONDS)
  with _sessions_lock:
    _sessions[sid] = {
      'created_at': _utc_now().isoformat(),
      'expires_at': expires_at.isoformat(),
      'remote_ip': remote_ip,
      'files': [],
    }
  return sid


def _session_from_cookie(req: Request) -> str | None:
  sid = req.cookies.get(SESSION_COOKIE_NAME)
  if not sid:
    return None
  with _sessions_lock:
    data = _sessions.get(sid)
    if not data:
      return None
    if _utc_now() > datetime.fromisoformat(data['expires_at']):
      _sessions.pop(sid, None)
      return None
  return sid


def _safe_rel_path(filename: str) -> str:
  normalized = filename.replace('\\', '/').strip().lstrip('/')
  parts = PurePosixPath(normalized).parts
  if not parts:
    raise ValueError('empty filename')
  if any(p in {'.', '..'} for p in parts):
    raise ValueError('path traversal detected')
  return '/'.join(parts)


def _save_uploaded_file(rel_path: str, body: bytes) -> str:
  abs_path = os.path.abspath(os.path.join(UPLOAD_DIR, rel_path))
  root = os.path.abspath(UPLOAD_DIR)
  if not abs_path.startswith(root + os.sep) and abs_path != root:
    raise ValueError('path traversal blocked')
  os.makedirs(os.path.dirname(abs_path), exist_ok=True)
  with open(abs_path, 'wb') as f:
    f.write(body)
  return abs_path


def _file_info(abs_path: str) -> dict:
  size = os.path.getsize(abs_path)
  md5 = hashlib.md5()
  with open(abs_path, 'rb') as f:
    while True:
      chunk = f.read(1024 * 1024)
      if not chunk:
        break
      md5.update(chunk)
  return {
    'size': size,
    'md5': md5.hexdigest(),
  }


def _validate_xml_if_needed(abs_path: str) -> tuple[bool, str]:
  if not abs_path.lower().endswith('.xml'):
    return True, 'non-xml file, skipped xml parse'
  try:
    root = ET.parse(abs_path).getroot()
  except Exception as exc:
    return False, f'xml parse failed: {exc}'
  return True, f'xml root={root.tag}'


def _plain_failure(message: str) -> PTR:
  return PTR(f'failure\n{message}', media_type='text/plain; charset=utf-8')


@router.api_route('/1c_exchange', methods=['GET', 'POST'])
async def exchange(req: Request):
  rid = _request_id()
  params = dict(req.query_params)
  mode = params.get('mode', '').strip().lower()
  exchange_type = params.get('type', '').strip().lower()
  filename = params.get('filename', '').strip()
  body = await req.body()

  log_event(
    'request.received',
    rid,
    method=req.method,
    path=str(req.url.path),
    query=params,
    headers={k: v for k, v in req.headers.items() if k.lower() != 'authorization'},
    body_size=len(body),
    mode=mode,
    exchange_type=exchange_type,
  )

  if mode == 'checkauth':
    if not AUTH_ENABLED:
      sid = _create_session(req.client.host if req.client else 'unknown')
      response = PTR(f'success\n{SESSION_COOKIE_NAME}\n{sid}', media_type='text/plain; charset=utf-8')
      response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=sid,
        httponly=True,
        max_age=SESSION_TTL_SECONDS,
        samesite='lax',
      )
      log_event('checkauth.success.no_auth', rid, session_id=sid)
      return response

    creds = _decode_basic_auth(req.headers.get('authorization'))
    if not creds:
      log_event('checkauth.failure', rid, reason='missing_or_invalid_basic_auth')
      response = _plain_failure('missing basic auth')
      response.status_code = 401
      response.headers['WWW-Authenticate'] = 'Basic realm="1C Exchange"'
      return response

    username, password = creds
    if username != AUTH_USER or password != AUTH_PASSWORD:
      log_event('checkauth.failure', rid, reason='bad_credentials', username=username)
      response = _plain_failure('invalid credentials')
      response.status_code = 401
      response.headers['WWW-Authenticate'] = 'Basic realm="1C Exchange"'
      return response

    sid = _create_session(req.client.host if req.client else 'unknown')
    response = PTR(f'success\n{SESSION_COOKIE_NAME}\n{sid}', media_type='text/plain; charset=utf-8')
    response.set_cookie(
      key=SESSION_COOKIE_NAME,
      value=sid,
      httponly=True,
      max_age=SESSION_TTL_SECONDS,
      samesite='lax',
    )
    log_event('checkauth.success', rid, session_id=sid, username=username)
    return response

  sid = _session_from_cookie(req)
  if not sid:
    log_event('session.failure', rid, reason='missing_or_expired_cookie', cookie_name=SESSION_COOKIE_NAME)
    response = _plain_failure('session is not valid, run mode=checkauth')
    response.status_code = 401
    return response

  if mode == 'init':
    zip_value = 'yes' if ZIP_ENABLED else 'no'
    log_event('init.success', rid, session_id=sid, zip=zip_value, file_limit=FILE_LIMIT)
    return PTR(f'zip={zip_value}\nfile_limit={FILE_LIMIT}', media_type='text/plain; charset=utf-8')

  if mode == 'file':
    if req.method != 'POST':
      log_event('file.failure', rid, session_id=sid, reason='method_not_allowed')
      return _plain_failure('mode=file requires POST')
    if not filename:
      log_event('file.failure', rid, session_id=sid, reason='missing_filename')
      return _plain_failure('filename is required')
    if len(body) > FILE_LIMIT:
      log_event('file.failure', rid, session_id=sid, reason='chunk_too_large', body_size=len(body), file_limit=FILE_LIMIT)
      return _plain_failure('chunk exceeds file_limit')
    try:
      rel_path = _safe_rel_path(filename)
      abs_path = _save_uploaded_file(rel_path, body)
    except ValueError as exc:
      log_event('file.failure', rid, session_id=sid, reason='invalid_filename', detail=str(exc), filename=filename)
      return _plain_failure(str(exc))

    info = _file_info(abs_path)
    with _sessions_lock:
      entry = _sessions.get(sid)
      if entry is not None:
        if rel_path not in entry['files']:
          entry['files'].append(rel_path)
    log_event(
      'file.success',
      rid,
      session_id=sid,
      filename=filename,
      stored_as=rel_path,
      absolute_path=abs_path,
      body_size=len(body),
      file_size=info['size'],
      md5=info['md5'],
    )
    return PTR('success', media_type='text/plain; charset=utf-8')

  if mode == 'import':
    if not filename:
      log_event('import.failure', rid, session_id=sid, reason='missing_filename')
      return _plain_failure('filename is required')
    try:
      rel_path = _safe_rel_path(filename)
    except ValueError as exc:
      log_event('import.failure', rid, session_id=sid, reason='invalid_filename', detail=str(exc), filename=filename)
      return _plain_failure(str(exc))

    abs_path = os.path.abspath(os.path.join(UPLOAD_DIR, rel_path))
    if not os.path.exists(abs_path):
      log_event('import.failure', rid, session_id=sid, reason='file_not_found', filename=filename, absolute_path=abs_path)
      return _plain_failure('file not found, upload first via mode=file')

    info = _file_info(abs_path)
    xml_ok, xml_message = _validate_xml_if_needed(abs_path)
    if not xml_ok:
      log_event('import.failure', rid, session_id=sid, reason='xml_invalid', filename=filename, detail=xml_message)
      return _plain_failure(xml_message)

    log_event(
      'import.success',
      rid,
      session_id=sid,
      filename=filename,
      absolute_path=abs_path,
      file_size=info['size'],
      md5=info['md5'],
      xml=xml_message,
      exchange_type=exchange_type,
    )
    return PTR('success', media_type='text/plain; charset=utf-8')

  if mode == 'query':
    # Sale exchange (orders) stub: return empty but valid XML envelope.
    payload = '<?xml version="1.0" encoding="UTF-8"?><КоммерческаяИнформация ВерсияСхемы="2.10"></КоммерческаяИнформация>'
    log_event('query.success', rid, session_id=sid, exchange_type=exchange_type, note='returned empty orders payload')
    return PTR(payload, media_type='application/xml; charset=utf-8')

  if mode == 'success':
    log_event('success.ack', rid, session_id=sid, exchange_type=exchange_type)
    return PTR('success', media_type='text/plain; charset=utf-8')

  log_event('mode.failure', rid, session_id=sid, reason='unsupported_mode', mode=mode)
  return _plain_failure(f'unsupported mode: {mode or "empty"}')
