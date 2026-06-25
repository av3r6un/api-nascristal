import enum
import uuid

from sqlalchemy import Boolean, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PaymentProvider(enum.Enum):
  YOOKASSA = "yookassa"


class PaymentStatus(enum.Enum):
  PENDING = "pending"
  WAITING_FOR_CAPTURE = "waiting_for_capture"
  SUCCEEDED = "succeeded"
  CANCELED = "canceled"
  FAILED = "failed"


class Payment(Base):
  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  uuid: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True, default=lambda: str(uuid.uuid4()))
  provider: Mapped[str] = mapped_column(String(32), nullable=False, default=PaymentProvider.YOOKASSA.value)
  idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
  external_payment_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
  status: Mapped[str] = mapped_column(String(32), nullable=False, default=PaymentStatus.PENDING.value)
  amount_value: Mapped[str] = mapped_column(String(32), nullable=False)
  currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")
  paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
  confirmation_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
  return_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
  description: Mapped[str | None] = mapped_column(String(255), nullable=True)
  payment_metadata: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
  request_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
  response_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
  notification_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

  def __init__(
    self,
    idempotency_key: str,
    amount_value: str,
    currency: str = "RUB",
    provider: PaymentProvider | str = PaymentProvider.YOOKASSA,
    status: PaymentStatus | str = PaymentStatus.PENDING,
    paid: bool = False,
    return_url: str | None = None,
    description: str | None = None,
    payment_metadata: dict | None = None,
    request_payload: dict | None = None,
    response_payload: dict | None = None,
    notification_payload: dict | None = None,
    external_payment_id: str | None = None,
    confirmation_url: str | None = None,
    payment_uuid: str | None = None,
    **kwargs,
  ) -> None:
    self.uuid = payment_uuid or str(uuid.uuid4())
    self.provider = self._coerce_provider(provider).value
    self.idempotency_key = idempotency_key
    self.external_payment_id = external_payment_id
    self.status = self._coerce_status(status)
    self.amount_value = amount_value
    self.currency = currency
    self.paid = paid
    self.confirmation_url = confirmation_url
    self.return_url = return_url
    self.description = description
    self.payment_metadata = payment_metadata or {}
    self.request_payload = request_payload or {}
    self.response_payload = response_payload or {}
    self.notification_payload = notification_payload or {}

  @staticmethod
  def _coerce_provider(provider: PaymentProvider | str) -> PaymentProvider:
    if isinstance(provider, PaymentProvider):
      return provider
    return PaymentProvider(provider)

  @staticmethod
  def _coerce_status(status: PaymentStatus | str) -> str:
    if isinstance(status, PaymentStatus):
      return status.value
    return PaymentStatus(status).value

  @property
  def json(self) -> dict:
    return dict(
      id=self.id,
      uuid=self.uuid,
      provider=self.provider,
      idempotency_key=self.idempotency_key,
      external_payment_id=self.external_payment_id,
      status=self.status,
      amount_value=self.amount_value,
      currency=self.currency,
      paid=self.paid,
      confirmation_url=self.confirmation_url,
      return_url=self.return_url,
      description=self.description,
      metadata=self.payment_metadata,
      request_payload=self.request_payload,
      response_payload=self.response_payload,
      notification_payload=self.notification_payload,
      created_ts=self.created_ts,
      updated_ts=self.updated_ts,
    )
