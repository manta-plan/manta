<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Manta's purpose

Manta exists to make world-class energy system planning straightforward and accessible.
With it, the institutions that shape the energy transition can make faster decisions, with more confidence and trust.
This page explains the problem Manta answers, the kind of application it is, and how it relies on, promotes, and enables other efforts in the energy modelling community.

!!! warning "Manta is still under development"

    This page describes what Manta is designed to become.
    The [user guide](index.md#what-the-web-app-supports-today) lists what the web app supports today.

## The usability barrier

Open-source energy system models are fast, capable and free to use, yet few of the organisations that plan the energy transition rely on them.
The main barrier is usability, not performance.
To run these models today, you manage CSV files, write code in Python or Julia, and need to understand GitHub.

The result is that many organisations do not move to open-source tools, and keep relying on proprietary tools.
These tools are often closed, so their users cannot see how a result was reached (black-box tools).
A result that no one outside the vendor can inspect is hard to trust, however good it is.

## A full application, not just an interface

Manta is a complete application that sits on top of existing open-source modelling tools.
It is not a set of screens that fills in the input files for one tool (a graphical user interface, or GUI).

A GUI alone would fall short.
It helps one modeller work a little faster, but it ties every study to the one tool underneath.
The organisation cannot pick the best tool for each question, or move to better tools as the field advances.
A simple GUI also has no shared projects, no control over who sees what, and no record of what was run.

Manta serves the companies that run high-voltage grids (transmission system operators, or TSOs), as well as regulators, governments and industry.
To use a tool for real decisions, these organisations need more than a GUI:

- Security fit for confidential grid data, and the option to run Manta on their own servers.
- Efficient handling of large runs, with each step given the computing power it needs (orchestration).
- Models, scenarios and results kept together in one place, with every version stored (data management).
- Transparent execution, so anyone can trace a result back to its model, data, and workflow - and reproduce it.
- An intuitive interface that any analyst can use without writing code.
- Shared projects, where teams can collaborate.
- Accounts, with administrators who decide who can view and edit each project.

The [Users and scope](../explanation/scope.md) page sets out how these needs shape Manta's design.

## A shared structure for the community to fill

Manta does not aim to contain every model and analysis from the start.
It provides the foundation, and a community of experts adds the parts that run on it.
The diagram shows who adds what, and who uses it.

![Tool developers create modular workflow blocks, which analysis experts use to create repeatable playbooks. A data community creates model-ready datasets, which modelling experts use to create transparent and validated models. Analysts run playbooks on models, and see the results in interactive dashboards. Decision makers use the resulting transparent and reproducible analyses.](../static/purpose-community-draft.webp)

Each group works at the level it knows best:

- Tool developers write blocks. A block is one unit of work in an energy model workflow, such as grouping hourly data into fewer, longer periods.
- Analysis experts chain blocks into playbooks. A playbook is a set of blocks that you can run as one repeatable analysis.
- A data community prepares datasets that are ready to use in a model.
- Modelling experts build models from those datasets, and validate them.
- Analysts run playbooks on models, and visualise the results in dashboards.
- Decision makers use the analyses, which anyone can trace back and repeat.

An analyst can start a study without learning to write blocks, prepare data and build models first.
The work of every group upstream is already there to use.

The structure matters as much as the parts.
Every block describes its settings and its inputs in the same way, so a block from one author fits into a playbook from another.
Without that shared shape, each contribution would be a one-off that only its author could connect.
Manta ships with a first set of blocks and playbooks.
Developers and tool creators can add new blocks, and analysts can build new playbooks from them.
[Concepts](concepts.md) defines each of these terms.

## The modelling tools under Manta

Manta's first goal is a consistent, reliable application that grid operators and industry can use, whatever tool runs underneath.
To reach that goal quickly, the blocks that ship with Manta currently use [PyPSA](https://pypsa.org), an open-source power system modelling tool.
Manta describes models in PyPSA's terms, and imports PyPSA models.

Manta is not a wrapper for PyPSA, though.
None of its structure is designed for PyPSA: projects, runs, blocks, playbooks and stored results work the same whichever tool a block uses.
The modelling tool sits inside each block, and the rest of Manta never calls it directly.
So other tools can run in other blocks, and contributors can bring the tools they know.

Parts of the web app use PyPSA's terms and views today.
This is a shortcut to a working application, not part of Manta's design.
Manta aims to describe models in one common format that covers many tools.

The first blocks answer two planning questions.
The first is what to build and when (capacity expansion), and the second is how the system runs hour by hour (dispatch).
Both are optimisation problems.
Other kinds of analysis, such as how power moves through the grid (power flow), fit the same structure of blocks and playbooks.

Most of the people building Manta today are PyPSA experts.
The group also includes people with experience of [Calliope](https://www.callio.pe) and [Tulipa](https://github.com/TulipaEnergy/TulipaEnergyModel.jl), two other optimisation frameworks.
Manta welcomes contributors who know other optimisation frameworks, and experts in power flow and other techniques that the current group does not cover.

