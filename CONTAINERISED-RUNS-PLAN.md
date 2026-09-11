# Running calculation jobs in their own containers — plan

## 1. The problem

Manta runs its only job inside the application process.
Starting the app launches a background helper, and that helper computes pi digits.
Nothing restarts the helper if it fails to come up.

The arrangement also assumes there is one job.
Every calculation shares one process, one set of dependencies and one point of failure.
Energy-system modelling needs many jobs, each with its own tools and libraries, and some of them heavy or long-running.

## 2. The design

The application people interact with is separated from the thing that runs calculations, and the second gets a home of its own.

- **A worker package sits alongside the backend and the frontend.**
  It holds two things: the calculation code, and the instructions for building it into a container image.
  It has nothing to do with either neighbour.
- **One background service turns job requests into containers.**
  The watcher sees a new request and starts a fresh container to run it.
  Every run gets a clean, disposable environment, so no two jobs share one.
- **The worker registers its job types at startup.**
  It announces what it knows how to run.
  The backend asks "please run this" and later "what was the result", and that is the entire contract between them.
- **Starting the normal services and the app is the whole procedure.**
  No command wires the parts together by hand.
- **Concurrency limits and a durable store for job tracking stay out.**
  Both are real improvements.
  Neither is needed to prove this design, and adding them now buys complexity against no evidence.

## 3. Adding a new job type

Adding a job type is additive.
A new job is a new folder with its own dependencies and its own image, registered the same way as the first.
It touches no backend code, touches no other job, and cannot break something unrelated by needing a newer or conflicting library.
The backend, the watcher and each job stay separate and independently replaceable.

The first version of this system flagged this as an open question, and this plan answers it.

## 4. The path to Kubernetes

Production needs Kubernetes, and this design makes the move a swap rather than a rebuild.

- **The container image does not change.**
  The same packaged image runs under Docker on one machine or as a pod in a cluster.
- **The watcher changes.**
  Today it asks the local Docker daemon for a container.
  On a cluster it asks the cluster for a pod.
  The idea is the same and the manager is different.
- **An image registry is the one new piece of infrastructure.**
  Any node in the cluster has to be able to pull the worker image.
  One machine running everything locally does not need one yet.
- **Job submission and result reading do not change.**
  Both are already decoupled from where the work happens.

## 5. Verification

Submit a job through the app.
Confirm that an isolated container starts and runs it, and that the result and the logs come back.
Nothing is set up by hand at any point in that path.
