<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# playbook and playbook-library

This page states the boundaries both modelling packages keep, how to change the format of a playbook document, and how to test a change to each package.
[Installation: Blocks and playbooks](../installation/blocks-and-playbooks.md) shows how to set both up and run the example playbook.
To write a block, see the package READMEs, [playbook](https://github.com/manta-plan/manta/blob/main/playbook/README.md) and [playbook-library](https://github.com/manta-plan/manta/blob/main/playbook-library/README.md).
To write a playbook, see the [playbook syntax](../reference/playbook/syntax.md).

## Change the playbook document format

The models in `playbook/src/playbook/playbooks/syntax.py` define the format of a playbook document.
After you change them, write the JSON schema again.
Run this from the `playbook` folder:

```bash
uv run python -m playbook.playbooks.schema
```

While the committed `playbook.schema.json` differs from the models, `test_committed_schema_matches_playbook_doc` fails.
`pixi run docs-build` generates the [playbook schema](../reference/playbook/schema.md) page from that file.

## Boundaries

--8<-- "CONTRIBUTING.md:docs-playbooks"

## Testing playbook

Run these commands from the `playbook` folder.

--8<-- "playbook/README.md:docs-testing"

## Testing playbook-library

Run these commands from the `playbook-library` folder.
From `playbook` or the repository root, pixi uses the workspace at the root instead, which has no `dev` or `full` environment.

--8<-- "playbook-library/README.md:docs-testing"
