import json
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from manta_blocks import Catalogue

# In the monorepo the committed catalogue sits next to the backend; resolving it
# from this file (src/manta/config -> repo root) keeps it independent of the
# working directory the app or tests were started from. Any deployment that isn't
# "the monorepo checked out on disk" must set MANTA_CATALOGUE_PATH instead.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_CATALOGUE_PATH = _REPO_ROOT / "manta-batteries" / "catalogue.json"


def catalogue_path() -> Path:
    load_dotenv()
    return Path(os.environ.get("MANTA_CATALOGUE_PATH", _DEFAULT_CATALOGUE_PATH))


@lru_cache
def get_catalogue() -> Catalogue:
    """The description of every block playbooks may use.

    The backend cannot import the blocks themselves (they need solver stacks the
    app deliberately does not install), so this catalogue - generated inside the
    block environments, see manta-batteries/README.md - is how playbooks are
    validated and wired here.
    """
    return Catalogue.model_validate(json.loads(catalogue_path().read_text()))


def orchestrator_env() -> str:
    """The environment name the playbook orchestrator is deployed under.

    Must match what `manta_batteries.provision` registered against the Prefect
    server (see its DEFAULT_ORCHESTRATOR_ENV): together they name the deployment
    run_playbook/<env> that every playbook run is started on.
    """
    load_dotenv()
    return os.environ.get("MANTA_ORCHESTRATOR_ENV", "orchestrator")
