import os
from collections.abc import Generator
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_BACKEND_DIR = Path(__file__).resolve().parents[3]


def database_url() -> str:
    load_dotenv(_BACKEND_DIR / ".env")
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ["POSTGRES_PORT"]
    db = os.environ["POSTGRES_DB"]
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


@lru_cache
def get_engine() -> Engine:
    return create_engine(database_url())


def get_db_session() -> Generator[Session]:
    session = sessionmaker(bind=get_engine())()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
