<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# User guide

This guide is for modellers who use the Manta web app.
It names the stages an energy system study moves through in Manta, and lists what the web app supports in each stage today.
Today the web app supports the stages from signing in to Run, some only in part, and offers nothing yet for Inspect and Report.

## What the web app supports today

A project is one study, and it moves through seven stages from signing in to sharing a report.
For what you do in each stage, see [How a study works in Manta](how-a-study-works.md).
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

- [Manta's purpose](purpose.md) states the problem Manta answers, and why it is built around a community.
- [How a study works in Manta](how-a-study-works.md) describes a study from model to results, and the kinds of analysis a playbook runs.
- [Concepts](concepts.md) defines each term this guide uses.
- [Playbooks and blocks](playbooks.md) explains what a playbook is made of and how Manta runs one.
- [Start and follow a run](run.md) shows how to start a run in the web app.
