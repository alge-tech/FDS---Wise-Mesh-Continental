"""Engine, sessions and the declarative base shared by every module's models."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    Engine,
    ForeignKey,
    MetaData,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.types import Uuid

from app.core.config import get_settings
from app.core.ids import new_id, utcnow

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)
    type_annotation_map = {datetime: DateTime(timezone=True), UUID: Uuid(as_uuid=True)}


def pk() -> Mapped[UUID]:
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=new_id)


def timestamp_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


def fk(target: str, *, nullable: bool = False, index: bool = True) -> Mapped[Any]:
    return mapped_column(ForeignKey(target), nullable=nullable, index=index)


def currency_col(*, nullable: bool = False) -> Mapped[Any]:
    return mapped_column(CHAR(3), ForeignKey("currencies.code"), nullable=nullable)


def money_col(*, nullable: bool = False) -> Mapped[Any]:
    return mapped_column(BigInteger, nullable=nullable)


def status_col(enum: type[StrEnum], *, default: StrEnum | None = None) -> Mapped[Any]:
    return mapped_column(Text, nullable=False, default=default)


def status_check(column: str, enum: type[StrEnum], name: str | None = None) -> CheckConstraint:
    values = ", ".join(f"'{v.value}'" for v in enum)
    return CheckConstraint(f"{column} IN ({values})", name=name or f"{column}_valid")


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    return _engine


def session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(get_engine(), expire_on_commit=False, autoflush=False)
    return _session_factory


def set_engine(engine: Engine) -> None:
    """Used by tests to point the app at the test database."""
    global _engine, _session_factory
    _engine = engine
    _session_factory = sessionmaker(engine, expire_on_commit=False, autoflush=False)


def get_session() -> Iterator[Session]:
    """Request-scoped session. Services open the transaction they need with session.begin()."""
    with session_factory()() as session:
        yield session


@contextmanager
def transaction(session: Session) -> Iterator[Session]:
    """Open the one transaction a service needs.

    Reads done earlier in the request (auth, loading the caller) auto-begin an implicit
    transaction; it is closed first so the change runs in a clean transaction of its own.
    """
    if session.in_transaction():
        session.commit()
    with session.begin():
        yield session
