<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Documentation

This page shows how to build the documentation site, refresh the REST API reference, and find the rules a page follows.
You need [pixi](https://pixi.prefix.dev/) for the site and [uv](https://docs.astral.sh/uv/) for the API schema.

## Build and serve the site

The site is built with [Zensical](https://zensical.org/) from `mkdocs.yml`, in the pixi environment at the repository root.
To preview it while you edit, run this from the repository root:

```bash
pixi run docs-serve
```

Zensical prints the local URL and rebuilds a page when you save it.
To build the site the way CI and Read the Docs do, run:

```bash
pixi run docs-build
```

The build is strict, so a dead link or a missing anchor fails it.
The site is written to `.docs/`, which git ignores.

## Pages pulled in from the READMEs

Installation and most contributing pages contain sections of `README.md`, `CONTRIBUTING.md` and the package READMEs.
Each page includes a section with a snippet, `--8<-- "README.md:docs-install"`, which takes the text between the `[start:docs-install]` and `[end:docs-install]` markers.
To change that text, edit the README, not the page.
A link in a pulled-in section that points outside `docs/` is a full GitHub URL, because a relative one fails the strict build.

## Refresh the REST API reference

The [REST API](../reference/backend/rest-api.md) page is generated from `docs/reference/backend/openapi.json`, the OpenAPI schema of the backend's v1 routes.
`pixi run docs-build` and `pixi run docs-serve` regenerate the page first, with `tools/docs/gen_rest_api.py`.
The page itself is ignored by git, so edit the generator rather than the page.

The schema is committed, and you export it again whenever you change a route, a request or a result:

```bash
pixi run docs-openapi
```

This runs `tools/docs/export_openapi.py` in the backend's uv environment.
It builds the app from the v1 router alone, so no database or other service needs to be running.
CI exports the schema on every pull request and fails if the result differs from the committed file.

## Writing rules

The rules for a page live in two agent skills in `.claude/skills/`.
`docs-writing` sets what kind of page to write and how each kind is shaped.
`prose-writing` sets the reader, the voice and the words, for pages, pull requests and issues alike.
Each skill has a `project.md` beside it with the rules that are Manta's own.
