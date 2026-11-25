import os

from dotenv import load_dotenv


def app_host() -> str:
    load_dotenv()
    return os.environ.get("APP_HOST", "127.0.0.1")


def app_port() -> int:
    load_dotenv()
    return int(os.environ.get("APP_PORT", "8000"))


def forwarded_allow_ips() -> str:
    # Peers whose X-Forwarded-For uvicorn trusts for the client address:
    # comma-separated IPs or networks. Only the reverse proxy in front of the
    # backend belongs here; any other peer could pick its own address.
    load_dotenv()
    return os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1")
