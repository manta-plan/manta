# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Run a library playbook on the full-resolution Belgian model of the public bucket.

    pixi run -e full python -m playbook_library.examples [directory] [--playbook NAME]

The playbook is `cluster-expand-dispatch` unless named. The script downloads the
`BEL-full-res` datarecord store into the directory, or into a new temporary directory,
because each block writes its result as a new revision into the store it reads and the
bucket is read-only. The tests download the public
stores with the same functions, which need the `public-data` extra.
"""

import argparse
import json
import tempfile
from pathlib import Path
from uuid import UUID

from playbook.blocks.core import RevisionRef
from playbook.playbooks.yaml_io import playbook_from_doc

from playbook_library.playbooks import library_playbooks
from playbook_library.public_data import download_public_store

EXAMPLE_STORE = "BEL-full-res"
EXAMPLE_PLAYBOOK = "cluster-expand-dispatch"


def inputs_ref(store_dir: Path) -> RevisionRef:
    """Point at the `inputs` revision that `revisions.json` of a public store lists."""
    revisions = json.loads((store_dir / "revisions.json").read_text())
    return RevisionRef(store=str(store_dir), id=UUID(revisions["inputs"]))


def main(argv: list[str] | None = None) -> int:
    playbooks = library_playbooks()
    parser = argparse.ArgumentParser(
        prog="python -m playbook_library.examples",
        description=f"Run a library playbook on the {EXAMPLE_STORE} model of the public bucket.",
    )
    parser.add_argument(
        "directory",
        type=Path,
        nargs="?",
        help="where to copy the store to; a new temporary directory if not given",
    )
    parser.add_argument("--playbook", default=EXAMPLE_PLAYBOOK, choices=sorted(playbooks))
    args = parser.parse_args(argv)

    root = args.directory or Path(tempfile.mkdtemp(prefix="playbook-example-"))
    ref = inputs_ref(download_public_store(EXAMPLE_STORE, root / EXAMPLE_STORE))
    entry = playbooks[args.playbook]
    print(f"Running {args.playbook!r} on revision {ref.id} of {ref.store}")
    result = playbook_from_doc(entry.doc).run(ref, entry.default_config)
    print(f"Done. Final result: revision {result.id} of {result.store}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
