<!--
SPDX-FileCopyrightText: 2026 Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# playbook and playbook-library

This page states the boundaries both modelling packages keep, and how to test a change to each.
[Installation: Blocks and playbooks](../installation/blocks-and-playbooks.md) shows how to set both up and run the example playbook.
Writing a block or a playbook is covered in the package READMEs, [playbook](https://github.com/manta-plan/manta/blob/main/playbook/README.md) and [playbook-library](https://github.com/manta-plan/manta/blob/main/playbook-library/README.md).

## Boundaries

--8<-- "CONTRIBUTING.md:docs-playbooks"

## Testing playbook

Run these commands from the `playbook` folder.

--8<-- "playbook/README.md:docs-testing"

## Testing playbook-library

Run these commands from the `playbook-library` folder.
From `playbook` or the repository root, pixi uses the workspace at the root instead, which has no `dev` or `full` environment.

--8<-- "playbook-library/README.md:docs-testing"
