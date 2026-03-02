class BaseError(Exception):
  messages = {
      'bad_request': ('Bad request', 400),
      'invalid_payload': ('Invalid payload', 400),
      'unauthorized': ('Unauthorized', 401),
      'token_expired': ('Token expired', 401),
      'token_revoked': ('Token revoked', 401),
      'token_decode_error': ('Token decode Error', 403),
      'forbidden': ('Forbidden', 403),
      'not_found': ('Not found', 404),
      'conflict': ('Conflict', 409),
      'internal': ('Internal server error', 500),
      'login_not_found': ('User is not registered', 404),
      'passwords_mismatch': ('Email or password are incorrect', 400)
  }
  status: int = 400
  message = None

  def __init__(self, message=None, status=None) -> None:
    super().__init__()
    if status:
      self.status = status
    self.message = message

  def make_error(self, error, **kwargs):
    message, status = self.messages[error]
    if status:
      self.status = status
    if not self.message:
      self.message = ' '.join(kwargs.get(word, word) for word in message.split())

  @property
  def json(self):
    return dict(data=dict(status='error', message=self.message), status=self.status)

  def __str__(self):
    return self.message
