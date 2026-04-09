from __future__ import annotations

import inspect

from sqlalchemy import func, select
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def relation(*args, **kwargs):
    return relationship(*args, **kwargs)


class ModelQuery:
    def __init__(self, model, session, stmt=None):
        self.model = model
        self.session = session
        self.stmt = stmt if stmt is not None else select(model)

    def where(self, *criteria):
        return self._clone(self.stmt.where(*criteria))

    def filter_by(self, **kwargs):
        return self._clone(self.stmt.filter_by(**kwargs))

    def order_by(self, *clauses):
        return self._clone(self.stmt.order_by(*clauses))

    def limit(self, value):
        return self._clone(self.stmt.limit(value))

    def offset(self, value):
        return self._clone(self.stmt.offset(value))

    def options(self, *options):
        return self._clone(self.stmt.options(*options))

    def all(self):
        return self.session.scalars(self.stmt).all()

    def first(self):
        return self.session.scalars(self.stmt.limit(1)).first()

    def one(self):
        return self.session.scalars(self.stmt).one()

    def one_or_none(self):
        return self.session.scalars(self.stmt).one_or_none()

    def count(self):
        count_stmt = select(func.count()).select_from(self.stmt.order_by(None).subquery())
        return self.session.execute(count_stmt).scalar_one()

    def exists(self):
        return self.count() > 0

    def paginate(self, *, page=1, per_page=20):
        page = max(1, int(page))
        per_page = max(1, int(per_page))
        total = self.count()
        items = self.offset((page - 1) * per_page).limit(per_page).all()
        pages = (total + per_page - 1) // per_page if total else 0
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    def _clone(self, stmt):
        return type(self)(self.model, self.session, stmt=stmt)


class Model(Base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)

    def validate(self):
        return None

    def before_save(self, session):
        return None

    def after_save(self, session):
        return None

    def before_delete(self, session):
        return None

    def after_delete(self, session):
        return None

    def save(self, session):
        self.validate()
        _invoke_model_hook(self.before_save, session)
        session.add(self)
        session.flush()
        session.refresh(self)
        _invoke_model_hook(self.after_save, session)
        return self

    def delete(self, session):
        _invoke_model_hook(self.before_delete, session)
        session.delete(self)
        session.flush()
        _invoke_model_hook(self.after_delete, session)

    def update_from_dict(self, values: dict, *, validate=True):
        for key, value in values.items():
            setattr(self, key, value)
        if validate:
            self.validate()
        return self

    def to_dict(self):
        data = {}
        for column in self.__table__.columns:
            data[column.name] = getattr(self, column.name)
        return data

    @classmethod
    def create(cls, session, **values):
        instance = cls(**values)
        return instance.save(session)

    @classmethod
    def query(cls, session):
        return ModelQuery(cls, session)

    @classmethod
    def all(cls, session):
        return cls.query(session).all()

    @classmethod
    def get(cls, session, obj_id):
        return session.get(cls, obj_id)

    @classmethod
    def filter_by(cls, session, **kwargs):
        return cls.query(session).filter_by(**kwargs).all()

    @classmethod
    def first_by(cls, session, **kwargs):
        return cls.query(session).filter_by(**kwargs).first()

    @classmethod
    def one_by(cls, session, **kwargs):
        return cls.query(session).filter_by(**kwargs).one()

    @classmethod
    def count(cls, session, **kwargs):
        query = cls.query(session)
        if kwargs:
            query = query.filter_by(**kwargs)
        return query.count()

    @classmethod
    def exists(cls, session, **kwargs):
        query = cls.query(session)
        if kwargs:
            query = query.filter_by(**kwargs)
        return query.exists()


def _invoke_model_hook(hook, session):
    params = inspect.signature(hook).parameters
    if params:
        return hook(session)
    return hook()
