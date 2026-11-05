# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Run the `expand` playbook on the Belgian test model from the public test data bucket.

    pixi run -e full python -m playbook_library.examples [directory]

The script downloads the `BEL-pre-aggregated` datarecord store into the directory, or
into a new temporary directory, because each block writes its result as a new revision
into the store it reads and the bucket is read-only. The tests download the public
stores with the same functions.
"""

import json
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen, urlretrieve
from uuid import UUID

from playbook.blocks.core import DataRecord
from playbook.playbooks.yaml_io import playbook_from_doc

from playbook_library.playbooks import library_playbooks

PUBLIC_OBJECTS = "https://storage.googleapis.com/storage/v1/b/manta-public-test-data/o"
EXAMPLE_STORE = "BEL-pre-aggregated"
EXAMPLE_PLAYBOOK = "expand"


def download_public_store(name: str, store_dir: Path) -> Path:
    """Download the store `name` of the public test data bucket into `store_dir`."""
    prefix = f"{name}/"
    with urlopen(f"{PUBLIC_OBJECTS}?{urlencode({'prefix': prefix})}") as response:
        listing = json.load(response)
    for item in listing["items"]:
        target = store_dir / item["name"].removeprefix(prefix)
        target.parent.mkdir(parents=True, exist_ok=True)
        urlretrieve(item["mediaLink"], target)
    return store_dir


def inputs_record(store_dir: Path) -> DataRecord:
    """Point a record at the `inputs` revision that `revisions.json` of a public store lists."""
    revisions = json.loads((store_dir / "revisions.json").read_text())
    return DataRecord(url=str(store_dir), uuid=UUID(revisions["inputs"]))


def main(argv: list[str]) -> int:
    root = Path(argv[0]) if argv else Path(tempfile.mkdtemp(prefix="playbook-example-"))
    record = inputs_record(download_public_store(EXAMPLE_STORE, root / EXAMPLE_STORE))

    entry = library_playbooks()[EXAMPLE_PLAYBOOK]
    print(f"Running {EXAMPLE_PLAYBOOK!r} on revision {record.uuid} of {record.url}")
    result = playbook_from_doc(entry.doc).run(record, entry.default_config)
    print(f"Done. Final result: revision {result.uuid} of {result.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
