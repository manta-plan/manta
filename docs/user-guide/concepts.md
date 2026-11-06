<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Concepts

This page defines the terms the user guide uses, in the order a project meets them.
Some terms name stages the web app does not support today, and the [table of stages](index.md#what-the-web-app-supports-today) lists what each stage offers.

Project
:   A project is one energy system study. You attach a model to it, and its data record holds that model with the scenarios, runs and results of the study.

Model
:   A model is a description of an energy system that a solver can optimise: its network, technologies, costs and time series. Manta works with models built with [PyPSA](https://pypsa.org), the open-source power system modelling tool.

Scenario
:   A scenario is the base model plus an ordered set of changes, such as a higher carbon price or a new interconnector.

Playbook
:   A playbook is a ready-made sequence of blocks with default settings for each of them. [Playbooks and blocks](playbooks.md) explains what one is made of.

Block
:   A block is one piece of modelling work on a model, such as shortening its time series or deciding what to build.

Run
:   A run is one pass of a playbook over a model, with the settings you chose. Its status shows whether it is waiting, running, completed or failed.

Data record
:   A data record is the store that holds a project's model, scenarios and results as layers, each on top of the one before. The model is the first layer, each scenario adds patch layers, and each block in a run adds a result layer. Each stage also reads from the data record. The network view reads the model and scenario layers, and each block reads the layer the block before it added. Inspections and reports read a run's final result layer.

Inspection
:   An inspection is a page of charts and tables built from the results of one or more runs.

Report
:   A report is a set of pages of charts and text, arranged to print or share.
