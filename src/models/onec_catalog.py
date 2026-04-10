from __future__ import annotations

from datetime import datetime as dt
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from .base import Base


def uuid1_str() -> str:
  return str(uuid.uuid1())


class OneCImportRuns(Base):
  __tablename__ = "onec_import_runs"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  exchange_type: Mapped[str] = mapped_column(String(32), nullable=False)
  classifier_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
  source_md5: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
  status: Mapped[str] = mapped_column(String(32), nullable=False)
  started_at: Mapped[dt] = mapped_column(DateTime, nullable=False, server_default=func.now(), default=func.now)
  finished_at: Mapped[dt | None] = mapped_column(DateTime, nullable=True)
  products: Mapped[list["Product"]] = relationship(back_populates="last_seen_import_run")
  
  @classmethod
  async def latest(cls, session) -> OneCImportRuns:
    all_runs = await cls.all(session, status='success')
    sorted_runs = sorted(all_runs, key=lambda x: x.id, reverse=True)
    return sorted_runs[0]


class Category(Base):
  __tablename__ = "categories"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  eid: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
  parent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("categories.id"), nullable=True)
  name: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
  index: Mapped[int] = mapped_column(Integer, nullable=False)
  icon: Mapped[str] = mapped_column(String(25), nullable=False, default="diamond", server_default="diamond")

  parent: Mapped["Category | None"] = relationship(remote_side=[id], back_populates="children")
  children: Mapped[list["Category"]] = relationship(back_populates="parent")
  properties: Mapped[list["Property"]] = relationship(back_populates="parent_category")
  products: Mapped[list["Product"]] = relationship("Product", back_populates="category")
  uid = synonym("eid")

  def __init__(
    self,
    eid: str | None = None,
    index: int = 0,
    icon: str = "diamond",
    name: str = "",
    parent_id: int | None = None,
    uid: str | None = None,
    **kwargs,
  ) -> None:
    self.eid = eid or uid or ""
    self.index = index
    self.icon = icon
    self.name = name
    self.parent_id = parent_id

  @classmethod
  async def create_uid(cls, session: AsyncSession):
    return str(uuid.uuid1())

  @classmethod
  async def next_index(cls, session: AsyncSession) -> int:
    query = select(func.coalesce(func.max(cls.index), 0) + 1)
    result = await session.execute(query)
    return int(result.scalar_one())

  @property
  def json(self) -> dict:
    return dict(id=self.id, eid=self.eid, uid=self.eid, parent_id=self.parent_id, name=self.name, index=self.index, icon=self.icon)


class Property(Base):
  __tablename__ = "properties"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  eid: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
  parent_category_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("categories.id"), nullable=True, index=True)
  index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
  name: Mapped[str] = mapped_column(String(255), nullable=False)
  is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")

  parent_category: Mapped["Category | None"] = relationship(back_populates="properties")
  options: Mapped[list["PropertyOption"]] = relationship(
    back_populates="property",
    cascade="all, delete-orphan",
  )
  attributes: Mapped[list["ProductAttribute"]] = relationship(back_populates="property")


class PropertyOption(Base):
  __tablename__ = "property_options"
  __table_args__ = (
    UniqueConstraint("property_id", "value", name="uq_property_options_property_value"),
  )

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  eid: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
  property_id: Mapped[int] = mapped_column(Integer, ForeignKey("properties.id"), nullable=False, index=True)
  value: Mapped[str] = mapped_column(String(255), nullable=False)
  name: Mapped[str | None] = mapped_column(String(255), nullable=True)
  icon: Mapped[str | None] = mapped_column(String(255), nullable=True)
  is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")

  property: Mapped["Property"] = relationship(back_populates="options")
  attributes: Mapped[list["ProductAttribute"]] = relationship(back_populates="option")


class Product(Base):
  __tablename__ = "products"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  eid: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
  sku: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
  code: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
  name: Mapped[str] = mapped_column(String(255), nullable=False)
  description: Mapped[str | None] = mapped_column(Text, nullable=True)
  category_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("categories.id"), nullable=True, index=True)
  primary_image: Mapped[str | None] = mapped_column(String(512), nullable=True)
  is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
  last_seen_import_run_id: Mapped[int | None] = mapped_column(
    Integer,
    ForeignKey("onec_import_runs.id"),
    nullable=True,
    index=True,
  )

  category: Mapped["Category | None"] = relationship("Category", back_populates="products")
  last_seen_import_run: Mapped["OneCImportRuns | None"] = relationship(back_populates="products")
  images: Mapped[list["ProductImage"]] = relationship(
    back_populates="product",
    cascade="all, delete-orphan",
  )
  attributes: Mapped[list["ProductAttribute"]] = relationship(
    back_populates="product",
    cascade="all, delete-orphan",
  )
  offers: Mapped[list["Offer"]] = relationship(
    back_populates="product",
    cascade="all, delete-orphan",
  )


class ProductImage(Base):
  __tablename__ = "product_images"
  __table_args__ = (
    UniqueConstraint("product_id", "path", name="uq_product_images_product_path"),
  )

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  eid: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True, default=uuid1_str)
  product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False, index=True)
  path: Mapped[str] = mapped_column(String(512), nullable=False)
  sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
  is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")

  product: Mapped["Product"] = relationship(back_populates="images")


class ProductAttribute(Base):
  __tablename__ = "product_attributes"
  __table_args__ = (
    UniqueConstraint("product_id", "property_id", name="uq_product_attributes_product_property"),
  )

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  eid: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True, default=uuid1_str)
  product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False, index=True)
  property_id: Mapped[int] = mapped_column(Integer, ForeignKey("properties.id"), nullable=False, index=True)
  option_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("property_options.id"), nullable=True, index=True)

  product: Mapped["Product"] = relationship(back_populates="attributes")
  property: Mapped["Property"] = relationship(back_populates="attributes")
  option: Mapped["PropertyOption | None"] = relationship(back_populates="attributes")


class Offer(Base):
  __tablename__ = "offers"
  __table_args__ = (
    UniqueConstraint("product_id", name="uq_offers_product_id"),
  )

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  eid: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
  product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False, index=True)
  quantity: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0, server_default="0")
  unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
  coefficient: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=1, server_default="1")
  is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
  amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0, server_default="0")
  currency: Mapped[str | None] = mapped_column(String(16), nullable=True)

  product: Mapped["Product"] = relationship(back_populates="offers")
