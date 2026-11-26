import os

from dotenv import load_dotenv


def guest_logins_per_client_per_hour() -> int:
    """How many guest accounts one client IP can create in an hour."""
    load_dotenv()
    return int(os.environ.get("GUEST_LOGINS_PER_CLIENT_PER_HOUR", "5"))


def guest_logins_per_hour() -> int:
    """How many guest accounts everyone together can create in an hour. A backstop for
    the per-client limit, which can be dodged by rotating IPs, and which lumps every
    user into one client when the app sits behind a proxy it doesn't trust headers from."""
    load_dotenv()
    return int(os.environ.get("GUEST_LOGINS_PER_HOUR", "100"))
