from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class IntegrationConfig(Base):
  code: Mapped[str] = mapped_column(String(32), primary_key=True)
  enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
  config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class DeliveryShipment(Base):
  __table_args__ = (UniqueConstraint('purchase_id', name='uq_delivery_purchase'), Base.__table_args__)
  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  purchase_id: Mapped[int] = mapped_column(ForeignKey('purchases.id'), nullable=False)
  provider: Mapped[str] = mapped_column(String(32), nullable=False)
  account_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
  external_number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
  remote_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True)
  tracking_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
  status: Mapped[str] = mapped_column(String(32), nullable=False, default='draft')
  details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
  request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
  registration: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
  editing: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
  cancellation: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
  pickup: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
  waybill: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
  barcode: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

  @property
  def json(self):
    return dict(id=self.id, purchase_id=self.purchase_id, provider=self.provider,
      external_number=self.external_number,
      remote_uuid=self.remote_uuid, tracking_number=self.tracking_number,
      status=self.status, details=self.details, registration=self.registration,
      editing=self.editing, cancellation=self.cancellation, pickup=self.pickup,
      waybill=self.waybill, barcode=self.barcode,
      created_ts=self.created_ts, updated_ts=self.updated_ts)
