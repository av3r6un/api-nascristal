from typing import Any

from pydantic import RootModel


class I18nPatchResponse(RootModel[dict[str, Any]]):
  pass
