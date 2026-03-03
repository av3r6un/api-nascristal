from datetime import datetime as dt
import enum

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Enum, Integer, JSON, Text, String, ForeignKey

from .base import Base

class PageStatus(enum.Enum):
  DRAFT = 'draft'
  PUBLISHED = 'published'


class StaticPage(Base):
  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  slug: Mapped[str] = mapped_column(String(25), unique=True, nullable=False)
  status: Mapped[PageStatus] = mapped_column(Enum(PageStatus), nullable=False, server_default=PageStatus.DRAFT.name)
  translations: Mapped[list["StaticPagesTranslation"]] = relationship(
    back_populates="page",
    cascade="all, delete-orphan",
    lazy="selectin",
  )
  
  def __init__(self, slug, **kwargs) -> None:
    self.slug = slug
    self.status = PageStatus(kwargs.get('status')).name if kwargs.get('status') else None
  
  @property
  def json(self):
    return dict(id=self.id, slug=self.slug, status=self.status.value)


class StaticPagesTranslation(Base):
  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  page_id: Mapped[int] = mapped_column(Integer, ForeignKey('static_pages.id'), nullable=False)
  page: Mapped["StaticPage"] = relationship(back_populates="translations")
  locale: Mapped[str] = mapped_column(String(2), nullable=False)
  title: Mapped[str] = mapped_column(String(255), nullable=False) #
  description: Mapped[str | None] = mapped_column(Text, nullable=True) # with toggle
  meta_title: Mapped[str] = mapped_column(String(255), nullable=False) 
  meta_description: Mapped[str | None] = mapped_column(Text, nullable=True)
  og_image: Mapped[str | None] = mapped_column(String(255), nullable=True) #
  content: Mapped[dict | None] = mapped_column(JSON, nullable=True)

  def __init__(self, page_id: int, locale: str, title: str, content: dict = None, **kwargs) -> None:
    self.page_id = page_id
    self.locale = locale
    self.title = title
    self.content = content
    self.description = kwargs.get('description')
    self.meta_title = kwargs.get('meta_title', title)
    self.meta_description = kwargs.get('meta_description', kwargs.get('description'))
    self.og_image = kwargs.get('og_image')
  
  @property
  def json(self):
    return dict(
      id=self.id, page_id=self.page_id, locale=self.locale, title=self.title, description=self.description,
      meta_title=self.meta_title, meta_description=self.meta_description, og_image=self.og_image, content=self.content
    )
  
    
