<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Prose rules for Manta

This file contains Manta's own prose rules.
[SKILL.md](SKILL.md) contains the shared rules, and where the two differ, this file wins.

## The reader of a page

Manta has no public release yet, so the reader of a page today is a developer who changes Manta or writes blocks and playbooks for it.
They know Python and energy modelling, and have read no other page.

A how-to guide with the tag `Modelling tool developers` has a second reader, who maintains a modelling framework or runs studies with one.
They know their own framework and workflow, and they may not use PyPSA or have installed Manta.
Describe their side of a page in the words of their own work: a script, a notebook, a Snakemake workflow, a configuration file, a set of dependencies.
On a page that is not about PyPSA, use an example that fits any framework, such as the `geometry` of a `node`, and not a PyPSA word such as `carrier`.

## Project words

| Project word | Define it at first use as | Not |
| --- | --- | --- |
| block | one unit of work in an energy model workflow | task, module, component |
| playbook | blocks chained together into something you can run | workflow, pipeline |
| step | one block, or one nested playbook, in a playbook | stage, node |
| catalogue | the description of every block: names, settings as JSON schema and dimensions | registry, manifest |
| data record | the store in which Manta keeps a project's model, scenarios, and results as layers of tables | tables, store, saved model, model file |
| configuration | the settings of one block, each with its type and its default | settings model, config |
| setting | one entry in the configuration of a block | option, parameter |

A page that prepares the reader's own workflow for Manta, such as `docs/howto/prepare-for-manta.md`, uses "step" and "block" for two different things.
A step is a part of the workflow the reader has today: a script, a rule, or a notebook cell.
A block is what the reader writes for Manta.
So the reader splits their steps into blocks, and then declares the configuration, the dimensions, and the environment of each block.
On such a page, do not write "step" for a place in a playbook or for a part of the guide.
Write "block", "that point in the playbook", or "this guide".

## Punctuation

Use the Oxford comma in every list of three or more items: "format, lint, and type-check".
This rule overrides SKILL.md and its examples.

A semicolon may join two clauses that make one contrast: "It requires you to understand your framework's data model; it doesn't require you to have installed Manta."
This rule overrides "No semicolons" in SKILL.md.
Contractions such as "doesn't" are allowed, and so is "e.g." before an example.

## Voice

- **"We" states the plans and aims of the team.**
  "We plan to support data records that follow a common schema." "Our goal is to support as many modelling frameworks as the community is able to contribute."
  Manta stays the actor for what the software does.
- **A limit comes with what the reader can do today and with the plan beyond it.**
  State what Manta does "currently", then what that means for the reader, then the plan as "We plan to …" or "Our goal is …".
  Put the plan in a `note` or `warning` admonition, and link the section of `docs/explanation/planned-changes.md` or the table of stages that tracks it.
  Never write "will support".
  This rule overrides "No history and no promises on a page" in SKILL.md.
- **State what Manta does and what the reader gains, not what cannot happen.**
  "Manta runs the block in a container built from that environment. This isolation ensures that blocks with conflicting dependencies can run in the same playbook."
  Not "No other part of Manta installs a block's dependencies", and not "A block cannot read a file that an earlier block left behind".
  A sentence that tells the reader what their work does not achieve is cut: say what it prepares instead.
- **Name a thing by what it is, not by a pointer back to it.**
  "To check your conversion functions", not "To check the pair".
  "Your framework's source code", not "that code".
  State what each named function does: "`to_network` converts a data record to a PyPSA model", not "the blocks do both with two functions".

## Words to avoid

None listed yet.

## Extra message rules

None listed yet.
