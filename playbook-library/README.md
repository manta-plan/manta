<!--
SPDX-FileCopyrightText: 2026 Manta contributors

SPDX-License-Identifier: MIT
-->

# playbook-library

The blocks **and** playbooks that Manta ships, built on [PyPSA](https://pypsa.org).

The framework next door ([`playbook`](../playbook)) defines what a block and a
playbook *are*, and runs them. This is the content: the ready-made pieces of
energy-model work a user can actually pick and run.

The blocks — single units of work on a model:

| Block | What it does |
| --- | --- |
| `cluster_time` | Shorten a model's time series, so later blocks have less to solve |
| `overnight_capacity_expansion` | Decide what to build, treating the whole model as one moment in time |
| `myopic_capacity_expansion` | Decide what to build one investment period at a time, in order |
| `perfect_capacity_expansion` | Decide what to build in every investment period at once, with perfect foresight |
| `rolling_horizon_dispatch` | Decide how to run a system, a stretch of time at a time |

The playbooks chain those blocks into something you can run. Each one declares its
inputs with defaults, so a user can run it without setting any input:

| Playbook | What it does |
| --- | --- |
| `cluster-expand-dispatch` | Shorten the time series, decide what to build, then decide how to run it |
| `expand` | Decide what to build: overnight, myopic or with perfect foresight |

> This directory is developed inside the `manta` monorepo for now, but is written as a
> standalone package: it is also the reference for anyone writing their own library of
> blocks and playbooks, so it must not depend on the Manta app — only on `playbook`.

## Layout

```text
pixi.toml                       The environments blocks run in (names are the contract)
src/playbook_library/
  __init__.py                   Registers the blocks by name, without importing them
  catalogue.json                Generated description of every block (see below)
  time_cluster.py               ... one module per block ...
  pypsa_helpers.py              Where blocks meet their data, and PyPSA work they share
  pypsa_configs.py              Settings models mirroring PyPSA's optimize options
  examples.py                   A tiny network, and the example playbook run on it
  public_data.py                Downloads of the stores in the public test data bucket
  playbooks/                    The playbooks this library ships
```

## Getting started
<!-- --8<-- [start:docs-setup] -->

```bash
pixi run -e dev test     # packaging, registration, and the catalogue, without PyPSA
pixi run -e full test    # everything, including the blocks and the end-to-end run
```

Then see a real run, start to finish:

```bash
pixi run -e full python -m playbook_library.examples
```

That seeds a tiny network — one bus, one generator that can be built, a day of demand
— as the root revision of a datarecord store, runs the `expand` playbook on it, and
prints the final revision. Pass a directory or an `s3://` URL to choose where the store
is created.

To run a single block instead, without a playbook around it:

```bash
pixi run -e pypsa python -m playbook.blocks.run_one cluster_time \
    --source playbook_library --config '{"n_hours": 6}' \
    --revision '{"store": "<store>", "id": "<revision>"}'
```
<!-- --8<-- [end:docs-setup] -->

## Environments
<!-- --8<-- [start:docs-environments] -->

Each block declares the environment it needs (`ENV = "pypsa"`), and that name is what
picks the environment it later runs in. The environments themselves are pixi's:

| Environment | What it is for |
| --- | --- |
| `default` | no PyPSA — what a process that only *reads* blocks looks like |
| `pypsa` | the solver stack: what a block actually runs in |
| `dev` | `default` plus pytest and ruff |
| `full` | everything; the only environment that can run the blocks |

That `dev` has no PyPSA and its tests still pass is the check that a block's
dependencies stay its own.
<!-- --8<-- [end:docs-environments] -->

## Adding a block

1. Write it in its own module, as a `MantaBlock` subclass — see
   [the framework's README](../playbook/README.md#writing-a-block) for what a block
   declares, and `time_cluster.py` for the shortest real example.
2. Register it in `__init__.py` with `register_lazy("your_block",
   "playbook_library.your_module:YourBlock")`. Registering the location rather than
   importing the class is what keeps this package importable without PyPSA.
3. Read and write data through `pypsa_helpers`: `to_network(base)` in,
   `write_network(n, base)` out, as a new revision in the store of the `base` revision
   the block's `run` was given. Blocks never open files themselves, which is
   what lets the same block run against a local file or object storage unchanged.
   A helper only one block needs is a method on that block's class; `pypsa_helpers`
   holds only what blocks share.
4. Regenerate the catalogue (below) and add tests (below).

Keep PyPSA imports inside the block modules. `__init__.py`, `playbooks/` and the
catalogue must all keep working in an environment that has never heard of PyPSA.

## Adding a playbook

1. Write it as a YAML document in `playbooks/`. For the format, see
   [the playbook syntax](../docs/reference/playbook/syntax.md), and for a real
   playbook, see `expand.yaml`.
2. Write every block setting in the step's `with`. Only where a user should be able to
   change a setting for a run, declare an input and read it in `with`. Give every
   input a default, so that a user can run the playbook without setting any.
3. Run the tests. The tests in `tests/test_playbooks.py` check every playbook in
   `playbooks/` with its default inputs, so a default that cannot run fails there.
   Add a case for anything else the playbook has to get right. Anything that offers
   playbooks to a user cannot import the blocks they name. So most of those tests
   run without PyPSA, and check against the catalogue.

Playbooks are found by the name written inside the document, not by filename, so
renaming a file changes nothing and two playbooks claiming one name is an error.

## The catalogue

`catalogue.json` describes every block — settings as JSON schema, dimensions,
environments — so that processes which cannot import PyPSA can still list these blocks
and check a playbook and its settings against them. It is committed; regenerate it after adding or
changing a block:

```bash
pixi run -e pypsa catalogue
```

A stale catalogue fails the `full` test suite, so this is not something you can forget
silently.

<!-- TODO: regenerate and verify catalogue.json in CI, rather than relying on the
committed file being refreshed by hand. -->

## Testing your contribution
<!-- --8<-- [start:docs-testing] -->

```bash
pixi run -e dev test     # must pass without PyPSA
pixi run -e full test    # must pass with it
pixi run -e dev lint
```

What the suite covers, and where to add to it:

| File | What it checks |
| --- | --- |
| `tests/test_catalogue.py` | the committed catalogue matches the blocks and works without PyPSA |
| `tests/test_library.py` | each block, run on a tiny network: a usable network comes out as a new revision of the one it read |
| `tests/test_playbooks.py` | the shipped playbooks parse and have no issues with their default inputs, checked against the catalogue and, with PyPSA, against the blocks |
| `tests/test_pypsa_end_to_end.py` | the whole playbook, one network in and one out |

Tests that need PyPSA start with `pytest.importorskip("pypsa")` and carry
`pytestmark = pytest.mark.pypsa`, so they skip rather than fail in `dev`. A new block
needs at least a case in `test_library.py` showing it produces a usable network as a
new revision in the store it read from — keep the networks tiny, so the suite stays quick.
<!-- --8<-- [end:docs-testing] -->

## Current limitations

- Blocks read and write revisions of a datarecord store, and turning them into PyPSA
  networks and back is confined to `pypsa_helpers.py`.
- The settings models in `pypsa_configs.py` mirror PyPSA's `optimize` options by hand,
  and have to be updated when those change.
