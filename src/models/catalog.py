from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Category(Base):
  __tablename__ = "categories"

  uid: Mapped[str] = mapped_column(String(8), primary_key=True)
  index: Mapped[int] = mapped_column(Integer, nullable=False)
  icon: Mapped[str] = mapped_column(String(25), nullable=False, default="diamond", server_default="diamond")
  translations: Mapped[list["CategoryTranslation"]] = relationship(
    back_populates="category",
    cascade="all, delete-orphan",
    lazy="selectin",
  )

  def __init__(self, uid: str, index: int, icon: str = "diamond", **kwargs) -> None:
    self.uid = uid
    self.index = index
    self.icon = icon

  @classmethod
  async def next_index(cls, session: AsyncSession) -> int:
    query = select(func.coalesce(func.max(cls.index), 0) + 1)
    result = await session.execute(query)
    return int(result.scalar_one())

  @property
  def json(self) -> dict:
    return dict(uid=self.uid, index=self.index, icon=self.icon)


class CategoryTranslation(Base):
  __table_args__ = (
    UniqueConstraint("category_uid", "locale", name="uq_category_translations_category_locale"),
  )

  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  category_uid: Mapped[str] = mapped_column(String(8), ForeignKey("categories.uid"), nullable=False)
  category: Mapped["Category"] = relationship(back_populates="translations")
  locale: Mapped[str] = mapped_column(String(2), nullable=False)
  name: Mapped[str] = mapped_column(String(255), nullable=False)
  description: Mapped[str | None] = mapped_column(Text, nullable=True)

  def __init__(self, category_uid: str, locale: str, name: str, description: str | None = None, **kwargs) -> None:
    self.category_uid = category_uid
    self.locale = locale
    self.name = name
    self.description = description

  @property
  def json(self) -> dict:
    return dict(
      id=self.id,
      category_uid=self.category_uid,
      locale=self.locale,
      name=self.name,
      description=self.description,
    )


class Color(Base):
  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  sku: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
  name: Mapped[str] = mapped_column(String(100), nullable=False)

  def __init__(self, sku: str, name: str, **kwargs) -> None:
    self.sku = sku
    self.name = name

  @property
  def json(self) -> dict:
    return dict(id=self.id, sku=self.sku, name=self.name)


class Size(Base):
  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  sku: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
  size_min: Mapped[int] = mapped_column(Integer, nullable=False)
  size_max: Mapped[int] = mapped_column(Integer, nullable=False)

  def __init__(self, sku: str, size_min: int, size_max: int, **kwargs) -> None:
    self.sku = sku
    self.size_min = size_min
    self.size_max = size_max

  @property
  def json(self) -> dict:
    return dict(id=self.id, sku=self.sku, size_min=self.size_min, size_max=self.size_max)
