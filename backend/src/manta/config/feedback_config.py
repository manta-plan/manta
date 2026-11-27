import os

from dotenv import load_dotenv


def feedback_script_url() -> str | None:
    """The Apps Script web app in OET's Google Workspace that stores feedback. Unset
    means feedback isn't configured, e.g. in local development."""
    load_dotenv()
    return os.environ.get("FEEDBACK_SCRIPT_URL") or None


def feedback_script_secret() -> str:
    """The secret the script checks before it appends a row. Comes from the environment,
    never the repo."""
    load_dotenv()
    return os.environ["FEEDBACK_SCRIPT_SECRET"]
