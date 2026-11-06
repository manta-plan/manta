<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Docs rules for Manta

This file contains Manta's own docs rules.
[SKILL.md](SKILL.md) contains the shared rules, and where the two differ, this file wins.

## Nav sections

- Home (`docs/index.md`) states what Manta is, from the preamble of `README.md`.
- Installation (`docs/installation/`) has one page per kind of work: the full stack, blocks and playbooks, the backend and the frontend. They pull setup and running from `README.md` and the package READMEs, and the contributing pages keep tests, linting and coding rules.
- Explanation (`docs/explanation/`) holds the explanation pages, such as the architecture.
- Reference (`docs/reference/`) holds the Python API of `playbook` and `runner`, and the REST API.
- Contributing (`docs/contributing/`) is the section for someone who changes Manta, last in the nav. Its pages pull their content from `CONTRIBUTING.md` and the package READMEs.

## The running example

None is chosen yet.

## Figure colours

No figure exists yet. Assign the colours with the first one.

## Generated content

| Page | Written by | Checked by |
| --- | --- | --- |
| `docs/reference/backend/rest-api.md` | `tools/docs/gen_rest_api.py`, from `docs/reference/backend/openapi.json`, before every `pixi run docs-build` and `pixi run docs-serve`. Git ignores the page. | the strict build |
| `docs/reference/backend/openapi.json` | `pixi run docs-openapi`, which runs `tools/docs/export_openapi.py` in the backend's uv environment | `.github/workflows/docs.yml` exports it again and fails if it differs |

## Extra mechanics

- In phase 1, `README.md`, `CONTRIBUTING.md` and the package READMEs are the source of every installation and contributing page. A page pulls a section in with a snippet between `<!-- --8<-- [start:name] -->` and `<!-- --8<-- [end:name] -->` markers. Edit the README, not the page.
- A GitHub alert (`> [!NOTE]`) in a pulled-in section renders as an admonition, through the `github-callouts` extension of `markdown-callouts`.

## Extra gates

After a change to a backend route, request or result, run `pixi run docs-openapi` and commit `docs/reference/backend/openapi.json`.
