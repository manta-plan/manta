<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Manta

--8<-- "README.md:docs-preamble"

Manta is a web platform for energy system studies.
A study in Manta is a project.
Its stages are: sign in, open a project, bring in a model, define scenarios, run a playbook, inspect the results and report on them.
The [user guide](user-guide/index.md) describes each stage and what the web app supports in it.

## The parts of Manta

- The web app is where a modeller works. It serves the sign-in stage and part of the Run stage: it signs you in, and starts and follows runs.
- The backend serves the sign-in, project and Run stages. It keeps users, projects and runs, and starts each run.
- The modelling framework serves the Run stage. It defines what a block and a playbook are, checks a playbook against its settings, and runs it.
- The library of ready-made blocks serves the Run stage. It contains the blocks and playbooks Manta ships, built on the open-source [PyPSA](https://pypsa.org) power system modelling tool.
- The runner serves the Run stage. It runs each block of a playbook in its own container, and each block saves its result as a new revision in a data record.

## Where to start

- To use the web app as a modeller, read the [user guide](user-guide/index.md).
- To write or run blocks and playbooks, follow [Blocks and playbooks](installation/blocks-and-playbooks.md), then read the [playbook and playbook-library contributing guide](contributing/playbook.md) and the [`playbook` reference](reference/playbook/api.md).
- To work on Manta itself, follow [Full stack](installation/full-stack.md), [Backend](installation/backend.md) or [Frontend](installation/frontend.md). The [technical overview](explanation/architecture.md) shows how the parts fit together, and the [contributing guide](contributing/index.md) sets out how to change them. The [reference](reference/index.md) lists the Python and REST interfaces.
