<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Blocks and playbooks

This page shows how to run the blocks and playbooks Manta ships on your own machine, without Docker or the backend.
You need [pixi](https://pixi.sh) and a [clone of the repository](full-stack.md#1-clone-the-repository).
pixi installs Python, PyPSA and the HiGHS solver into environments of its own, for macOS on Apple silicon and for Linux.

## Run the example playbook

Run these commands from the `playbook-library` folder.
The first command installs the environment it names, which takes a few minutes.

--8<-- "playbook-library/README.md:docs-setup"

The example run logs each solver call, then ends with two lines like these:

```text
Running 'expand' on revision 74848185-ed25-4323-829a-bc7d70d08bc0 of /var/folders/.../playbook-example-9pybfz6e
Done. Final result: revision 9f9cb669-10cc-4e1d-b0fe-0acf6711624a of /var/folders/.../playbook-example-9pybfz6e
```

The `expand` playbook read the first revision of the store and wrote its result as a new revision in the same store.

## Environments

--8<-- "playbook-library/README.md:docs-environments"

## Work on the framework alone

The `playbook` framework defines what a block and a playbook are, and uses [uv](https://docs.astral.sh/uv/getting-started/installation/) instead of pixi.
Run these commands from the `playbook` folder.

--8<-- "playbook/README.md:docs-setup"

## Next steps

- To write a block or a playbook, read the [playbook README](https://github.com/manta-plan/manta/blob/main/playbook/README.md) and the [playbook-library README](https://github.com/manta-plan/manta/blob/main/playbook-library/README.md).
- To run the full test suites and the linters, read [Contributing: playbook and playbook-library](../contributing/playbook.md).
