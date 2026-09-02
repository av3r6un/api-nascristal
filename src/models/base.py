from datetime import date
from datetime import datetime as dt
from decimal import Decimal
from enum import Enum
import secrets
import string
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, AsyncAttrs
from sqlalchemy.orm import mapped_column, selectinload, DeclarativeBase, Mapped, declared_attr
from sqlalchemy import asc, desc, inspect, select, text, func, DateTime, Integer


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
        col = cls.__get_column(field)
        if op == 'gte': exps.append(col >= v)
        elif op == 'lte': exps.append(col <= v)
        elif op == 'gt': exps.append(col > v)
        elif op == 'lt': exps.append(col < v)
        elif op == 'like': exps.append(col.like(v))
        elif op == 'ilike': exps.append(col.ilike(f'%{v}%'))
        elif op == 'date': exps.append(func.date(col) == (v if isinstance(v, date) else date.fromisoformat(v)))
        elif op == 'notnull': exps.append(col.isnot(None))
        elif op == 'isnull': exps.append(col.is_(None))
        else:
          raise ValueError(f'Unsupported filter operation: {op}')
      else:
        simple[k] = v
    return simple, exps

  @classmethod
  def __get_column(cls, field: str):
    col = getattr(cls, field, None)
    if col is None:
      raise AttributeError(f'There is no column: {field}')
    return col

  @classmethod
  def __build_order_by(cls, order_by: str | list[str] | None):
    if not order_by:
      return []
    fields = [order_by] if isinstance(order_by, str) else order_by
    return [
      desc(cls.__get_column(field[1:])) if field.startswith('-')
      else asc(cls.__get_column(field))
      for field in fields
    ]

  @classmethod
  def __build_group_by(cls, group_by: str | list[str] | None):
    if not group_by:
      return []
    fields = [group_by] if isinstance(group_by, str) else group_by
    return [cls.__get_column(field) for field in fields]

  @classmethod
  def __relationship_load(cls, path: str):
    model = cls
    loader = None
    for name in path.split('.'):
      mapper = inspect(model)
      if name not in mapper.relationships:
        raise AttributeError(f'{model.__name__} has no relationship: {name}')
      relationship = getattr(model, name)
      loader = selectinload(relationship) if loader is None else loader.selectinload(relationship)
      model = mapper.relationships[name].mapper.class_
    return loader

  @staticmethod
  def __json_value(value):
    if isinstance(value, Decimal):
      return str(value)
    if isinstance(value, Enum):
      return value.value
    if isinstance(value, dt):
      return int(value.timestamp())
    if isinstance(value, date):
      return value.isoformat()
    return value

  @classmethod
  async def get(cls, session: AsyncSession, *, relationships: list[str] | None = None, limit: int | None = None, offset: int | None = None, **filters):
    order_by = filters.pop('order_by', None)
    group_by = filters.pop('group_by', None)
    query = select(cls)

    mapper = inspect(cls)
    relation_names = [rel.key for rel in mapper.relationships] if relationships is None else relationships
    for name in relation_names:
      query = query.options(cls.__relationship_load(name))

    simple, expressions = cls.__build_filters(**filters)
    if simple:
      query = query.filter_by(**simple)
    if expressions:
      query = query.filter(*expressions)

    groups = cls.__build_group_by(group_by)
    if groups:
      query = query.group_by(*groups)

    ordering = cls.__build_order_by(order_by)
    if ordering:
      query = query.order_by(*ordering)

    if offset is not None:
      query = query.offset(offset)
    if limit is not None:
      query = query.limit(limit)

    result = await session.execute(query)
    return result.scalars()

  @classmethod
  async def get_json(cls, session, **filters):
    results = await cls.get(session, **filters)
    return [row.json for row in results]

  @classmethod
  async def get_multi(cls, session: AsyncSession, field: str, variables: list):
    query = select(cls).where(cls.__get_column(field).in_(variables))
    result = await session.execute(query)
    return result.scalars().all()

  @classmethod
  async def first(cls, session, **filters):
    return (await cls.get(session, **filters)).first()

  @classmethod
  async def all(cls, session, **filters):
    return (await cls.get(session, **filters)).all()

  @classmethod
  async def grouped(cls, session: AsyncSession, group_by: str | list[str], aggregates: dict[str, Any], **filters) -> list[dict[str, Any]]:
    groups = cls.__build_group_by(group_by)
    columns = [*groups, *(expression.label(name) for name, expression in aggregates.items())]
    query = select(*columns)

    simple, expressions = cls.__build_filters(**filters)
    if simple:
      query = query.filter_by(**simple)
    if expressions:
      query = query.filter(*expressions)

    result = await session.execute(query.group_by(*groups))
    return [
      {key: cls.__json_value(value) for key, value in row.items()}
      for row in result.mappings().all()
    ]

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
