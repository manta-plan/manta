<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Concepts

This page defines the terms the user guide uses, in the order you will come across them.
Some terms name stages the web app does not support today.
See the [table of stages](index.md#what-the-web-app-supports-today) for when to expect them.

Project
:   A project is one energy system study.
You attach a model to it, and its data record holds that model with the scenarios, runs and results of the study.

Model
:   A model is a description of an energy system that a solver can optimise: its network, technologies, costs and time series.
Manta currently represents models using the [PyPSA](https://pypsa.org) energy modelling framework terminology and can import PyPSA models.
We aim to support models from several modelling frameworks and to represent the model in Manta using a common schema.

Scenario
:   A scenario is the base model plus an ordered set of changes, such as a higher carbon price or a new interconnector.

Playbook
:   A playbook is a ready-made sequence of configurable analysis steps.
[Playbooks and blocks](playbooks.md) explains what one is made of.

Block
:   A block is one step of an analysis applied to a model (a _playbook_), such as aggregating its time series or optimising future technology capacities.

Run
:   A run is one pass of a playbook over a model, with the settings you chose.
Its status shows whether it is waiting, running, completed or failed.

Data record
:   A data record is the store that holds a project's model, scenarios and results as layers, each on top of the one before.
The input model is the first layer, each scenario adds patch layers, and each block in a run adds a result layer.
Each stage also reads from the data record.
The Model stage reads the input model and scenario layers, and each block in a run reads the layer the block before it added.
The Inspect and Report stages read a run's final result layer.

Inspection
:   An inspection is a page of charts and tables built from the results of one or more runs.

Report
:   A report is a set of pages of charts and text, arranged to print or share.
