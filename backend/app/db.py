"""
Sets up the SQLAlchemy engine, session factory, and the FastAPI dependency that hands each
request its own database session.

models.py defines *what* our tables look like (User, Letter, Extraction, Job) as Python
classes. On its own, that's just class definitions sitting in memory -- nothing connects
them to the actual Postgres database docker-compose started. This file is the missing
link: it opens the connection, and gives every request a short-lived Session to read and
write through those models.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://bnav:bnav@localhost:5432/bureaucracy_navigator",
)

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all tables that don't exist yet.

    Fine for a project this size. A real production app would use Alembic
    migrations instead -- create_all() can add a brand-new table, but it can't
    safely change an existing column's type or drop one. Worth naming as a
    deliberate scope cut if it comes up in an interview, not something we
    accidentally missed.
    """
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency: opens one Session per request, and always closes it
    afterward -- even if the request handler raises partway through."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
