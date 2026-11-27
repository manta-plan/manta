import os

from dotenv import load_dotenv


def guest_login_enabled() -> bool:
    """Whether POST /v1/auth/guest creates guest accounts. Turned off on instances
    that only known users may sign in to. The frontend hides its "Continue as guest"
    button through its own build arg, VITE_GUEST_LOGIN_ENABLED."""
    load_dotenv()
    return os.environ.get("GUEST_LOGIN_ENABLED", "true").lower() == "true"
