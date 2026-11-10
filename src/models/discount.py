from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Discount(Base):
  id: Mapped[int] = mapped_column(primary_key=True)
  uuid: Mapped[UUID] = mapped_column(Uuid, unique=True)
  name: Mapped[str] = mapped_column(String(255))
  active: Mapped[bool]
  all_products: Mapped[bool]
  amount: Mapped[Decimal] = mapped_column(Numeric(9, 6))


class DiscountProduct(Base):
  __table_args__ = (
    UniqueConstraint('discount_id', 'entity_type', 'entity_uuid', name='uq_discount_products_scope'),
    Index('ix_discount_products_entity', 'entity_type', 'entity_uuid'),
    Base.__table_args__,
  )

  id: Mapped[int] = mapped_column(primary_key=True)
  discount_id: Mapped[int] = mapped_column(ForeignKey('discounts.id', ondelete='CASCADE'))
  entity_type: Mapped[str] = mapped_column(String(32))
  entity_uuid: Mapped[UUID] = mapped_column(Uuid)
