import os

from dotenv import load_dotenv


def app_host() -> str:
    load_dotenv()
    return os.environ.get("APP_HOST", "127.0.0.1")


def app_port() -> int:
    load_dotenv()
    return int(os.environ.get("APP_PORT", "8000"))
