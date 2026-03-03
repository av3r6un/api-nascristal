from typing import Any

from pydantic import RootModel


class CatalogResponse(RootModel[list[dict]]):
  pass
