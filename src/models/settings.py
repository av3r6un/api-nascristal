from datetime import datetime as dt
import enum

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Enum, Integer, JSON, Text, String, ForeignKey

from .base import Base

class SettingsKeys(enum.Enum):
  SITE_NAME = 'site_name'
  LOGO_URL = 'logo_url'
  SOCIALS = 'socials'
  CONTACTS = 'contacts'
  SEO = 'seo'
  MAINTENANCE = 'maintenance'
  

class Setting(Base):
  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  key: Mapped[SettingsKeys] = mapped_column(Enum(SettingsKeys), nullable=False)
  value: Mapped[dict | bool] =  mapped_column(JSON, nullable=False, default=False)
  
  def __init__(self, key: str, value: str| dict | bool, **kwargs) -> None:
    self.key = SettingsKeys(key)
    self.value = value
    
  @property
  def json(self):
    return {self.key.value: self.value}
    
