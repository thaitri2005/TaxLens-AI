from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from taxlens.config import get_settings

settings = get_settings()
# A short connect timeout makes an unreachable database fail fast (readiness checks,
# laptop collection runs) instead of hanging.
engine = create_engine(
    settings.database_url, pool_pre_ping=True, connect_args={"connect_timeout": 10}
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def database_is_ready() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return False
    return True
