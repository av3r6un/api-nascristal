from typing import Any

from pydantic import BaseModel

class StaticPageResponse(BaseModel):
  id: int
  page_id: int
  locale: str
  title: str
  description: str | None
  meta_title: str
  meta_description: str | None
  og_image: str | None
  content: dict[str, Any] | None


class StaticPageListItem(BaseModel):
  id: int
  slug: str
  status: str
  locale: str
  title: str
  description: str | None
  meta_title: str
  meta_description: str | None
  og_image: str | None
  content: dict[str, Any] | None


class StaticPagesResponse(BaseModel):
  items: list[StaticPageListItem]

class StaticPageRequest(BaseModel):
  slug: str
  locale: str
  title: str
  meta_title: str
  status: str
  description: str | None
  meta_description: str | None
  og_image: str | None
  content: dict[str, Any] | None
