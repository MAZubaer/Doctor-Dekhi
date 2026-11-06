"""Database engine, session factory and the FastAPI session dependency."""

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# Neon suspends idle compute and drops idle connections, so stale pooled
# connections are tested before use and recycled every five minutes. The connect
# timeout allows for a Neon cold start, but makes an unreachable database fail
# quickly instead of hanging requests.
engine = create_engine(
    settings.active_database_url,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=5,
    max_overflow=5,
    connect_args={"connect_timeout": 10},
)

# expire_on_commit=False lets a response be built from committed objects without
# querying the database again for each one.
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as db:
        yield db


DbSession = Annotated[Session, Depends(get_db)]
