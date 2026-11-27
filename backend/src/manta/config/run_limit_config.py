import os

from dotenv import load_dotenv


def max_concurrent_runs_per_user() -> int:
    """How many runs one user can have active at a time, over all of their projects.
    A run is active until it reaches a final state, so one that is queued counts too."""
    load_dotenv()
    return int(os.environ.get("MANTA_MAX_CONCURRENT_RUNS_PER_USER", "2"))
