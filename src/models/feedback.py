from datetime import datetime as dt

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, Integer, Boolean

from .base import Base


class Feedback(Base):
  
  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  name: Mapped[str] = mapped_column(String(100), nullable=False)
  email: Mapped[str] = mapped_column(String(100), nullable=False)
  message: Mapped[str] = mapped_column(Text, nullable=False)
  processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
  
  def __init__(self, name, email, message, **kwargs) -> None:
    self.name = name
    self.email = email
    self.message = message
  
  @property
  def json(self):
    return dict(id=self.id, name=self.name, email=self.email, processed=self.processed)
  
  async def was_processed(self, session):
    self.processed = True
    await self.save(session)
  
    