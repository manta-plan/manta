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

## Project words

| Project word | Define it at first use as | Not |
| --- | --- | --- |
| block | one unit of work in an energy model workflow | task, module, component |
| playbook | blocks chained together into something you can run | workflow, pipeline |
| step | one block, or one nested playbook, in a playbook | stage, node |
| catalogue | the description of every block: names, settings as JSON schema and dimensions | registry, manifest |

## Punctuation

Use the Oxford comma in every list of three or more items: "format, lint, and type-check".
This rule overrides SKILL.md and its examples.

## Line breaks

In a Markdown file in the repository, write one sentence per line, with no line breaks at a fixed width, as [CONTRIBUTING.md](../../../CONTRIBUTING.md) states under Markdown files.
Markup that needs its own line keeps it: a definition list has the term on one line and its `:` definition on the next.
A PR or issue body is exempt, because GitHub renders each line break.

## Words to avoid

None listed yet.

## Extra message rules

None listed yet.
