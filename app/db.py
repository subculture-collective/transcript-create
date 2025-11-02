from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session as _SASession, sessionmaker

from .settings import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db():
    # Allow tests to monkeypatch SessionLocal to a concrete Session instance
    created_here = False
    if callable(SessionLocal):
        db = SessionLocal()
        created_here = True
    else:
        db = SessionLocal  # type: ignore[assignment]
        if not isinstance(db, _SASession):
            # Fallback: create a new session
            db = sessionmaker(bind=engine, expire_on_commit=False)()
            created_here = True
    try:
        yield db
    finally:
        if created_here:
            db.close()
