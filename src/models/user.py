from datetime import datetime as dt
import enum

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import DateTime, Enum, String, func

from src.core.security import check_pw, create_token, hash_password
from src.exceptions import JSRError

from .base import Base


class Role(enum.Enum):
  OWNER = "owner"
  MANAGER = "manager"
  DEVELOPER = "developer"
  INTERNAL = "internal"


class User(Base):
  uid: Mapped[str] = mapped_column(String(6), primary_key=True)
  email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
  password: Mapped[str] = mapped_column(String(255), nullable=False)

  role: Mapped[Role] = mapped_column(Enum(Role), nullable=False, default=Role.MANAGER, server_default=Role.MANAGER.value)
  reg_date: Mapped[dt] = mapped_column(DateTime, nullable=False, server_default=func.now())
  last_date: Mapped[dt] = mapped_column(DateTime, nullable=False, server_default=func.now())
  reg_ip: Mapped[str] = mapped_column(String(64), nullable=False)
  last_ip: Mapped[str] = mapped_column(String(64), nullable=False)

  def __init__(self, uid: str, email: str, password: str, reg_ip: str, role: str | Role = Role.MANAGER, **kwargs) -> None:
    self.uid = uid
    self.email = email
    self.password = hash_password(password)
    self.role = role if isinstance(role, Role) else Role(role)
    self.reg_ip = reg_ip
    self.last_ip = reg_ip
    self.reg_date = dt.now()
    self.last_date = dt.now()

  @property
  def info(self) -> dict:
    return dict(uid=self.uid, email=self.email, role=self.role.value)

  @property
  def json(self) -> dict:
    return dict(**self.info, reg_ip=self.reg_ip, reg_date=self.reg_date, last_ip=self.last_ip, last_date=self.last_date)

  @classmethod
  async def login(cls, session, email: str, password: str, last_ip: str, **kwargs) -> dict:
    user = await cls.first(session, email=email)
    if not user:
      raise JSRError("login_not_found")

    info = user._login(password=password, last_ip=last_ip)
    await user.save(session)
    return info

  def _login(self, password: str, last_ip: str) -> dict:
    if not check_pw(password, self.password):
      raise JSRError("passwords_mismatch")

    self.last_ip = last_ip
    self.last_date = dt.now()
    extra = dict(accs_token=create_token(self.uid, fresh=True), rfsh_token=create_token(self.uid, fresh=False))
    return dict(tokens=extra, **self.info)

  def refresh(self) -> dict:
    return dict(accs_token=create_token(self.uid, fresh=True))
