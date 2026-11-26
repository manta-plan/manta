<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Docs rules for Manta

This file contains Manta's own docs rules.
[SKILL.md](SKILL.md) contains the shared rules, and where the two differ, this file wins.

## Nav sections

- Home (`docs/index.md`) states what Manta is, from the preamble of `README.md`.
- User guide (`docs/user-guide/`) is for modellers who use the web app: the stages of a study, the concepts, and what playbooks and blocks are.
- Installation (`docs/installation/`) has one page per kind of work: the full stack, blocks and playbooks, the backend and the frontend. They pull setup and running from `README.md` and the package READMEs, and the contributing pages keep tests, linting and coding rules.
- How-to (`docs/howto/`) contains every task guide: the reader has a task, and the page gives the steps. Only setup stays outside it, in Installation. A guide has one or more of three readers. `App users` work in the web app. `Modelling tool developers` maintain a modelling framework, a workflow, or a tool that a workflow uses, and write blocks and playbooks for Manta. `Manta developers` change Manta.
- Explanation (`docs/explanation/`) holds the explanation pages, such as the architecture.
- Reference (`docs/reference/`) holds the Python API of `playbook` and `runner`, and the REST API.
- Contributing (`docs/contributing/`) is the section for someone who changes Manta, last in the nav. Its pages pull their content from `CONTRIBUTING.md` and the package READMEs.

## How-to guides for modelling tool developers

A guide with the tag `Modelling tool developers` prepares a reader who may not have run Manta.
These rules override SKILL.md, which keeps teaching and explanation out of a how-to.

- Open the guide's first section with the reader's starting point.
- A section may open with the model of Manta that the reader needs before they can decide.
  "Split your workflow into blocks" states that data records build up in layers, because the reader cannot choose what one block contains without it.
  Keep that model to a short paragraph and one concrete sequence as a list, and link the explanation page for the argument.
- Explain a concept with a modelling sequence the reader knows from their own work: aggregate the time dimension, optimise capacities, then fix them and solve again.
  Prefer that sequence to the name of one of Manta's own playbooks, and name a block of Manta's only where the page shows or links it.
- Give the reason for a requirement in one sentence where the reason tells the reader what they gain.
  "This isolation ensures that blocks with conflicting dependencies can run in the same playbook."
- Follow the two meanings of "step" and "block" that the prose-writing skill's project.md sets for these pages.

## The running example

None is chosen yet.

## Figure colours

No figure exists yet. Assign the colours with the first one.

## Generated content

| Page | Written by | Checked by |
| --- | --- | --- |
| `docs/reference/backend/rest-api.md` | `tools/docs/gen_rest_api.py`, from `docs/reference/backend/openapi.json`, before every `pixi run docs-build` and `pixi run docs-serve`. Git ignores the page. | the strict build |
| The table in `docs/howto/index.md`, between the `howto-guides` markers | `tools/docs/gen_howto_index.py`, from the title and the front matter of each guide, before every `pixi run docs-build` and `pixi run docs-serve`. Git tracks the page, so commit the table when it changes. | the strict build, which refuses a tag outside `tags_allowed` |
| `docs/reference/backend/openapi.json` | `pixi run docs-openapi`, which runs `tools/docs/export_openapi.py` in the backend's uv environment | `.github/workflows/docs.yml` exports it again and fails if it differs |

## Extra mechanics

- In phase 1, `README.md`, `CONTRIBUTING.md` and the package READMEs are the source of every installation and contributing page. A page pulls a section in with a snippet between `<!-- --8<-- [start:name] -->` and `<!-- --8<-- [end:name] -->` markers. To change snippet text, edit the README, not the page. Prose written on the page itself, such as `docs/contributing/docs.md`, is edited on the page.
- A how-to guide opens with front matter, above the SPDX header. `tags` lists its readers, from the three in `tags_allowed` in `mkdocs.yml`. `description` is one line that follows "Use it to" in the table on the landing page. Add no row to that table by hand.
- Write one sentence per line, in a list item too.
  The second sentence of an item starts on a line of its own, with an indent of two spaces.
- A GitHub alert (`> [!NOTE]`) in a pulled-in section renders as an admonition, through the `github-callouts` extension of `markdown-callouts`.

## Extra gates

After a change to a backend route, request or result, run `pixi run docs-openapi` and commit `docs/reference/backend/openapi.json`.
