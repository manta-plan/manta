# Running calculation jobs in their own containers — plan

**The problem today**

When the app starts, it quietly launches a background helper to run our one existing job (the pi-digit calculation). It's a shortcut that happens to work, but it's fragile — no automatic recovery if it fails to start, and it wasn't built with the idea that we'll eventually have many different jobs running independently, some potentially heavy or long-running.

**What we're building**

We're separating "the app that people interact with" from "the thing that actually runs calculations," and giving the second one a proper, dedicated home.

- A new, self-contained worker package, sitting alongside the backend and frontend, with nothing to do with either. It holds exactly two things: the calculation code, and the instructions for building it into a container image.
- A single background service watches for new job requests and, for each one, starts a fresh, isolated container to actually run it. Every run gets a clean, disposable environment — no jobs stepping on each other's toes.
- The worker announces itself when it starts up — it registers "here's a job I know how to run" with the system. The backend app never needs to know anything about how a calculation works; it only ever asks "please run this" and later "what was the result." That's the entire contract between the two.
- No manual setup, ever. Starting the normal services plus starting the app is the whole procedure. Nobody needs to remember a special command to wire this up.
- We're deliberately not adding concurrency limits or moving to a more robust database for the job-tracking system yet — those are real future improvements, but not needed to prove this out, and adding them now would be complexity we can't yet justify.

**Why this is more than just "fixing the pi job"**

Today there's exactly one job. Soon there will be many — real energy-system-modelling calculations, each potentially needing very different tools and libraries. The current shortcut couldn't support that: everything shared one process, one set of dependencies, one point of failure.

The design here fixes that at the root. Because each job type lives in its own self-contained package with its own container image, adding a new kind of job later is purely additive — a new folder, its own dependencies, its own image, registered the same way. It doesn't touch the backend, doesn't touch other jobs, and can't accidentally break something unrelated by needing a newer or conflicting library. The backend, the "waiting room" that watches for work, and each individual job all stay cleanly separated and independently replaceable. This was an open question flagged when the very first version of this system was built — this PR is effectively answering it.

**The path to Kubernetes**

We already know this needs to run on Kubernetes eventually for real production workloads. The good news: the way we're building this, that move is a swap, not a rebuild.

- The container image doesn't change. Whether a job runs via Docker on one machine or as a pod in a cluster, it's the same packaged image doing the same thing.
- What changes is who's in charge of starting containers. Right now, our watcher service talks directly to Docker on the same machine. On Kubernetes, it would instead ask the cluster to start the job — same idea, different manager.
- The one new piece of infrastructure we'd need is a place to publish images so any machine in the cluster can pull them (a "registry") — right now everything runs locally on one machine, so this isn't needed yet.
- Nothing about how the app submits jobs or reads results changes at all — that part is already fully decoupled from where the actual work happens.

**Verifying it works**

Once built: submit a job through the app, confirm a real, isolated container actually spins up and runs it, and confirm the result and logs come back correctly — proving the whole path end to end with nothing set up by hand.
