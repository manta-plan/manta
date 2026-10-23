<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# Contributing

<!-- --8<-- [start:docs] -->

Contribution rules and conventions for datarecord. We welcome all contributors —
a good place to start is the issues tagged
["help wanted"](https://github.com/energy-models/datarecord/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22)
and
["good first issue"](https://github.com/energy-models/datarecord/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22).

By opening a pull request you represent that your contribution is your own
original work and that you agree to license it under the project's MIT license.

## Reporting issues

Open a GitHub issue to report a bug or request a feature:

- [Report a bug](https://github.com/energy-models/datarecord/issues/new?template=BUG-REPORT.yml)
  — include a full traceback where there is one.
- [Request a feature](https://github.com/energy-models/datarecord/issues/new?template=FEATURE-REQUEST.yml).
- [Report a documentation problem](https://github.com/energy-models/datarecord/issues/new?template=DOCS.yml).
- [Anything else](https://github.com/energy-models/datarecord/issues/new).

## Development workflow

- Manage the environment with [`pixi`](https://pixi.sh) and run every command
  inside it: `pixi run <command>` (e.g. `pixi run pytest`).
- Run the test suite with `pixi run test`, and lint, format and type-check with
  `pixi run lint` before every commit — it runs the full lefthook hook set
  (ruff, prettier, taplo, typos, zizmor, reuse and mypy).
- Lockfiles must stay consistent with package metadata: after any change to
  `pixi.toml`, run `pixi lock`.
- The per-python environments (`py311` … `py314`) mirror CI.

## Project conventions

- Branch off `main` for every change and open pull requests via the GitHub CLI
  (`gh`). A one-line commit message is fine for a small change; a larger one gets
  a summary line of at most 50 characters, a blank line, then a body describing
  what changed and why. Before opening a pull request, check you have updated
  `CHANGELOG.md`, added or updated documentation, and added tests for new
  functionality; give the pull request a clear summary of the change.
- Write tests for new features and bug fixes under `tests/` as `test_*.py`,
  reusing the shared fixtures in `tests/fixtures.py` and `tests/conftest.py`
  where useful. Run the tests after making changes and make sure they pass.
- The [design pages](https://energy-models.github.io/datarecord/design/) are the
  authoritative design. Cite them from a
  docstring's numpydoc `Notes` section rather than restating the argument — a
  comment that re-argues the design is a defect. When behaviour changes, update
  the page, not just the code. (`Notes`, not `References`: numpydoc discourages
  web links under `References` and expects entries there to augment a docstring
  rather than be required to understand it, which these are.)
- Documentation is mkdocs: `pixi run -e docs docs` serves it locally, and
  `pixi run -e docs docs-build` is the strict build CI runs, which fails on a
  broken cross-reference. Every pull request publishes a rendered preview to
  `https://energy-models.github.io/datarecord/pr-<N>/`, linked from a comment on
  the pull request itself; it is removed when the pull request closes, and a
  weekly job sweeps any that outlive it. Both live in
  `.github/workflows/docs.yml`.
- No tool import may leak into core `datarecord`
  ([module layout](https://energy-models.github.io/datarecord/design/module-layout/)):
  everything framework-specific lives under `datarecord/tools/` behind an
  optional extra.

## Design enhancement proposals

A change to the design starts as a design enhancement proposal (DEP): the
argument for it, the design it lands, and usage examples.

- Start from the
  [template](https://energy-models.github.io/datarecord/design/proposals/dep-NNNN-template/):
  copy it to `docs/design/proposals/dep-NNNN-slug.md`, where `NNNN` is the next
  free four-digit number, and append it to the end of the `Enhancement proposals`
  nav in `mkdocs.yml`. A number is never reused or reassigned.
- Its header carries `Status` — `Draft`, `Accepted`, `Implemented` or
  `Superseded`, with the date — and `Version`, the release it ships in:
  `Unreleased` until the release that sets it.
- Implementing it moves the design into the
  [design pages](https://energy-models.github.io/datarecord/design/) and the
  usage examples into the
  [usage pages](https://energy-models.github.io/datarecord/usage/), with as much
  of the argument as they need to stand on their own, and what it leaves open
  into [open questions](https://energy-models.github.io/datarecord/design/open-questions/).
  The DEP stays as the record of the argument, and is not revised after: a
  change is a new DEP that replaces it.
- **Nothing outside the DEPs links to one** — not a design or usage page, a
  docstring, a test or an error message — except open questions and the
  template. A DEP that is not yet implemented is not the design, and one that
  is has been superseded by the pages it landed in. `pixi run lint` fails on
  such a link.

## Architecture in one paragraph

datarecord stores dimensioned attribute data with a declared schema: entities
(named members of a type, unique record-wide), groups of them — a `connection`
over `(entity, bus)` being the one every network has — attribute values over
both, and the axes those values vary along. A record is defined by the
`RecordLike` protocol — what it answers, not how it is stored — and a parquet
directory is its on-disk form. The concrete `Record` folds a tree of layers
resolved last-writer-wins, degenerating to a scan over a single directory
(`Record.at(uri)`), so a consumer cannot tell how many layers it holds. Queries
are built with `narwhals` and executed by `duckdb`, staying lazy until
collected. Beyond those and `pydantic`, core depends on nothing. Keep new
features consistent with this schema-declared, backend-agnostic,
lazily-evaluated design.

## Releasing

The version lives in `[project].version` in `pyproject.toml`; there is no
VCS-derived versioning. `CHANGELOG.md` tracks user-facing changes under an
`[Unreleased]` heading between releases.

To cut `vX.Y.Z`:

1. Confirm `pixi run test` and `pixi run -e docs docs-build` pass — best done on
   a release pull request.
2. Rename the `[Unreleased]` heading in `CHANGELOG.md` to
   `vX.Y.Z` with the release date, set `version` in `pyproject.toml`, and set
   `Version` to `vX.Y.Z` in every DEP header reading `Unreleased`.
3. Merge the release pull request, then tag the merge commit `vX.Y.Z` and create
   the GitHub release from that tag.
4. Open a follow-up adding a fresh `[Unreleased]` heading to `CHANGELOG.md`.

## AI-assisted contributions

If you use AI tools when contributing, please read `AGENTS.md`
for how AI-generated content must be marked and what we expect you to write
by hand.

<!-- --8<-- [end:docs] -->
