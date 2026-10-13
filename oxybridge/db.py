from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from oxybridge.config import settings


def now():
    return datetime.now(UTC)


def uid():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings().database_url,
    pool_pre_ping=True,
    pool_size=settings().database_pool_size,
    max_overflow=settings().database_max_overflow,
    connect_args={"connect_timeout": 5},
)
Session = sessionmaker(engine, expire_on_commit=False)


@contextmanager
def transaction():
    with Session.begin() as db:
        yield db


def get_db():
    with Session() as db:
        yield db
