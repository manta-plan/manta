<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# User guide

This guide is for modellers who use the Manta web app.
It names the stages an energy system study moves through in Manta, and lists what the web app supports in each stage today.
Today the web app supports the stages from signing in to Run, some only in part, and offers nothing yet for Inspect and Report.

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
The diagram shows three blocks as an example; a real run adds one result layer for each block in its playbook.

You sign in, then create a project or open one you made before.
You bring a model into the project: a premade model, an example model, or your own model.
Manta stores the model as the first layer of the project's data record.

!!! note "Supported Modelling Frameworks"

    Initially, only [PyPSA](https://pypsa.org) models are supported in Manta.
    PyPSA is the open-source power system modelling tool that Manta's models are currently built with.
    We aim to support a range of the most popular open-source capacity expansion, production cost, and (eventually) power flow modelling frameworks.
    To do so, we will use a generalised model and data schema.

In the Model stage you look at the model's network on a map and browse its components and their values.
You also define scenarios.
A scenario is the base model plus an ordered set of changes.
You start a new scenario from an existing one, then change a value for one component or for every component that matches a type, carrier, or location, or add new components.
You can compare the inputs of two scenarios side by side.
Manta stores each scenario as patch layers on top of the model layer.
The network you see is read from the model layer together with the patch layers of the scenario you pick.

In the Run stage you pick a [playbook](playbooks.md) and a scenario, adjust the playbook's settings, and run it while you follow its status and log.
The first block reads the scenario, and each later block reads the result layer added by the previous block.
Each block adds its own result layer on top, and the last block adds the final result layer.
This allows you to inspect results from intermediate blocks of a run, in case you need to understand unexpected results.

In the Inspect stage you read the final result layer of a run.
You see headline figures and results on the map, and you open inspections, which are pages of charts and tables.
Manta provides a set of inspections, and you can build your own from charts and tables of your choice.
You can show two runs side by side in the same inspection to compare them.

In the Report stage you arrange charts from your inspections, together with headings, text, and images, into pages.
Each chart in a report shows the results of the run you choose for it.
You export the report as a PDF to print or share.

## What the web app supports today

Each row names a stage, what the web app lets you do in it, and the milestones that track the work on it.

| Stage                    | What you can do today                                                                                                                                                                                                      | Tracked in                                                                                                                                                                |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Sign in                  | You sign in with a username and password, and sign out from the **Projects** page.                                                                                                                                         | [M2.3](https://github.com/manta-plan/manta/milestone/9)                                                                                                                   |
| Create or open a project | The **Projects** page lists your projects. You create a project with a name, a description, and a data record, and you open, rename, or remove a project.                                                                  | [M2.3](https://github.com/manta-plan/manta/milestone/9), [M3](https://github.com/manta-plan/manta/milestone/1)                                                            |
| Bring in a model         | You pick a data record from the **Data Catalog** when you create a project. An administrator adds the data records, so you cannot upload a model of your own.                                                              | [M2.2](https://github.com/manta-plan/manta/milestone/8), [M3](https://github.com/manta-plan/manta/milestone/1)                                                            |
| Model                    | You view the model's network on a map, browse its components and their values, and view the scenarios the data record has. You cannot define a scenario.                                                                   | [M2.3](https://github.com/manta-plan/manta/milestone/9), [M4](https://github.com/manta-plan/manta/milestone/2)                                                            |
| Run                      | You pick a data record and a playbook, adjust the playbook's settings, and start a run once Manta has checked them. The run starts from the data record's input model, not from a scenario. You follow its status and log. | [M2.1](https://github.com/manta-plan/manta/milestone/7), [M2.2](https://github.com/manta-plan/manta/milestone/8), [M2.3](https://github.com/manta-plan/manta/milestone/9) |
| Inspect                  | The web app offers nothing for this stage.                                                                                                                                                                                 | [M2.2](https://github.com/manta-plan/manta/milestone/8), [M2.3](https://github.com/manta-plan/manta/milestone/9), [M4](https://github.com/manta-plan/manta/milestone/2)   |
| Report                   | The web app offers nothing for this stage.                                                                                                                                                                                 | [M2.3](https://github.com/manta-plan/manta/milestone/9), [M4](https://github.com/manta-plan/manta/milestone/2)                                                            |

## Next steps

- [Concepts](concepts.md) defines each term this guide uses.
- [Playbooks and blocks](playbooks.md) explains what a playbook is made of and how Manta runs one.
- [Start and follow a run](../howto/start-and-follow-a-run.md) shows how to start a run in the web app.
