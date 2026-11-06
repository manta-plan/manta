<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# User guide

This guide is for modellers who use the Manta web app.
It names the stages an energy system study moves through in Manta, and lists what the web app supports in each stage today.
Today the web app covers signing in and part of the Run stage.

## How a project moves through Manta

A project is one study.
It moves through seven stages, from signing in to sharing a report.

<div class="manta-figure">
--8<-- "docs/user-guide/project-flow.svg"
</div>

The top row shows what you do, from left to right.
The bottom part shows the project's data record, which Manta builds up one layer at a time as you go.
Each layer sits on top of the layers before it, so the layers underneath stay as they were.
A solid arrow shows a stage adding a layer, and a dashed arrow shows a stage reading the layers beneath it.
The diagram shows three blocks as an example, and a real run adds one result layer for each block in its playbook.

You sign in, then create a project or open one you made before.
You bring a model into the project: a premade model, an example model or your own [PyPSA](https://pypsa.org) model.
PyPSA is the open-source power system modelling tool that Manta's models are built with.
Manta stores the model as the first layer of the project's data record.

In the Model stage you look at the model's network and define scenarios.
A scenario is the base model plus an ordered set of changes, and Manta stores each scenario as patch layers on top of the model layer.
The network you see is read from the model layer together with the patch layers of the scenario you pick.

In the Run stage you pick a [playbook](playbooks.md) and a scenario, adjust the playbook's settings, and run it while you follow its status and log.
The first block reads the scenario, and each later block reads the result layer the block before it added.
Each block adds its own result layer on top, and the last block adds the final result layer.
So you can look at the model as each block left it.

In the Inspect stage you read the final result layer through inspections, which are pages of charts and tables, and compare runs.
In the Report stage you arrange charts and text from the same final result layer into pages to print or share.

## What the web app supports today

Each row names a stage, what the web app lets you do in it, and the milestones that track the work on it.

| Stage                    | What you can do today                                                                                                                         | Tracked in                                                                                                                                                                      |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Sign in                  | You sign in with a username and password, and sign out.                                                                                       | [M2.3](https://github.com/manta-plan/manta/milestone/9)                                                                                                                         |
| Create or open a project | Manta creates one project for you when you open the web app in a new browser tab. You cannot name, open or switch projects.                  | [M2.3](https://github.com/manta-plan/manta/milestone/9), [M3](https://github.com/manta-plan/manta/milestone/1)                                                                  |
| Bring in a model         | The web app offers nothing for this stage.                                                                                                    | [M2.2](https://github.com/manta-plan/manta/milestone/8), [M3](https://github.com/manta-plan/manta/milestone/1)                                                                  |
| Model                    | The web app offers nothing for this stage.                                                                                                    | [M2.3](https://github.com/manta-plan/manta/milestone/9), [M4](https://github.com/manta-plan/manta/milestone/2)                                                                  |
| Run                      | You start a run of the `expand` playbook with its default settings, and follow its status and log. The run does not complete, because it has no model to work on. | [M2.1](https://github.com/manta-plan/manta/milestone/7), [M2.2](https://github.com/manta-plan/manta/milestone/8), [M2.3](https://github.com/manta-plan/manta/milestone/9) |
| Inspect                  | The web app offers nothing for this stage.                                                                                                    | [M2.2](https://github.com/manta-plan/manta/milestone/8), [M2.3](https://github.com/manta-plan/manta/milestone/9), [M4](https://github.com/manta-plan/manta/milestone/2) |
| Report                   | The web app offers nothing for this stage.                                                                                                    | [M2.3](https://github.com/manta-plan/manta/milestone/9), [M4](https://github.com/manta-plan/manta/milestone/2)                                                                  |

## Next steps

- [Concepts](concepts.md) defines each term this guide uses.
- [Playbooks and blocks](playbooks.md) explains what a playbook is made of and how Manta runs one.
- [Start and follow a run](run.md) shows how to start a run in the web app.
