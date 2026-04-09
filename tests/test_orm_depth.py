from sqlalchemy import ForeignKey, create_engine
from sqlalchemy.orm import Mapped, mapped_column, selectinload, sessionmaker

import fusionframe.db as db_module
from fusionframe.db import Base, transaction
from fusionframe.orm import Model, relation


def test_model_query_relationships_and_pagination(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'orm_depth.db'}", echo=False)
    session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", session_local)

    class Author(Model):
        __tablename__ = "authors_depth"
        name: Mapped[str] = mapped_column(nullable=False)
        books = relation("Book", back_populates="author", cascade="all, delete-orphan")

    class Book(Model):
        __tablename__ = "books_depth"
        title: Mapped[str] = mapped_column(nullable=False)
        author_id: Mapped[int] = mapped_column(ForeignKey("authors_depth.id"), nullable=False)
        author = relation("Author", back_populates="books")

    Base.metadata.create_all(bind=engine)

    with transaction() as session:
        alice = Author.create(session, name="Alice")
        Book.create(session, title="A-1", author_id=alice.id)
        Book.create(session, title="A-2", author_id=alice.id)
        Author.create(session, name="Bob")

    with transaction() as session:
        author = (
            Author.query(session)
            .options(selectinload(Author.books))
            .filter_by(name="Alice")
            .one()
        )
        ordered = Author.query(session).order_by(Author.name.desc()).all()
        page = Author.query(session).order_by(Author.name.asc()).paginate(page=1, per_page=1)

        assert author.name == "Alice"
        assert [book.title for book in author.books] == ["A-1", "A-2"]
        assert [item.name for item in ordered] == ["Bob", "Alice"]
        assert page["total"] == 2
        assert page["pages"] == 2
        assert page["items"][0].name == "Alice"
        assert Author.count(session) == 2
        assert Author.exists(session, name="Bob") is True
        assert Author.first_by(session, name="Bob").name == "Bob"

    Base.metadata.remove(Book.__table__)
    Base.metadata.remove(Author.__table__)
    engine.dispose()


def test_model_validation_hooks_update_and_transactions(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'orm_hooks.db'}", echo=False)
    session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", session_local)

    events = []

    class Product(Model):
        __tablename__ = "products_depth"
        name: Mapped[str] = mapped_column(nullable=False)
        price: Mapped[int] = mapped_column(nullable=False)

        def validate(self):
            self.name = self.name.strip()
            if self.price < 0:
                raise ValueError("price must be positive")

        def before_save(self, session):
            events.append(f"before-save:{self.name}")

        def after_save(self, session):
            events.append(f"after-save:{self.name}")

        def before_delete(self, session):
            events.append(f"before-delete:{self.name}")

        def after_delete(self, session):
            events.append(f"after-delete:{self.name}")

    Base.metadata.create_all(bind=engine)

    with transaction() as session:
        product = Product.create(session, name=" Widget ", price=10)
        product.update_from_dict({"price": 12}).save(session)
        assert product.name == "Widget"
        assert product.price == 12

    try:
        with transaction() as session:
            Product.create(session, name="Broken", price=-1)
    except ValueError as exc:
        assert "price must be positive" in str(exc)
    else:
        raise AssertionError("expected validation failure")

    with transaction() as session:
        stored = Product.one_by(session, name="Widget")
        stored.delete(session)

    with transaction() as session:
        assert Product.count(session) == 0

    assert events == [
        "before-save:Widget",
        "after-save:Widget",
        "before-save:Widget",
        "after-save:Widget",
        "before-delete:Widget",
        "after-delete:Widget",
    ]

    Base.metadata.remove(Product.__table__)
    engine.dispose()
