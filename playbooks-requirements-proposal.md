## Requirements

The following product requirements are relevant to our discussion on the design of blocks and playbooks (please add more I've missed):

1. Model-agnostic: should be easy to add blocks using different model frameworks and dependency environments
1. Modular: should be easy to re-use parts of model workflows to create new ones
    - (Post MVP) Users should be able to use the UI / text representation to make new workflows from existing blocks
1. Contributions: modelers outside the Manta team should be able to write new blocks and playbooks and use them with Manta
    - Since modelers aren't familiar with app development, they shouldn't have to make a PR to the `manta` repo
    - This means the class definitions of blocks needs to be a Python package we publish to PyPI/conda-forge
1. Reproducibility: need to know which input data, playbook, blocks, and environments were used so that outputs can be reproduced
1. People should be able to run blocks (& playbooks) without the Manta app -- at least for testing
    - Running it without prefect is nice-to-have but not essential
1. Manta users should be able to view the outputs of each block after a playbook is run
1. Configurability: playbooks should have flexible and powerful configs so that as many possible related workflows can be captured by the same playbook.
    - Example: a global playbook-level config for solver options applies the same solver options to all blocks that call a solver (e.g. solver=highs). Block-level config still allows the user to overwrite the options for a particular solver block.
1. Validation: Manta should catch common workflow errors early, such as a missing `scenario` dimension, or a kind of result.

Not a requirement:
1. People should be able to run blocks and playbooks without Prefect
    - The current situation is that people have to use snakemake to run pypsa-based workflows. It feels reasonable that people need to use a workflow manager to run model workflows. Prefect has a SLURM plugin, so power users can run workflows on HPC clusters.


## Concepts

### Blocks

A block is a unit of modeling code with a given depdency environment and given computational resource requirements.
Blocks (can?) also define what dimensions they add/remove/modify, or what dimensions they need to run. 

This means:
- All code in a block runs with a fixed env; if you need to run code in 2 envs, you need at least 2 blocks
- All code in a block runs in a fixed compute env; if you want part of a code to use less/more computational resources, you need to split it into blocks.

### Playbooks

A playbook is a "program" written using blocks.
It's essentially a graph of blocks, config options (per block config, and global playbook-level config), sensible default configs, (and optionally) custom UI.
Playbooks can be serialized to some text form (e.g. Bryn's YAML inspired by GitHub Actions).

This definition encompasses both the playbooks built-in to Manta (and which can have custom UI / wizards for ease of use) and ephemeral playbooks that a future Manta UI will allow users to build / modify by drag-and-dropping blocks.

A playbook + a set of configs + input datarecord(s) = everything needed for a run.

## Proposals

### Playbook interpreter should live with the definition of blocks

- This allows playbooks to be used by power users without the Manta app
- As Bryn says: Playbooks need to be exposed to an external audience just as much as Blocks; they should be treated similarly IMO. A modeller will create Blocks and they will create Playbooks that connect those Blocks, both outside the Manta UI. 
- This will allow "integration tests" of sequences of blocks together

### What code lives where

This isn't the question of "in which repo?", this is the question of which package is responsible for what.

#### `manta-blocks` package:

This is a packaged library that OET modellers or 3rd party contributors can use as a "factory" to define new blocks.
This contains the class definition of what a block is, how it specifies its environment and computation requirements, and information on dimension requirements it has on its input(s) and output(s).

Assuming the above proposal, this package also has a "factory" to define playbooks.
This contains what a playbook is, how it is (de)serialized as text, and how it is interpreted.

Assuming "Not a requirement #1", this package can use Prefect and decorates blocks and playbooks with `@task` and `@flow`.

This package **does not contain** any concrete definitions of blocks and playbooks, apart from a few simple ones for testing.
It also does not contain any docker stuff, or any complex Prefect deployments; it uses the simplest Prefect deployment method to run tests.

#### `manta-batteries` package:

This is the standard library of blocks that OET maintains (mostly PyPSA blocks for MVP).
This package depends on `manta-blocks`, and individual blocks depend on e.g. PyPSA. (Or perhaps we need a `pypsa-blocks` package that depends on PyPSA, `calliope-blocks` package that depends on Calliope, etc?)

#### `manta` repo: `backend/`
- Stores playbooks in the app DB
- Calls the same "orchestrator" or "playbook interpreter" flow via Prefect for each playbook run; which playbook to run and the config are parameters to this flow.
- Local dev: sets up a docker work pool, workers, and registers Prefect deployments for each flow

#### `manta-infra`

The future repo that sets up the production deployment, Kubernetes etc.
- Sets up a kubernetes work pool, and kubernetes workers for blocks; the orchestrator / playbook interpreter runs on a long-lived worker on a process work pool.
    - Alternative: each playbook run runs on a k8s pod: idles for hours, exposed to eviction, and orphans its children if it dies

### Monorepo: keep `manta-blocks` in the main `manta` repo as a subdir

(`manta-batteries` can be a separate repo if we want a standalone example for 3rd party block contributors that doesn't overwhelm them with app code.)

Pros:
- Faster development (we can move quickly now and test things without having to set up new repos and publish packages)
- Easier to review 1 PR instead of N linked PRs
- Easier to deploy a change across many systems
- Easier to ensure security compliance when we have fewer repos' settings to sync and linting/testing/branch protection to set up
- Can still be split into separate repos later

Cons:
- More complex: you need a separate, nested requirements list / pyproject.toml and refs to the source of the package will be the monorepo which is quite confusing
    - Rebuttal: we already have top-level directories with different environments (frontend is typescript!), we don't have a top-level pyproject.toml. It's not hard to build or publish a subtree as a package. With uv workspaces, manta depends on it via a path/workspace source in dev and the pinned published version in prod. We can add a check to CI that only (re)builds `manta-blocks` when the subdirectory changes.

### Prefect workers fetch a block's code from git not PyPI

Prefect supports running flows that are defined in git repositories, so we can directly point to the `manta-batteries` repo and run any block from it; we don't need to fetch from PyPI.
This is the faster way to get started, and I don't see any advantages of fetching block code from PyPI.
With git we already have the ability to pin versions, do PR review, etc.

### Build docker images for block envs in CI, instead of pixi installs at run time

I'm happy to keep dockerfiles out of `manta-batteries` and continue with pixi environments there since that's lighter-weight and sufficient for PyPSA -- which is what most of our v1 blocks will use.
However, `PLAYBOOKS-AND-BLOCKS-PLAN.md` L375–L404 suggests using a generic worker image and running `pixi install` every run.
That's fine for a first step of implementation, but eventually its cleaner and faster to build one docker image per block env (e.g. one for all PyPSA blocks) and point Prefect to that image.
This shouldn't be too much more work, since Prefect supports docker envs out of the box.

### `manta`'s CI generates catalogue of blocks from pinned `manta-batteries` commit

Eventually, I like Bryn's PoC idea of generating a catalogue of blocks, their envs, and their descriptions.
This can be done in the CI of `manta` before we deploy the app, or eventually by the CI of `manta-batteries` and loaded into `manta` dynamically if we want to upgrade blocks without redeployment.
