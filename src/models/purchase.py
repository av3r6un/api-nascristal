import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class PurchaseStatus(enum.Enum):
  CREATED = "created"
  AWAITING_PAYMENT = "awaiting_payment"
  PROCESSING = "processing"
  DELIVERING = "delivering"
  FINISHED = "finished"


class Purchase(Base):
  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  uuid: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True, default=lambda: str(uuid.uuid4()))
  payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"), nullable=True, index=True)
  product_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
  properties: Mapped[dict[str, list[str]]] = mapped_column(JSON, nullable=False, default=dict)
  product_quantities: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False, default=dict)
  quantity: Mapped[int] = mapped_column(Integer, nullable=False)
  contact_info: Mapped[dict] = mapped_column(JSON, nullable=False)
  final_price: Mapped[int] = mapped_column(Integer, nullable=False)
  status: Mapped[PurchaseStatus] = mapped_column(
    Enum(PurchaseStatus),
    nullable=False,
    default=PurchaseStatus.CREATED,
    server_default=PurchaseStatus.CREATED.name,
  )
  payment: Mapped["Payment | None"] = relationship("Payment", lazy="selectin")

  def __init__(
    self,
    product_ids: list[int],
    properties: dict[str, list[str]],
    product_quantities: dict[str, int],
    quantity: int,
    contact_info: dict,
    final_price: int,
    payment_id: int | None = None,
    purchase_uuid: str | None = None,
    status: PurchaseStatus | str = PurchaseStatus.CREATED,
    **kwargs,
  ) -> None:
    self.uuid = purchase_uuid or str(uuid.uuid4())
    self.payment_id = payment_id
    self.product_ids = product_ids
    self.properties = properties
    self.product_quantities = product_quantities
    self.quantity = quantity
    self.contact_info = contact_info
    self.final_price = final_price
    self.status = self._coerce_status(status)

  @staticmethod
  def _coerce_status(status: PurchaseStatus | str) -> PurchaseStatus:
    if isinstance(status, PurchaseStatus):
      return status
    return PurchaseStatus(status)

  @property
  def json(self) -> dict:
    return dict(
      id=self.id, uuid=self.uuid, payment_id=self.payment_id, product_ids=self.product_ids,
      properties=self.properties, product_quantities=self.product_quantities,
      quantity=self.quantity, contact_info=self.contact_info, final_price=self.final_price,
      status=self.status.value, created_ts=self.created_ts, updated_ts=self.updated_ts
    )
