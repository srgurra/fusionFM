from sqlalchemy import select
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Model(Base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)

    def save(self, session):
        session.add(self)
        session.flush()
        session.refresh(self)
        return self

    def delete(self, session):
        session.delete(self)

    def to_dict(self):
        data = {}
        for column in self.__table__.columns:
            data[column.name] = getattr(self, column.name)
        return data

    @classmethod
    def all(cls, session):
        return session.scalars(select(cls)).all()

    @classmethod
    def get(cls, session, obj_id):
        return session.get(cls, obj_id)

    @classmethod
    def filter_by(cls, session, **kwargs):
        stmt = select(cls).filter_by(**kwargs)
        return session.scalars(stmt).all()

    @classmethod
    def first_by(cls, session, **kwargs):
        stmt = select(cls).filter_by(**kwargs)
        return session.scalars(stmt).first()