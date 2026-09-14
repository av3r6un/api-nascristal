from __future__ import annotations

from datetime import datetime as dt
from decimal import Decimal
from typing import List
import uuid

from sqlalchemy import Boolean, Double, Integer, String, Uuid, Text, ForeignKey, DateTime, DECIMAL, UniqueConstraint, false, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Product(Base):
  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  uuid: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, unique=True)
  sku: Mapped[str | None] = mapped_column(String(25), nullable=True)
  name: Mapped[str] = mapped_column(String(50), nullable=False)
  description: Mapped[str | None] = mapped_column(Text, nullable=True)
  code: Mapped[str] = mapped_column(String(15), nullable=False, unique=True)
  external_code: Mapped[str] = mapped_column(String(24), nullable=False)
  category_id: Mapped[int] = mapped_column(Integer, ForeignKey('categories.id'))
  server_updated: Mapped[dt] = mapped_column(DateTime, nullable=False)
  archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
  
  category: Mapped[Category] = relationship("Category", back_populates="products", lazy="selectin")
  variants: Mapped[List[ProductVariant]] = relationship("ProductVariant", back_populates="product", lazy="selectin") # type: ignore
  
  @property
  def json(self):
    return dict(
      id=self.id, uuid=self.uuid, sku=self.sku, name=self.name, description=self.description, archived=self.archived,
      category=self.category.json, variants=[a.json for a in self.variants], images=[]
    )
  

class ProductVariant(Base):
  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  uuid: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, unique=True)
  product_id: Mapped[int] = mapped_column(Integer, ForeignKey('products.id'), nullable=False)
  name: Mapped[str] = mapped_column(String(50), nullable=False)
  code: Mapped[str] = mapped_column(String(15), nullable=False, unique=True)
  external_code: Mapped[str] = mapped_column(String(24), nullable=False)
  archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
  sku: Mapped[str] = mapped_column(String(48), nullable=False)
  image_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
  
  product: Mapped[Product] = relationship("Product", back_populates='variants', lazy='selectin')
  attributes: Mapped[List[ProductAttribute]] = relationship('ProductAttribute', back_populates='variant', lazy='selectin')
  offer: Mapped[Offer] = relationship("Offer", back_populates="variant", uselist=False)
  
  @property
  def json(self):
    return dict(
      id=self.id, uuid=self.uuid, product_id=self.product.id, name=self.name,
      archived=self.archived, sku=self.sku, attributes=[a.json for a in self.attributes],
      offer=self.offer.json
    )


class Offer(Base):
  __table_args__ = (
    UniqueConstraint("variant_id", name="uq_offers_variant_id"),
  )
  
  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  variant_id: Mapped[int] = mapped_column(Integer, ForeignKey('product_variants.id'), nullable=False, index=True)
  amount: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False, default=Decimal("0.00"), server_default="0.00")
  is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
  quantity: Mapped[float] = mapped_column(Double, nullable=False, default=0, server_default="0")
  
  variant: Mapped[ProductVariant] = relationship("ProductVariant", back_populates="offer")
  
  @property
  def json(self):
    return dict(id=self.id, amount=self.amount, is_active=self.is_active, quantity=self.quantity)
  
  
class ProductAttribute(Base):
  __table_args__ = (
    UniqueConstraint('variant_id', 'option_id', name='uq_product_attributes_variant_option'),
  )

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  variant_id: Mapped[int] = mapped_column(Integer, ForeignKey('product_variants.id'), nullable=False)
  option_id: Mapped[int] = mapped_column(Integer, ForeignKey('attribute_options.id'), nullable=False)

  variant: Mapped[ProductVariant] = relationship('ProductVariant', back_populates="attributes", lazy='selectin')
  option: Mapped[AttributeOption] = relationship('AttributeOption', back_populates="product_attributes", lazy='selectin')

  @property
  def json(self):
    return dict(
      id=self.id,
      variant_id=self.variant_id,
      option_id=self.option_id,
      attribute=dict(
        id=self.option.attribute.id,
        uuid=self.option.attribute.uuid,
        name=self.option.attribute.name,
      ),
      value=self.option.value,
      label=self.option.label,
    )
  

class Attribute(Base):
  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  uuid: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, unique=True)
  name: Mapped[str] = mapped_column(String(25), nullable=False)

  options: Mapped[List[AttributeOption]] = relationship('AttributeOption', back_populates='attribute', lazy='selectin')

  @property
  def json(self):
    return dict(
      id=self.id,
      uuid=self.uuid,
      name=self.name,
      options=[option.json for option in sorted(self.options, key=lambda option: (option.value, option.id))],
    )
  
class AttributeOption(Base):
  __table_args__ = (
    UniqueConstraint('attribute_id', 'value', name='uq_attribute_options_attribute_value'),
  )
  
  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  attribute_id: Mapped[int] = mapped_column(Integer, ForeignKey('attributes.id'), nullable=False)
  value: Mapped[str] = mapped_column(String(255), nullable=False)
  label: Mapped[str | None] = mapped_column(String(255), nullable=True)

  attribute: Mapped[Attribute] = relationship('Attribute', back_populates='options', lazy='selectin')
  product_attributes: Mapped[List[ProductAttribute]] = relationship(
    'ProductAttribute',
    back_populates='option',
    lazy='selectin',
  )
  
  @property
  def json(self):
    return dict(id=self.id, attribute_id=self.attribute_id, value=self.value, label=self.label)
  

class Category(Base):
  __tablename__ = "categories"
  
  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  name: Mapped[str] = mapped_column(String(50), nullable=False)
  sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0") 
  
  products: Mapped[List[Product]] = relationship('Product', back_populates="category", lazy='selectin')
  
  @property
  def json(self):
    return dict(id=self.id, name=self.name, sort_order=self.sort_order)
  

