from .base import BaseError

class JSRError(BaseError):
  def __init__(self, error: str = 'bad_request', *, status: int | None = None, message: str | None = None, **kwargs) -> None:
    super().__init__(message, status)
    self.make_error(error, **kwargs)
