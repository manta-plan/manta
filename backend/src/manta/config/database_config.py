import os
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parents[3]


def database_url() -> str:
    load_dotenv(_BACKEND_DIR / ".env")
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ["POSTGRES_PORT"]
    db = os.environ["POSTGRES_DB"]
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"
