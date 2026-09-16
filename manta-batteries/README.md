<!--
SPDX-FileCopyrightText: 2026 Manta Blocks contributors

SPDX-License-Identifier: MIT
-->

# Manta Batteries

The standard library of [Manta blocks](../manta-blocks) — the concrete units of
energy-model work that Manta ships, built on [PyPSA](https://pypsa.org):

| Block | What it does |
| --- | --- |
| `cluster_time` | Shorten a model's time series, so later blocks have less to solve |
| `overnight_capacity_expansion` | Decide what to build, treating the whole model as one moment in time |
| `myopic_capacity_expansion` | Decide what to build one investment period at a time, in order |
| `rolling_horizon_dispatch` | Decide how to run a system, a stretch of time at a time |

> This directory is developed inside the `manta` monorepo for now, but is written as
> a standalone package: it is also the reference for third-party modellers writing
> their own block libraries, so it must not depend on the Manta app — only on
> `manta-blocks`.

## Layout

```text
pixi.toml            The environments blocks run in (names are the contract)
catalogue.json       Generated description of every block (see below)
src/manta_batteries/
  __init__.py        Registers the blocks by name, without importing them
  time_cluster.py    ... one module per block ...
  pypsa_helpers.py   Where blocks meet their data (records in, records out)
  pypsa_configs.py   Settings models mirroring PyPSA's optimize options
  provision.py       Set up work pools + Prefect deployments for every block
  examples/          The example playbook (YAML and Python) and its settings
```

## Environments

Each block declares the pixi environment it needs (`ENV = "pypsa"`). One worker runs
per environment, and the playbook orchestrator runs in its own PyPSA-free
`orchestrator` environment — proof that a block's dependencies stay its own.

```bash
pixi run -e dev test           # packaging and registration, without PyPSA
pixi run -e full test          # everything, including the PyPSA blocks
pixi run -e full python -m manta_batteries.examples.cluster_expand_dispatch
```

## The catalogue

`catalogue.json` describes every block — settings as JSON schema, dimensions,
environments — so that processes which cannot import PyPSA (the Manta backend, the
orchestrator) can still validate and wire playbooks that use these blocks. It is
committed; regenerate it after adding or changing a block:

```bash
pixi run -e pypsa catalogue
```

<!-- TODO: generate and verify catalogue.json in CI from the pinned manta-batteries
state instead of committing it by hand, per the playbooks requirements proposal. -->

## Running under Manta

Manta's dev stack builds one job image from this directory (both environments
pre-installed) and provisions the work pools and deployments itself, from the
committed `catalogue.json` — nothing in this package is involved. There
**every block runs in its own container** from that image, spawned by a docker
worker for the pool. See [docker/README.md](../docker/README.md).

Records are S3 urls there; `manta_blocks.records` stages them for the blocks using
standard `AWS_*` environment variables (handed to job containers via the pool
templates).

To try a run end to end you need input data; the example seeder builds a tiny
network and publishes it:

```bash
pixi run -e pypsa python -m manta_batteries.examples.seed_network s3://manta/examples/network-tiny.nc
```

## Running without Manta (power users)

Everything here also runs without the app, against any Prefect server — see
"Running and deploying" in [manta-blocks' README](../manta-blocks/README.md).
The pools are process-type (jobs run as subprocesses of a worker started inside
the matching pixi environment), which is all this library needs:

```bash
prefect server start                                        # in one window
pixi run -e pypsa python -m manta_batteries.provision
pixi run -e pypsa prefect worker start --pool manta-pypsa   # in another window
pixi run -e orchestrator prefect worker start --pool manta-orchestrator
```

Then start runs with `manta_playbooks.control.start_run`, or run a playbook in one
process with `playbook.run(record, config)` — which is what the tests do.
