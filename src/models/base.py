from datetime import datetime as dt
from datetime import date
import secrets
import string
import re

from sqlalchemy.ext.asyncio import AsyncSession, AsyncAttrs
from sqlalchemy.orm import mapped_column, selectinload, DeclarativeBase, Mapped, declared_attr
from sqlalchemy import inspect, select, text, func, DateTime, Integer


class Base(AsyncAttrs, DeclarativeBase):
  __abstract__ = True
  __table_args__ = {
    'mysql_default_charset': 'utf8mb4',
    'mysql_collate': 'utf8mb4_general_ci'
  }
  
  created: Mapped[dt] = mapped_column(DateTime, server_default=func.now())
  updated: Mapped[dt] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
  
  @property
  def created_ts(self):
    return int(self.created.timestamp())

  @property
  def updated_ts(self):
    return int(self.updated.timestamp())
  
  @declared_attr
  def __tablename__(cls) -> str:
    return cls.camel_to_snake(cls.__name__) + 's'
 
  @staticmethod 
  def camel_to_snake(string):
    return re.sub(r'(?<!^)(?=[A-Z])', '_', string).lower()

  @classmethod
  def __build_filters(cls, **filters):
    simple, exps = {}, []
    for k, v in filters.items():
      if '__' in k:
        field, op = k.split('__', 1)
        col = getattr(cls, field)
        if op == 'gte': exps.append(col >= v)
        elif op == 'lte': exps.append(col <= v)
        elif op == 'gt': exps.append(col > v)
        elif op == 'lt': exps.append(col < v)
        elif op == 'like': exps.append(col.like(v))
        elif op == 'ilike': exps.append(col.ilike(f'%{v}%'))
        elif op == 'date': exps.append(func.date(col) == v if isinstance(v, date) else date.fromisoformat(v))
        elif op == 'notnull': exps.append(col.isnot(None))
        elif op == 'isnull': exps.append(col.is_(None))
      else:
        simple[k] = v
    return simple, exps

  @classmethod
  async def get(cls, session: AsyncSession, **filters):
    query = select(cls)
    for rel in inspect(cls).relationships:
      query = query.options(selectinload(getattr(cls, rel.key)))
    simple, expressions = cls.__build_filters(**filters)
    query = query.filter_by(**simple) if simple else query.filter(*expressions)
    result = await session.execute(query)
    return result.scalars()

  @classmethod
  async def get_json(cls, session, **filters):
    results = await cls.get(session, **filters)
    return [row.json for row in results]

  @classmethod
  async def get_multi(cls, session: AsyncSession, field: str, variables: list):
    if not getattr(cls, field, None):
      raise AttributeError(f'There is not column: {field}')
    query = select(cls).where(getattr(cls, field).in_(variables))
    result = await session.execute(query)
    return result.scalars().all()

  @classmethod
  async def first(cls, session, **filters):
    return (await cls.get(session, **filters)).first()

  @classmethod
  async def all(cls, session, **filters):
    return (await cls.get(session, **filters)).all()

  @classmethod
  async def truncate(cls, session: AsyncSession):
    await session.execute(text(f'TRUNCATE TABLE {cls.__tablename__}'))
    await session.commit()

  @classmethod
  async def create_uid(cls, session: AsyncSession):
    existing = await session.execute(select(cls.uid))
    uids = set(existing.scalars().all())
    alp = string.ascii_letters + string.digits
    while True:
      uid = ''.join(secrets.choice(alp) for _ in range(cls.__table__.c.uid.type.length))
      if uid not in uids:
        return uid

  async def edit(self, session: AsyncSession, **kwargs):
    columns = {col.key for col in self.__table__.columns}
    for k, v in kwargs.items():
      if k not in columns:
        continue
      if isinstance(self.__table__.columns.get(k).type, DateTime):
        if isinstance(v, (int, float)):
          v = dt.fromtimestamp(v)
      if isinstance(self.__table__.columns.get(k).type, Integer):
        if isinstance(v, dt):
          v = int(v.timestamp())
      setattr(self, k, v)
    await session.commit()

  async def save(self, session: AsyncSession):
    session.add(self)
    await session.commit()

  async def delete(self, session: AsyncSession):
    await session.delete(self)
    await session.commit()
