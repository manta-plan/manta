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

## To implement / fix

Three changes to the PoC as it stands on `sid/docker-pools-in-docker-dir`, in the order
they should be done.
Together they replace the one heavyweight image shared by the orchestrator and the PyPSA
blocks with one image per block environment plus a slim orchestrator image, and remove the
shared filesystem that stands between the current stack and Kubernetes.

### 1. Persist Prefect results to S3, not a shared volume

**Now**: `run_block` returns a `DataRecord` as `{"url": ...}` and Prefect persists it to
local disk (`persist_result=True` in `manta-blocks/src/manta_blocks/entrypoint.py` and
`manta_playbooks/execution.py`).
The orchestrator reads that value back from another process, so every job container and the
orchestrator container mount the same `prefect-results` volume at
`PREFECT_LOCAL_STORAGE_PATH=/prefect-results`.
A volume is the only reason those containers must sit on one machine.

Note this is *not* about block data: model data (netCDF) already goes straight to S3 through
`manta_blocks.records` (`stage` / `stage_output`).
Only Prefect's own small result payloads are on disk.

**Change**: point Prefect's default result storage at the S3 store, which needs no change to
either package.

1. Install `prefect-aws` in both images that execute flows (`docker/job.Dockerfile`,
   `docker/control.Dockerfile`).
2. In `docker/provision.py`, before provisioning, register the storage block on the Prefect
   server:

   ```python
   from botocore.config import Config
   from prefect_aws import AwsCredentials, S3Bucket
   from prefect_aws.client_parameters import AwsClientParameters

   credentials = AwsCredentials(
       aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
       aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
       # SeaweedFS has no bucket-subdomain DNS, so path-style addressing, for the same
       # reason manta_blocks.records uses it.
       aws_client_parameters=AwsClientParameters(
           endpoint_url=os.environ["AWS_ENDPOINT_URL"],
           config=Config(s3={"addressing_style": "path"}),
       ),
   )
   S3Bucket(
       bucket_name=os.environ.get("MANTA_S3_BUCKET", "manta"),
       bucket_folder="prefect-results",
       credentials=credentials,
   ).save("manta-results", overwrite=True)
   ```

   `overwrite=True` keeps re-provisioning idempotent, like everything else there.
3. Set `PREFECT_RESULTS_DEFAULT_STORAGE_BLOCK=s3-bucket/manta-results` in `job_env()` (so
   every job container gets it) and on the `prefect-worker-orchestrator` service.
4. Delete from `docker/compose-dev-services.yaml`: the `prefect-results` volume and its two
   mounts, `MANTA_JOB_VOLUMES`, and `PREFECT_LOCAL_STORAGE_PATH`.
   Delete `RESULTS_PATH` and the `MANTA_JOB_VOLUMES` handling from `docker/provision.py`.

**Verify**: run the walkthrough in `playbook-run-instructions.md`.
The run reaches COMPLETED, `docker volume ls` shows no results volume, and objects appear
under `s3://manta/prefect-results/`.
The failure to watch for is the orchestrator failing to read a child's result, which shows
up as the parent flow erroring straight after a block succeeds.

### 2. Run the orchestrator on the slim image

**Now**: `prefect-worker-orchestrator` runs the ~2 GB job image with
`pixi run -e orchestrator`, purely because both pixi environments come from one
`manta-batteries/pixi.toml` and one build was simpler.
The orchestrator imports `manta_playbooks.execution:run_playbook`, resolves blocks from the
catalogue passed as a run parameter, and never imports a block, so it needs neither pixi nor
PyPSA.

**Change**: in `docker/compose-dev-services.yaml`, build `prefect-worker-orchestrator` from
`docker/control.Dockerfile` as `manta-playbooks-control`, with
`command: prefect worker start --pool manta-orchestrator`.
That image already installs `manta-blocks`, which ships both `manta_blocks` and
`manta_playbooks`.

One trap: the orchestrator service is currently the only thing that builds the job image, so
`up` would stop building it.
Add a build-only service in the same profile:

```yaml
  playbooks-job-image:
    profiles: ["playbooks"]
    build:
      context: ..
      dockerfile: docker/job.Dockerfile
    image: manta-playbooks-job
    command: ["true"]
    restart: "no"
```

Keep the `orchestrator` pixi environment in `manta-batteries/pixi.toml`: it is how a power
user starts an orchestrator worker without docker, per that README.

**Verify**: a playbook run still completes, and `docker images` shows the orchestrator
worker on `manta-playbooks-control`.

### 3. One image per block environment, named by the catalogue

**Now**: `EnvironmentSpec` (in `manta_blocks/environments.py`) declares an `image` field that
nothing ever sets — `for_block` populates only `name` and `manifest` — so
`docker/provision.py` uses a single `MANTA_JOB_IMAGE` for every environment.
With a second modelling framework that means every block run pulls an image carrying every
framework.

**Change**:

1. Build one image per environment.
   Give `docker/job.Dockerfile` an `ARG PIXI_ENV` and install only that environment
   (`RUN pixi install --locked -e ${PIXI_ENV}`), then build it once per environment in
   compose with its own `image:` tag (`manta-playbooks-job-pypsa`).
   The job command stays `pixi run -e <env> prefect flow-run execute`; dropping pixi from the
   command needs the environment baked into the image's entrypoint and is a separate change.
2. In `docker/provision.py`, resolve each environment's image in this order: `spec.image`
   from the catalogue, then a `MANTA_ENV_IMAGES="pypsa=manta-playbooks-job-pypsa,..."`
   mapping, then today's `MANTA_JOB_IMAGE` as the fallback.
   Reading `spec.image` first means nothing here changes once CI stamps images into the
   catalogue.
3. Populate `spec.image` at catalogue-publish time, not in `for_block`: the environment
   describing itself cannot know which image it was built into.
   The CI that builds the image is what knows, per "`manta`'s CI generates catalogue of
   blocks" above.

**Verify**: provision with two environments described in the catalogue and confirm each pool's
job template carries its own image, and that a run of a PyPSA block pulls only the PyPSA
image.

**Leaves open**: `MantaBlock.MANIFEST` points at a third-party block's pixi manifest, which
means nothing once an environment is an image.
It should either be dropped for container targets or reinterpreted as "where to build the
image from".

### Other To Dos

- Rename Renderer -> Provisioner
- Figure out a nice way for blocks to write results to S3 without each block def in manta-batteries having to know about S3
- Make per-step logs and status endpoints so that FE can show the graph and status/logs of each block