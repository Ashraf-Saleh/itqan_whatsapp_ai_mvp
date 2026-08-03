"""Database engine, declarative base, session factory, and FastAPI dependency."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import get_settings

settings = get_settings()

# Render (and Heroku-style providers) hand out "postgres://" URLs, but SQLAlchemy's
# psycopg2 dialect requires the "postgresql://" scheme.
database_url = settings.database_url
if database_url.startswith("postgres://"):
    database_url = "postgresql://" + database_url[len("postgres://"):]

if database_url.startswith("sqlite"):
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
else:
    # pool_pre_ping avoids "server closed the connection unexpectedly" errors from
    # a managed Postgres instance recycling idle connections.
    engine = create_engine(database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Base class shared by every SQLAlchemy ORM model."""

    pass


def get_db():
    """Yield a request-scoped database session and always close it afterward."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
